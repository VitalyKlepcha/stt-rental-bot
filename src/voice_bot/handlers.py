"""Telegram message handlers for the voice-to-PDF rental request bot.

Defines a module-level :data:`router` with handlers for:

- ``/start`` — welcome message
- ``/help`` — usage instructions
- Voice messages — full pipeline: download → transcribe → extract → PDF → send
- Non-voice fallback — prompts user to send a voice message

Services (transcription, extraction, PDF generator) are injected by aiogram
from ``workflow_data`` — the dispatcher must register them there.
"""

from __future__ import annotations

import asyncio
import time
from io import BytesIO

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message

from voice_bot.config import settings
from voice_bot.exceptions import (
    ExtractionError,
    PDFGenerationError,
    TranscriptionError,
)
from voice_bot.services.extraction import ExtractionService
from voice_bot.services.pdf_generator import PDFGeneratorService
from voice_bot.services.transcription import TranscriptionService
from voice_bot.services.usage_limit import UsageLimitService

logger = structlog.get_logger(__name__)

router = Router()

# --- User-facing messages (Russian) -------------------------------------------

_ACK_TEXT = "Обрабатываю ваше сообщение…"
_PROGRESS_INTERVAL_SEC = 5
_PROGRESS_MESSAGES = [
    "Скачиваю голосовое сообщение…",
    "Распознаю речь…",
    "Обрабатываю текст…",
    "Извлекаю данные из сообщения…",
    "Анализирую заявку…",
    "Создаю PDF документ…",
    "Формирую заявку на аренду…",
    "Почти готово, ещё немного…",
]
_EMPTY_TRANSCRIPT_TEXT = "Не удалось распознать речь в сообщении."
_EMPTY_DATA_TEXT = "Не удалось извлечь данные из сообщения."
_VOICE_DOWNLOAD_ERROR_TEXT = "Не удалось получить голосовое сообщение. Попробуйте ещё раз."
_TRANSCRIPTION_ERROR_TEXT = "Ошибка при расшифровке голосового сообщения."
_EXTRACTION_ERROR_TEXT = "Ошибка при обработке данных."
_PDF_ERROR_TEXT = "Ошибка при создании PDF документа."
_UNEXPECTED_ERROR_TEXT = "Произошла непредвиденная ошибка. Попробуйте позже."
_NON_VOICE_TEXT = (
    "Этот бот принимает только голосовые сообщения. "
    "Отправьте голосовое сообщение с вашей заявкой."
)
_WELCOME_TEXT = (
    "Здравствуйте! Отправьте голосовое сообщение с заявкой на аренду "
    "строительной техники, и я создам для вас PDF документ."
)
_HELP_TEXT = (
    "Как пользоваться ботом:\n\n"
    "1. Отправьте голосовое сообщение с заявкой на аренду техники.\n"
    "2. Укажите: наименование оборудования, количество, сроки аренды, "
    "адрес доставки, контактные данные.\n"
    "3. Бот обработает сообщение и отправит вам PDF-документ с заявкой.\n\n"
    "Пример: «Мне нужен экскаватор JCB 3CX на три дня, начиная с пятницы. "
    "Доставьте на стройку на Ленина 15. Мой телефон плюс семь девятьсот…»"
)

_USER_LIMIT_REACHED_TEXT = (
    f"Вы достигли лимита запросов (50 голосовых сообщений). "
    f"Чтобы увеличить лимит, напишите на {settings.support_email}"
)
_ADMIN_GLOBAL_LIMIT_TEXT = (
    "⚠️ Достигнут общий лимит запросов (5000). "
    "Бот временно недоступен для пользователей."
)

_GLOBAL_LIMIT_REACHED_TEXT = (
    f"Бот временно недоступен — общий лимит запросов исчерпан. "
    f"Напишите на {settings.support_email}, чтобы узнать о возобновлении работы."
)

_PDF_FILENAME = "zayavka_na_arendu.pdf"
_PDF_CAPTION = "Ваша заявка на аренду готова"


async def _update_progress(status_msg: Message, interval: int) -> None:
    """Edit the status message with rotating progress text every *interval* seconds.

    Runs as a background task alongside the main processing pipeline.
    Cycles through ``_PROGRESS_MESSAGES`` so the user sees the bot is alive.
    Silently stops when cancelled or when all messages have been shown.
    """
    for text in _PROGRESS_MESSAGES:
        await asyncio.sleep(interval)
        try:
            await status_msg.edit_text(text)
        except TelegramAPIError:
            break


# --- Handlers ------------------------------------------------------------------


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Send a welcome message when the user issues /start."""
    user_id = message.from_user.id if message.from_user else None
    logger.info("command_start", user_id=user_id)
    await message.answer(_WELCOME_TEXT)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Send usage instructions when the user issues /help."""
    user_id = message.from_user.id if message.from_user else None
    logger.info("command_help", user_id=user_id)
    await message.answer(_HELP_TEXT)


