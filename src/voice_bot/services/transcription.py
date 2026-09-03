"""OpenAI Whisper API client for transcribing voice messages to text."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import openai
import structlog

from voice_bot.config import settings
from voice_bot.exceptions import TranscriptionError

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = structlog.get_logger(__name__)

_WHISPER_MODEL = "whisper-1"
_WHISPER_LANGUAGE = "ru"
_WHISPER_RESPONSE_FORMAT = "text"
_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # OpenAI Whisper API limit: 25 MB


class TranscriptionService:
    """Async client for the OpenAI Whisper speech-to-text API.

    The underlying ``AsyncOpenAI`` client is created lazily on the first
    ``transcribe`` call so that constructing the service never performs I/O.
    """

    def __init__(self, api_key: str) -> None:
        """Store the API key; the client is created on first use.

        Parameters:
            api_key: OpenAI API key used for authentication.
        """
        self._api_key = api_key
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Return the lazy ``AsyncOpenAI`` instance, creating it if needed."""
        if self._client is None:
            self._client = openai.AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        """Transcribe audio bytes via the Whisper API.

        Parameters:
            audio_bytes: Raw audio data (e.g. OGG/Opus from Telegram).
            filename: Filename hint for the API (used for format detection).

        Returns:
            The transcribed text as a string.

        Raises:
            TranscriptionError: If the audio is empty, too large, or the
                API call fails for any reason.
        """
        if not audio_bytes:
            raise TranscriptionError("Audio bytes are empty — nothing to transcribe")

        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise TranscriptionError(
                f"Audio file too large: {len(audio_bytes)} bytes "
                f"(limit: {_MAX_AUDIO_BYTES} bytes)"
            )

        client = self._get_client()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        logger.debug(
            "whisper_request_start",
            filename=filename,
            audio_size=len(audio_bytes),
        )

        try:
            response: str = await client.audio.transcriptions.create(
                file=(filename, audio_file),
                model=_WHISPER_MODEL,
                language=_WHISPER_LANGUAGE,
                response_format=_WHISPER_RESPONSE_FORMAT,
            )
        except openai.OpenAIError as exc:
            logger.error(
                "whisper_request_failed",
                filename=filename,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise TranscriptionError(
                f"Whisper API call failed: {exc}",
                cause=exc,
            ) from exc
        except Exception as exc:
            logger.error(
                "whisper_network_error",
                filename=filename,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise TranscriptionError(
                f"Network error during transcription: {exc}",
                cause=exc,
            ) from exc

        text = response.strip() if isinstance(response, str) else str(response).strip()

        logger.info(
            "whisper_request_success",
            filename=filename,
            text_length=len(text),
        )

        return text

    async def close(self) -> None:
        """Close the underlying OpenAI client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.debug("whisper_client_closed")


def create_transcription_service() -> TranscriptionService:
    """Create a ``TranscriptionService`` using the application's OpenAI API key."""
    return TranscriptionService(api_key=settings.openai_api_key)
