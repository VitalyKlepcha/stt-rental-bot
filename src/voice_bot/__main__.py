"""Application entry point — run with ``python -m voice_bot``."""

from __future__ import annotations

import asyncio
import sys

import structlog

from voice_bot.bot import (
    Services,
    create_bot,
    create_dispatcher,
    create_services,
    run_polling,
    run_webhook,
)
from voice_bot.config import settings
from voice_bot.logging_config import setup_logging

logger = structlog.get_logger(__name__)


def main() -> None:
    """Start the voice-to-PDF Telegram bot.

    Sets up structured logging, creates the bot/dispatcher/services,
    and runs in webhook or polling mode depending on configuration.
    """
    setup_logging(settings.log_level)

    mode = "webhook" if settings.use_webhook else "polling"
    logger.info("starting_voice_bot", mode=mode)

    bot = create_bot()
    services: Services = create_services()
    dp = create_dispatcher(bot, services)

    try:
        if settings.use_webhook:
            asyncio.run(run_webhook(bot, dp))
        else:
            asyncio.run(run_polling(bot, dp))
    except KeyboardInterrupt:
        logger.info("bot_stopped_by_keyboard_interrupt")
    except Exception as exc:
        logger.error(
            "bot_stopped_with_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
