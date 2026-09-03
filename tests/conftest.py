"""Shared pytest fixtures for the voice-to-PDF bot test suite."""

from __future__ import annotations

import os

# Set test env vars before any voice_bot imports so that config.py's
# module-level settings = get_settings() succeeds during collection.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test_token")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("ALLOWED_USER_IDS", "111111111,222222222")

from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from voice_bot.models import EquipmentItem, RentalRequestData


# --- Settings / env vars -------------------------------------------------------


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set test environment variables and return them as a dict.

    Uses monkeypatch so env vars are automatically restored after the test.
    """
    env: dict[str, str] = {
        "TELEGRAM_BOT_TOKEN": "123456:test_token",
        "OPENAI_API_KEY": "test-openai-key",
        "ALLOWED_USER_IDS": "111111111,222222222",
        "USE_WEBHOOK": "false",
        "LOG_LEVEL": "DEBUG",
        "PORT": "8080",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture
def allowed_user_ids() -> list[int]:
    """Return the list of allowed user IDs used in tests."""
    return [111111111, 222222222]


# --- Sample data ---------------------------------------------------------------


@pytest.fixture
def sample_rental_data() -> RentalRequestData:
    """Return a fully populated RentalRequestData for PDF and extraction tests."""
    return RentalRequestData(
        client_name="ООО СтройМонтаж",
        contact_phone="+79001234567",
        equipment=[
            EquipmentItem(name="Экскаватор JCB 3CX", quantity=2),
            EquipmentItem(name="Самосвал КамАЗ 6520", quantity=1),
        ],
        rental_start_date="2025-09-10",
        rental_end_date="2025-09-17",
        rental_duration_days=7,
        delivery_address="г. Москва, ул. Строителей, д. 15",
        preferred_delivery_time="09:00",
        special_requirements="Требуется_operator_с_допуском",
        urgency="urgent",
    )


@pytest.fixture
def empty_rental_data() -> RentalRequestData:
    """Return a RentalRequestData with all fields at their defaults."""
    return RentalRequestData()


@pytest.fixture
def sample_transcript() -> str:
    """Return a realistic Russian transcript simulating Whisper output."""
    return (
        "Здравствуйте, мне нужно арендовать два экскаватора JCB 3CX "
        "и один самосвал КамАЗ 6520. Срок аренды — одна недера, "
        "с десятого сентября по семнадцатое. "
        "Адрес доставки: Москва, улица Строителей, дом пятнадцать. "
        "Привезти к девяти утра. "
        "Мой телефон плюс семь девятьсот двенадцать тридцать четыре пятьдесят шесть семь. "
        "Организация ООО СтройМонтаж. "
        "Это срочно, нужен оператор с допуском."
    )


# --- Mock OpenAI client --------------------------------------------------------


@pytest.fixture
def mock_openai_client() -> AsyncMock:
    """Return an AsyncMock simulating AsyncOpenAI for transcription/extraction tests.

    The mock supports:
    - ``client.audio.transcriptions.create`` → returns a string (Whisper text)
    - ``client.chat.completions.parse`` → returns an object with
      ``choices[0].message.parsed``
    - ``client.close`` → coroutine
    """
    client = AsyncMock()

    # Whisper transcription: returns plain text when response_format="text"
    client.audio.transcriptions.create = AsyncMock(return_value="Распознанный текст")

    # GPT-4o-mini structured output: returns a choice with .message.parsed
    mock_choice = MagicMock()
    mock_choice.message.parsed = None  # tests override this as needed
    mock_choice.finish_reason = "stop"
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    client.chat.completions.parse = AsyncMock(return_value=mock_completion)

    client.close = AsyncMock()

    return client


# --- Mock Telegram objects -----------------------------------------------------


@pytest.fixture
def mock_bot() -> AsyncMock:
    """Return an AsyncMock simulating aiogram.Bot for handler tests."""
    bot = AsyncMock()
    bot.get_file = AsyncMock()
    bot.download_file = AsyncMock()
    return bot


@pytest.fixture
def mock_voice() -> MagicMock:
    """Return a MagicMock simulating a Voice object."""
    voice = MagicMock()
    voice.file_id = "test_file_id_123"
    voice.duration = 15
    return voice


@pytest.fixture
def mock_message(mock_bot: AsyncMock, mock_voice: MagicMock) -> MagicMock:
    """Return a MagicMock simulating aiogram.types.Message for handler tests.

    Includes:
    - ``message.voice`` — a Voice-like mock
    - ``message.answer`` — AsyncMock
    - ``message.answer_document`` — AsyncMock
    - ``message.bot`` — mock bot
    - ``message.from_user`` — a User-like mock with id and username
    """
    message = MagicMock()
    message.voice = mock_voice
    message.answer = AsyncMock()
    message.answer_document = AsyncMock()
    message.bot = mock_bot

    from_user = MagicMock()
    from_user.id = 111111111
    from_user.username = "test_user"
    message.from_user = from_user

    return message


@pytest.fixture
def mock_message_no_voice(mock_bot: AsyncMock) -> MagicMock:
    """Return a MagicMock simulating a Message without a voice attribute set."""
    message = MagicMock()
    message.voice = None
    message.answer = AsyncMock()
    message.answer_document = AsyncMock()
    message.bot = mock_bot

    from_user = MagicMock()
    from_user.id = 111111111
    from_user.username = "test_user"
    message.from_user = from_user

    return message


# --- Mock services -------------------------------------------------------------


@pytest.fixture
def mock_transcription_service() -> AsyncMock:
    """Return an AsyncMock simulating TranscriptionService."""
    service = AsyncMock()
    service.transcribe = AsyncMock(return_value="Распознанный текст")
    service.close = AsyncMock()
    return service


@pytest.fixture
def mock_extraction_service(sample_rental_data: RentalRequestData) -> AsyncMock:
    """Return an AsyncMock simulating ExtractionService.

    By default, ``extract`` returns the sample_rental_data fixture.
    """
    service = AsyncMock()
    service.extract = AsyncMock(return_value=sample_rental_data)
    service.close = AsyncMock()
    return service


# --- Real PDF generator --------------------------------------------------------


@pytest.fixture
def pdf_generator():
    """Return a real PDFGeneratorService instance (WeasyPrint is local)."""
    from voice_bot.services.pdf_generator import PDFGeneratorService

    return PDFGeneratorService()


# --- Audio bytes ---------------------------------------------------------------


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """Return dummy audio bytes simulating a downloaded .ogg voice file."""
    return b"\x4f\x67\x67\x53\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
