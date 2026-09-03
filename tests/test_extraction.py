"""Unit tests for the GPT-4o-mini entity extraction service.

All OpenAI API calls are mocked — no real network requests are made.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from voice_bot.exceptions import ExtractionError
from voice_bot.models import RentalRequestData
from voice_bot.prompts import SYSTEM_PROMPT_TEMPLATE
from voice_bot.services.extraction import ExtractionService


# --- Helpers ------------------------------------------------------------------


def _make_service(mock_openai_client: AsyncMock) -> ExtractionService:
    """Create an ExtractionService with the mock client pre-injected."""
    service = ExtractionService(api_key="test-api-key")
    service._client = mock_openai_client
    return service


def _set_parsed(mock_openai_client: AsyncMock, parsed: object) -> None:
    """Configure the mock client's parse return value with the given parsed object."""
    mock_choice = MagicMock()
    mock_choice.message.parsed = parsed
    mock_choice.finish_reason = "stop"
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_openai_client.chat.completions.parse = AsyncMock(return_value=mock_completion)


# --- Success tests ------------------------------------------------------------


async def test_extract_success(
    mock_openai_client: AsyncMock,
    sample_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """A well-formed API response returns the parsed RentalRequestData."""
    _set_parsed(mock_openai_client, sample_rental_data)
    service = _make_service(mock_openai_client)

    result = await service.extract(sample_transcript)

    assert result is sample_rental_data
    assert result.client_name == "ООО СтройМонтаж"
    assert result.urgency == "urgent"
    assert len(result.equipment) == 2


async def test_extract_success_empty_data(
    mock_openai_client: AsyncMock,
    empty_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """When the model returns all-default fields, the empty model is returned as-is."""
    _set_parsed(mock_openai_client, empty_rental_data)
    service = _make_service(mock_openai_client)

    result = await service.extract(sample_transcript)

    assert result is empty_rental_data
    assert result.is_empty()


# --- Error: parsed is None ----------------------------------------------------


async def test_extract_returns_none(
    mock_openai_client: AsyncMock,
    sample_transcript: str,
) -> None:
    """When the model returns parsed=None, ExtractionError is raised."""
    _set_parsed(mock_openai_client, None)
    service = _make_service(mock_openai_client)

    with pytest.raises(ExtractionError, match="no parsed data"):
        await service.extract(sample_transcript)


# --- Error: API errors --------------------------------------------------------


async def test_extract_api_error(
    mock_openai_client: AsyncMock,
    sample_transcript: str,
) -> None:
    """When the OpenAI SDK raises APIError, ExtractionError is raised."""
    mock_openai_client.chat.completions.parse = AsyncMock(
        side_effect=openai.APIError(
            message="Internal server error",
            request=MagicMock(),
            body=None,
        ),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(ExtractionError, match="API call failed"):
        await service.extract(sample_transcript)


async def test_extract_generic_exception(
    mock_openai_client: AsyncMock,
    sample_transcript: str,
) -> None:
    """Non-OpenAI exceptions (e.g. network) are also wrapped in ExtractionError."""
    mock_openai_client.chat.completions.parse = AsyncMock(
        side_effect=ConnectionError("DNS resolution failed"),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(ExtractionError, match="Network error"):
        await service.extract(sample_transcript)


async def test_extract_rate_limit_error(
    mock_openai_client: AsyncMock,
    sample_transcript: str,
) -> None:
    """RateLimitError (subclass of OpenAIError) is wrapped in ExtractionError."""
    mock_openai_client.chat.completions.parse = AsyncMock(
        side_effect=openai.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(),
            body=None,
        ),
    )
    service = _make_service(mock_openai_client)

    with pytest.raises(ExtractionError):
        await service.extract(sample_transcript)


# --- Error: input validation --------------------------------------------------


async def test_extract_empty_transcript_raises(
    mock_openai_client: AsyncMock,
) -> None:
    """An empty transcript raises ExtractionError before any API call."""
    service = _make_service(mock_openai_client)

    with pytest.raises(ExtractionError, match="empty"):
        await service.extract("")

    mock_openai_client.chat.completions.parse.assert_not_called()


async def test_extract_whitespace_only_transcript_raises(
    mock_openai_client: AsyncMock,
) -> None:
    """A whitespace-only transcript is treated as empty."""
    service = _make_service(mock_openai_client)

    with pytest.raises(ExtractionError, match="empty"):
        await service.extract("   \n\t  ")

    mock_openai_client.chat.completions.parse.assert_not_called()


async def test_extract_transcript_too_long_raises(
    mock_openai_client: AsyncMock,
) -> None:
    """A transcript exceeding the character limit raises ExtractionError."""
    service = _make_service(mock_openai_client)
    long_transcript = "а" * 20_000

    with pytest.raises(ExtractionError, match="too long"):
        await service.extract(long_transcript)

    mock_openai_client.chat.completions.parse.assert_not_called()


# --- Parameter verification tests ---------------------------------------------


async def test_extract_passes_system_prompt(
    mock_openai_client: AsyncMock,
    sample_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """The SYSTEM_PROMPT_TEMPLATE is sent as the first system-role message."""
    _set_parsed(mock_openai_client, sample_rental_data)
    service = _make_service(mock_openai_client)

    await service.extract(sample_transcript)

    call_kwargs = mock_openai_client.chat.completions.parse.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT_TEMPLATE.format(
        today=date.today().isoformat(),
    )


async def test_extract_passes_user_transcript(
    mock_openai_client: AsyncMock,
    sample_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """The transcript is sent as the user-role message."""
    _set_parsed(mock_openai_client, sample_rental_data)
    service = _make_service(mock_openai_client)

    await service.extract(sample_transcript)

    call_kwargs = mock_openai_client.chat.completions.parse.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == sample_transcript


async def test_extract_passes_gpt4o_mini_model(
    mock_openai_client: AsyncMock,
    sample_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """The model parameter is set to 'gpt-4o-mini'."""
    _set_parsed(mock_openai_client, sample_rental_data)
    service = _make_service(mock_openai_client)

    await service.extract(sample_transcript)

    call_kwargs = mock_openai_client.chat.completions.parse.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"


async def test_extract_passes_temperature_zero(
    mock_openai_client: AsyncMock,
    sample_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """The temperature parameter is set to 0 for deterministic output."""
    _set_parsed(mock_openai_client, sample_rental_data)
    service = _make_service(mock_openai_client)

    await service.extract(sample_transcript)

    call_kwargs = mock_openai_client.chat.completions.parse.call_args.kwargs
    assert call_kwargs["temperature"] == 0


async def test_extract_passes_response_format(
    mock_openai_client: AsyncMock,
    sample_rental_data: RentalRequestData,
    sample_transcript: str,
) -> None:
    """The response_format parameter is set to RentalRequestData."""
    _set_parsed(mock_openai_client, sample_rental_data)
    service = _make_service(mock_openai_client)

    await service.extract(sample_transcript)

    call_kwargs = mock_openai_client.chat.completions.parse.call_args.kwargs
    assert call_kwargs["response_format"] is RentalRequestData


# --- Close --------------------------------------------------------------------


async def test_close_releases_client(mock_openai_client: AsyncMock) -> None:
    """close() calls the underlying client's close and resets the reference."""
    service = _make_service(mock_openai_client)

    await service.close()

    mock_openai_client.close.assert_awaited_once()
    assert service._client is None


async def test_close_without_client() -> None:
    """close() is safe to call when no client was ever created."""
    service = ExtractionService(api_key="test-api-key")

    await service.close()

    assert service._client is None
