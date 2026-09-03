"""Unit tests for the OpenAI Whisper transcription service.

All OpenAI API calls are mocked — no real network requests are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from voice_bot.exceptions import TranscriptionError
from voice_bot.services.transcription import (
    TranscriptionService,
    create_transcription_service,
)


# --- Helpers ------------------------------------------------------------------


def _make_service(mock_openai_client: AsyncMock) -> TranscriptionService:
    """Create a TranscriptionService with the mock client pre-injected."""
    service = TranscriptionService(api_key="test-api-key")
    service._client = mock_openai_client
    return service


# --- Success tests ------------------------------------------------------------


async def test_transcribe_success(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """A well-formed API response returns the transcribed text."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        return_value="Распознанный текст",
    )
    service = _make_service(mock_openai_client)

    result = await service.transcribe(sample_audio_bytes)

    assert result == "Распознанный текст"


async def test_transcribe_strips_whitespace(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """Leading/trailing whitespace in the API response is stripped."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        return_value="  текст с пробелами  \n",
    )
    service = _make_service(mock_openai_client)

    result = await service.transcribe(sample_audio_bytes)

    assert result == "текст с пробелами"


# --- Empty / edge-case response tests -----------------------------------------


async def test_transcribe_empty_response_returns_empty_string(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """When the API returns an empty string, an empty string is returned."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(return_value="")
    service = _make_service(mock_openai_client)

    result = await service.transcribe(sample_audio_bytes)

    assert result == ""


async def test_transcribe_empty_bytes_raises(
    mock_openai_client: AsyncMock,
) -> None:
    """Empty audio bytes raise TranscriptionError before any API call."""
    service = _make_service(mock_openai_client)

    with pytest.raises(TranscriptionError, match="empty"):
        await service.transcribe(b"")

    mock_openai_client.audio.transcriptions.create.assert_not_called()


async def test_transcribe_audio_too_large_raises(
    mock_openai_client: AsyncMock,
) -> None:
    """Audio exceeding the 25 MB Whisper limit raises TranscriptionError."""
    service = _make_service(mock_openai_client)
    oversized = b"\x00" * (25 * 1024 * 1024 + 1)

    with pytest.raises(TranscriptionError, match="too large"):
        await service.transcribe(oversized)

    mock_openai_client.audio.transcriptions.create.assert_not_called()


# --- Error: API errors --------------------------------------------------------


async def test_transcribe_api_error(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """When the OpenAI SDK raises APIError, TranscriptionError is raised."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        side_effect=openai.APIError(
            message="Internal server error",
            request=MagicMock(),
            body=None,
        ),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(TranscriptionError, match="Whisper API call failed"):
        await service.transcribe(sample_audio_bytes)


async def test_transcribe_timeout(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """When httpx raises a TimeoutException, TranscriptionError is raised."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out"),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(TranscriptionError, match="Network error"):
        await service.transcribe(sample_audio_bytes)


async def test_transcribe_generic_exception(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """Non-OpenAI exceptions (e.g. connection errors) are wrapped in TranscriptionError."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        side_effect=ConnectionError("DNS resolution failed"),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(TranscriptionError, match="Network error"):
        await service.transcribe(sample_audio_bytes)


async def test_transcribe_rate_limit_error(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """RateLimitError (subclass of OpenAIError) is wrapped in TranscriptionError."""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        side_effect=openai.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(),
            body=None,
        ),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(TranscriptionError):
        await service.transcribe(sample_audio_bytes)


# --- Parameter verification tests ---------------------------------------------


async def test_transcribe_passes_language_ru(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """The language parameter is set to 'ru' for Russian transcription."""
    service = _make_service(mock_openai_client)

    await service.transcribe(sample_audio_bytes)

    call_kwargs = mock_openai_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["language"] == "ru"


async def test_transcribe_passes_whisper_model(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """The model parameter is set to 'whisper-1'."""
    service = _make_service(mock_openai_client)

    await service.transcribe(sample_audio_bytes)

    call_kwargs = mock_openai_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-1"


async def test_transcribe_passes_response_format_text(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """The response_format parameter is set to 'text'."""
    service = _make_service(mock_openai_client)

    await service.transcribe(sample_audio_bytes)

    call_kwargs = mock_openai_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["response_format"] == "text"


async def test_transcribe_passes_filename(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """The filename is forwarded to the API as the file tuple's first element."""
    service = _make_service(mock_openai_client)

    await service.transcribe(sample_audio_bytes, filename="custom.ogg")

    call_args = mock_openai_client.audio.transcriptions.create.call_args
    file_tuple = call_args.kwargs["file"]
    assert file_tuple[0] == "custom.ogg"


async def test_transcribe_default_filename(
    mock_openai_client: AsyncMock,
    sample_audio_bytes: bytes,
) -> None:
    """The default filename is 'voice.ogg'."""
    service = _make_service(mock_openai_client)

    await service.transcribe(sample_audio_bytes)

    call_args = mock_openai_client.audio.transcriptions.create.call_args
    file_tuple = call_args.kwargs["file"]
    assert file_tuple[0] == "voice.ogg"


# --- Factory function ---------------------------------------------------------


def test_create_transcription_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """The factory creates a TranscriptionService using settings.openai_api_key."""
    from voice_bot.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "factory-test-key")

    service = create_transcription_service()

    assert isinstance(service, TranscriptionService)
    assert service._api_key == "factory-test-key"


# --- Close --------------------------------------------------------------------


async def test_close_releases_client(mock_openai_client: AsyncMock) -> None:
    """close() calls the underlying client's close and resets the reference."""
    service = _make_service(mock_openai_client)

    await service.close()

    mock_openai_client.close.assert_awaited_once()
    assert service._client is None


async def test_close_without_client() -> None:
    """close() is safe to call when no client was ever created."""
    service = TranscriptionService(api_key="test-api-key")

    await service.close()

    assert service._client is None
