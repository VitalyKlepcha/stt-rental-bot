"""OpenAI GPT-4o-mini structured-output client for entity extraction.

Sends a transcribed voice message to GPT-4o-mini with a system prompt and a
Pydantic ``response_format`` so the model returns a validated
:class:`~voice_bot.models.RentalRequestData` instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import openai
import structlog

from voice_bot.config import settings
from voice_bot.exceptions import ExtractionError
from voice_bot.models import RentalRequestData
from voice_bot.prompts import SYSTEM_PROMPT

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = structlog.get_logger(__name__)

_GPT_MODEL = "gpt-4o-mini"
_GPT_TEMPERATURE = 0
_MAX_TRANSCRIPT_CHARS = 15_000  # keep prompt well within token limits
_TRANSCRIPT_PREVIEW_LEN = 120


class ExtractionService:
    """Async client for GPT-4o-mini structured entity extraction.

    The underlying ``AsyncOpenAI`` client is created lazily on the first
    ``extract`` call so that constructing the service never performs I/O.
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

    async def extract(self, transcript: str) -> RentalRequestData:
        """Extract structured rental-request data from a transcript.

        Parameters:
            transcript: Text produced by the Whisper transcription service.

        Returns:
            A validated :class:`RentalRequestData` instance.

        Raises:
            ExtractionError: If the transcript is empty, too long, the API
                call fails, or the model returns no parseable data.
        """
        if not transcript or not transcript.strip():
            raise ExtractionError("Transcript is empty — nothing to extract")

        if len(transcript) > _MAX_TRANSCRIPT_CHARS:
            raise ExtractionError(
                f"Transcript too long: {len(transcript)} chars "
                f"(limit: {_MAX_TRANSCRIPT_CHARS} chars)"
            )

        client = self._get_client()

        preview = transcript[:_TRANSCRIPT_PREVIEW_LEN]
        if len(transcript) > _TRANSCRIPT_PREVIEW_LEN:
            preview += "…"

        logger.debug(
            "extraction_request_start",
            transcript_length=len(transcript),
            transcript_preview=preview,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ]

        try:
            completion = await client.chat.completions.parse(
                model=_GPT_MODEL,
                messages=messages,
                temperature=_GPT_TEMPERATURE,
                response_format=RentalRequestData,
            )
        except openai.OpenAIError as exc:
            logger.error(
                "extraction_request_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise ExtractionError(
                f"GPT-4o-mini API call failed: {exc}",
                cause=exc,
            ) from exc
        except Exception as exc:
            logger.error(
                "extraction_network_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise ExtractionError(
                f"Network error during extraction: {exc}",
                cause=exc,
            ) from exc

        parsed = completion.choices[0].message.parsed

        if parsed is None:
            logger.error(
                "extraction_no_parsed_data",
                finish_reason=completion.choices[0].finish_reason,
            )
            raise ExtractionError("GPT-4o-mini returned no parsed data")

        logger.info(
            "extraction_request_success",
            client_name=parsed.client_name,
            equipment_count=len(parsed.equipment),
            urgency=parsed.urgency,
            has_phone=parsed.contact_phone is not None,
            has_address=parsed.delivery_address is not None,
        )

        return parsed

    async def close(self) -> None:
        """Close the underlying OpenAI client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.debug("extraction_client_closed")


def create_extraction_service() -> ExtractionService:
    """Create an ``ExtractionService`` using the application's OpenAI API key."""
    return ExtractionService(api_key=settings.openai_api_key)
