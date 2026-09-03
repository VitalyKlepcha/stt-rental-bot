"""Bot setup, dispatcher wiring, and lifecycle management.

Provides factory functions for the :class:`Bot` and :class:`Dispatcher`,
plus ``run_polling`` / ``run_webhook`` entry points for local development
and production (Cloud Run) respectively.

Services are created upfront, injected into handlers via aiogram's
``workflow_data``, and closed on shutdown through the dispatcher's
shutdown event.
"""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass

import structlog
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from voice_bot.config import settings
from voice_bot.handlers import router
from voice_bot.middleware import AccessControlMiddleware
from voice_bot.services.extraction import ExtractionService, create_extraction_service
from voice_bot.services.pdf_generator import PDFGeneratorService, create_pdf_generator
from voice_bot.services.transcription import (
    TranscriptionService,
    create_transcription_service,
)

logger = structlog.get_logger(__name__)


@dataclass
class Services:
    """Container for the bot's service instances.

    Passed to :func:`create_dispatcher` which injects each service into
    aiogram's ``workflow_data`` so handlers receive them as typed parameters.
    """

    transcription_service: TranscriptionService
    extraction_service: ExtractionService
    pdf_generator: PDFGeneratorService


def create_services() -> Services:
    """Create all service instances from application settings."""
    return Services(
        transcription_service=create_transcription_service(),
        extraction_service=create_extraction_service(),
        pdf_generator=create_pdf_generator(),
    )


async def _close_services(services: Services) -> None:
    """Close async service clients and release resources."""
    await services.transcription_service.close()
    await services.extraction_service.close()
    logger.info("services_closed")


def create_bot() -> Bot:
    """Create and return an aiogram Bot instance with HTML parse mode."""
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.debug("bot_created")
    return bot


def create_dispatcher(services: Services) -> Dispatcher:
    """Create a Dispatcher with middleware, router, and services wired in.

    Parameters:
        services: Container of service instances to inject into handlers
            via ``workflow_data``.

    Returns:
        A configured Dispatcher ready for polling or webhook mode.
    """
    dp = Dispatcher()

    dp.message.middleware(
        AccessControlMiddleware(allowed_user_ids=settings.allowed_user_ids),
    )
    dp.callback_query.middleware(
        AccessControlMiddleware(allowed_user_ids=settings.allowed_user_ids),
    )

    dp.include_router(router)

    dp.workflow_data.update(
        transcription_service=services.transcription_service,
        extraction_service=services.extraction_service,
        pdf_generator=services.pdf_generator,
    )

    @dp.shutdown()
    async def _on_shutdown(**_: object) -> None:
        """Close service clients when the dispatcher shuts down."""
        await _close_services(services)

    logger.debug("dispatcher_created")
    return dp


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    """Run the bot in long-polling mode for local development.

    Clears any existing webhook, then starts polling.  When polling stops
    (SIGINT or cancellation), the dispatcher's shutdown event fires —
    closing service clients — and the bot session is closed.
    """
    logger.info("starting_polling")
    await bot.delete_webhook()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("bot_session_closed")


async def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    """Run the bot in webhook mode for production (Cloud Run).

    Registers the webhook with Telegram, creates an aiohttp application
    with the webhook handler and a ``/healthz`` endpoint, and starts
    the HTTP server.  Gracefully shuts down on SIGINT or SIGTERM.
    """
    webhook_url = f"{settings.webhook_url}{settings.webhook_path}"
    logger.info("starting_webhook", webhook_url=webhook_url)

    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)

    async def _healthz(_request: web.Request) -> web.Response:
        """Health check endpoint for Cloud Run."""
        return web.json_response({"status": "ok"})

    app.router.add_get("/healthz", _healthz)

    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.port)
    await site.start()

    logger.info("webhook_server_started", port=settings.port)

    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret,
        )
        logger.info("webhook_registered", webhook_url=webhook_url)
    except Exception as exc:
        logger.error(
            "webhook_registration_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            webhook_url=webhook_url,
        )

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        """Set the stop event to trigger graceful shutdown."""
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler — not needed for Cloud Run
            pass

    try:
        await stop_event.wait()
    finally:
        logger.info("webhook_server_stopping")
        await runner.cleanup()
        await bot.session.close()
        logger.info("webhook_server_stopped")