@router.message(F.voice)
async def handle_voice_message(
    message: Message,
    transcription_service: TranscriptionService,
    extraction_service: ExtractionService,
    pdf_generator: PDFGeneratorService,
    usage_limit_service: UsageLimitService,
) -> None:
    """Process a voice message through the full pipeline.

    Steps:
        1. Download the ``.ogg`` voice file from Telegram.
        2. Transcribe it via OpenAI Whisper.
        3. Extract structured data via GPT-4o-mini.
        4. Generate a PDF document via WeasyPrint.
        5. Send the PDF back to the user.

    Each step is wrapped in its own try/except so that the user receives
    a specific, friendly Russian error message matching the error-handling
    table in ``Overview.md``.
    """
    user_id = message.from_user.id if message.from_user else None
    voice = message.voice
    if voice is None:
        return

    start_time = time.monotonic()

    logger.info(
        "voice_message_received",
        user_id=user_id,
        duration_sec=voice.duration,
    )

    status_msg = await message.answer(_ACK_TEXT)

    progress_task = asyncio.create_task(
        _update_progress(status_msg, _PROGRESS_INTERVAL_SEC),
    )

    # --- Step 0: Check usage limits -------------------------------------------
    user_id_for_limit = message.from_user.id if message.from_user else 0
    usage_result = await usage_limit_service.check_and_increment(user_id_for_limit)
    if not usage_result.allowed:
        if usage_result.reason == "user_limit_reached":
            await message.answer(_USER_LIMIT_REACHED_TEXT)
        else:
            await message.answer(_GLOBAL_LIMIT_REACHED_TEXT)
            if settings.admin_user_id is not None:
                try:
                    await message.bot.send_message(
                        settings.admin_user_id,
                        _ADMIN_GLOBAL_LIMIT_TEXT,
                    )
                except TelegramAPIError:
                    logger.warning(
                        "admin_notification_failed",
                        admin_user_id=settings.admin_user_id,
                    )
        progress_task.cancel()
        return

    # --- Step 1: Download voice file ------------------------------------------
    try:
        file = await message.bot.get_file(voice.file_id)
        buffer = BytesIO()
        await message.bot.download_file(file.file_path, destination=buffer)
        audio_bytes = buffer.getvalue()
    except (TelegramAPIError, TelegramNetworkError) as exc:
        logger.error(
            "voice_download_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_VOICE_DOWNLOAD_ERROR_TEXT)
        progress_task.cancel()
        return
    except Exception as exc:
        logger.error(
            "voice_download_unexpected_error",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_VOICE_DOWNLOAD_ERROR_TEXT)
        progress_task.cancel()
        return

    logger.debug(
        "voice_downloaded",
        user_id=user_id,
        audio_size=len(audio_bytes),
        elapsed_sec=round(time.monotonic() - start_time, 2),
    )

    # --- Step 2: Transcribe ---------------------------------------------------
    try:
        transcript = await transcription_service.transcribe(audio_bytes)
    except TranscriptionError as exc:
        logger.error(
            "transcription_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_TRANSCRIPTION_ERROR_TEXT)
        progress_task.cancel()
        return
    except Exception as exc:
        logger.error(
            "transcription_unexpected_error",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_TRANSCRIPTION_ERROR_TEXT)
        progress_task.cancel()
        return

    if not transcript or not transcript.strip():
        logger.warning("empty_transcript", user_id=user_id)
        await message.answer(_EMPTY_TRANSCRIPT_TEXT)
        progress_task.cancel()
        return

    logger.debug(
        "transcription_done",
        user_id=user_id,
        transcript_length=len(transcript),
        elapsed_sec=round(time.monotonic() - start_time, 2),
    )

    # --- Step 3: Extract entities ---------------------------------------------
    try:
        rental_data = await extraction_service.extract(transcript)
    except ExtractionError as exc:
        logger.error(
            "extraction_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_EXTRACTION_ERROR_TEXT)
        progress_task.cancel()
        return
    except Exception as exc:
        logger.error(
            "extraction_unexpected_error",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_EXTRACTION_ERROR_TEXT)
        progress_task.cancel()
        return

    if rental_data.is_empty():
        logger.warning("empty_extraction_result", user_id=user_id)
        await message.answer(_EMPTY_DATA_TEXT)
        progress_task.cancel()
        return

    logger.debug(
        "extraction_done",
        user_id=user_id,
        client_name=rental_data.client_name,
        equipment_count=len(rental_data.equipment),
        urgency=rental_data.urgency,
        elapsed_sec=round(time.monotonic() - start_time, 2),
    )

    # --- Step 4: Generate PDF -------------------------------------------------
    try:
        pdf_bytes = await asyncio.to_thread(pdf_generator.generate, rental_data)
    except PDFGenerationError as exc:
        logger.error(
            "pdf_generation_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_PDF_ERROR_TEXT)
        progress_task.cancel()
        return
    except Exception as exc:
        logger.error(
            "pdf_generation_unexpected_error",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_PDF_ERROR_TEXT)
        progress_task.cancel()
        return

    logger.debug(
        "pdf_generated",
        user_id=user_id,
        pdf_size=len(pdf_bytes),
        elapsed_sec=round(time.monotonic() - start_time, 2),
    )

    progress_task.cancel()

    # --- Step 5: Send PDF to user ---------------------------------------------
    try:
        await status_msg.delete()
        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename=_PDF_FILENAME),
            caption=_PDF_CAPTION,
        )
    except (TelegramAPIError, TelegramNetworkError) as exc:
        logger.error(
            "pdf_send_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(_UNEXPECTED_ERROR_TEXT)
        return

    logger.info(
        "voice_message_processed",
        user_id=user_id,
        total_elapsed_sec=round(time.monotonic() - start_time, 2),
        pdf_size=len(pdf_bytes),
    )


@router.message(~F.voice)
async def handle_non_voice(message: Message) -> None:
    """Catch-all for non-voice messages — prompt the user to send voice."""
    user_id = message.from_user.id if message.from_user else None
    logger.debug("non_voice_message", user_id=user_id)
    await message.answer(_NON_VOICE_TEXT)
