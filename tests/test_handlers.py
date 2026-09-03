"""Unit tests for Telegram message handlers."""

from __future__ import annotations

import sys
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest

# WeasyPrint native deps (Pango/GTK) are unavailable on Windows — mock before import.
if "weasyprint" not in sys.modules:
    _wp_mock = MagicMock()
    _wp_mock.HTML = MagicMock()
    sys.modules["weasyprint"] = _wp_mock

from voice_bot.exceptions import (
    ExtractionError,
    PDFGenerationError,
    TranscriptionError,
)
from voice_bot.handlers import (
    _ACK_TEXT,
    _EMPTY_DATA_TEXT,
    _EMPTY_TRANSCRIPT_TEXT,
    _EXTRACTION_ERROR_TEXT,
    _HELP_TEXT,
    _NON_VOICE_TEXT,
    _PDF_CAPTION,
    _PDF_ERROR_TEXT,
    _TRANSCRIPTION_ERROR_TEXT,
    _VOICE_DOWNLOAD_ERROR_TEXT,
    _WELCOME_TEXT,
    handle_help,
    handle_non_voice,
    handle_start,
    handle_voice_message,
)
from voice_bot.models import RentalRequestData


# --- Local fixtures -----------------------------------------------------------


@pytest.fixture
def mock_pdf_generator() -> MagicMock:
    """Return a MagicMock simulating PDFGeneratorService (sync generate)."""
    gen = MagicMock()
    gen.generate = MagicMock(return_value=b"%PDF-1.4 fake pdf bytes")
    return gen


@pytest.fixture
def configured_message(
    mock_message: MagicMock,
    sample_audio_bytes: bytes,
) -> MagicMock:
    """Return mock_message with bot.get_file and bot.download_file configured for success."""
    file_obj = MagicMock()
    file_obj.file_path = "voice/test_file.ogg"
    mock_message.bot.get_file.return_value = file_obj

    async def fake_download(file_path: str, destination: BytesIO | None = None) -> None:
        if destination is not None:
            destination.write(sample_audio_bytes)

    mock_message.bot.download_file.side_effect = fake_download
    return mock_message


# --- /start command -----------------------------------------------------------


async def test_handle_start(mock_message: MagicMock) -> None:
    """Test that /start sends the welcome message."""
    await handle_start(mock_message)
    mock_message.answer.assert_called_once_with(_WELCOME_TEXT)


# --- /help command -----------------------------------------------------------


async def test_handle_help(mock_message: MagicMock) -> None:
    """Test that /help sends the help text."""
    await handle_help(mock_message)
    mock_message.answer.assert_called_once_with(_HELP_TEXT)


# --- Non-voice fallback ------------------------------------------------------


async def test_handle_non_voice(mock_message_no_voice: MagicMock) -> None:
    """Test that non-voice messages get the 'only voice' prompt."""
    await handle_non_voice(mock_message_no_voice)
    mock_message_no_voice.answer.assert_called_once_with(_NON_VOICE_TEXT)


# --- Full voice message flow -------------------------------------------------


async def test_handle_voice_full_flow(
    configured_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
    sample_audio_bytes: bytes,
    sample_rental_data: RentalRequestData,
) -> None:
    """Test the full voice pipeline: ack -> download -> transcribe -> extract -> PDF -> send."""
    await handle_voice_message(
        configured_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    # Acknowledgment sent
    configured_message.answer.assert_any_call(_ACK_TEXT)

    # bot.get_file called with voice file_id
    configured_message.bot.get_file.assert_called_once_with("test_file_id_123")

    # bot.download_file called
    configured_message.bot.download_file.assert_called_once()

    # Transcription called with downloaded audio bytes
    mock_transcription_service.transcribe.assert_called_once_with(sample_audio_bytes)

    # Extraction called with transcript text
    mock_extraction_service.extract.assert_called_once_with("Распознанный текст")

    # PDF generation called with extracted RentalRequestData
    mock_pdf_generator.generate.assert_called_once_with(sample_rental_data)

    # PDF sent back to user with correct caption
    configured_message.answer_document.assert_called_once()
    call_kwargs = configured_message.answer_document.call_args.kwargs
    assert call_kwargs["caption"] == _PDF_CAPTION


# --- Transcription error -----------------------------------------------------


async def test_handle_voice_transcription_error(
    configured_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
) -> None:
    """Test that TranscriptionError sends error message and no PDF."""
    mock_transcription_service.transcribe.side_effect = TranscriptionError("API failed")

    await handle_voice_message(
        configured_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    configured_message.answer.assert_any_call(_TRANSCRIPTION_ERROR_TEXT)
    configured_message.answer_document.assert_not_called()
    mock_extraction_service.extract.assert_not_called()
    mock_pdf_generator.generate.assert_not_called()


# --- Extraction error --------------------------------------------------------


async def test_handle_voice_extraction_error(
    configured_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
) -> None:
    """Test that ExtractionError sends error message and no PDF."""
    mock_extraction_service.extract.side_effect = ExtractionError("API failed")

    await handle_voice_message(
        configured_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    configured_message.answer.assert_any_call(_EXTRACTION_ERROR_TEXT)
    configured_message.answer_document.assert_not_called()
    mock_pdf_generator.generate.assert_not_called()


# --- PDF generation error ----------------------------------------------------


async def test_handle_voice_pdf_error(
    configured_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
) -> None:
    """Test that PDFGenerationError sends error message and no PDF."""
    mock_pdf_generator.generate.side_effect = PDFGenerationError("WeasyPrint failed")

    await handle_voice_message(
        configured_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    configured_message.answer.assert_any_call(_PDF_ERROR_TEXT)
    configured_message.answer_document.assert_not_called()


# --- Empty transcript --------------------------------------------------------


async def test_handle_voice_empty_transcript(
    configured_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
) -> None:
    """Test that empty transcript sends 'Не удалось распознать речь' message."""
    mock_transcription_service.transcribe.return_value = ""

    await handle_voice_message(
        configured_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    configured_message.answer.assert_any_call(_EMPTY_TRANSCRIPT_TEXT)
    mock_extraction_service.extract.assert_not_called()
    mock_pdf_generator.generate.assert_not_called()
    configured_message.answer_document.assert_not_called()


# --- Voice download error (edge case) ----------------------------------------


async def test_handle_voice_download_error(
    mock_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
) -> None:
    """Test that download failure sends download error message and no PDF."""
    mock_message.bot.get_file.side_effect = RuntimeError("network error")

    await handle_voice_message(
        mock_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    mock_message.answer.assert_any_call(_VOICE_DOWNLOAD_ERROR_TEXT)
    mock_transcription_service.transcribe.assert_not_called()
    mock_message.answer_document.assert_not_called()


# --- Empty extraction result (edge case) -------------------------------------


async def test_handle_voice_empty_extraction_result(
    configured_message: MagicMock,
    mock_transcription_service: AsyncMock,
    mock_extraction_service: AsyncMock,
    mock_pdf_generator: MagicMock,
    empty_rental_data: RentalRequestData,
) -> None:
    """Test that empty RentalRequestData sends 'Не удалось извлечь данные' message."""
    mock_extraction_service.extract.return_value = empty_rental_data

    await handle_voice_message(
        configured_message,
        mock_transcription_service,
        mock_extraction_service,
        mock_pdf_generator,
    )

    configured_message.answer.assert_any_call(_EMPTY_DATA_TEXT)
    mock_pdf_generator.generate.assert_not_called()
    configured_message.answer_document.assert_not_called()
