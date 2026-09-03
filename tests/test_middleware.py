"""Unit tests for the access control middleware."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from voice_bot.middleware import AccessControlMiddleware

_DENIAL_TEXT = "У вас нет доступа к этому боту."


# --- Fixtures -------------------------------------------------------------------


@pytest.fixture
def middleware(allowed_user_ids: list[int]) -> AccessControlMiddleware:
    """Return an AccessControlMiddleware configured with the conftest whitelist."""
    return AccessControlMiddleware(allowed_user_ids)


@pytest.fixture
def mock_handler() -> AsyncMock:
    """Return an AsyncMock simulating the next handler in the middleware chain."""
    return AsyncMock(return_value="handler_result")


# --- Helpers --------------------------------------------------------------------


def _make_message(user_id: int, username: str = "test_user") -> MagicMock:
    """Create a MagicMock that passes isinstance(event, Message) checks."""
    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    from_user = MagicMock()
    from_user.id = user_id
    from_user.username = username
    msg.from_user = from_user
    return msg


def _make_callback_query(user_id: int, username: str = "test_user") -> MagicMock:
    """Create a MagicMock that passes isinstance(event, CallbackQuery) checks."""
    cq = MagicMock(spec=CallbackQuery)
    cq.answer = AsyncMock()
    from_user = MagicMock()
    from_user.id = user_id
    from_user.username = username
    cq.from_user = from_user
    return cq


# --- Core tests -----------------------------------------------------------------


async def test_allowed_user_passes(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Allowed user ID passes through to the handler."""
    event = _make_message(user_id=111111111)
    data: dict[str, Any] = {}

    result = await middleware(mock_handler, event, data)

    mock_handler.assert_awaited_once_with(event, data)
    assert result == "handler_result"


async def test_blocked_user_rejected(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Blocked user ID does NOT reach the handler."""
    event = _make_message(user_id=999999999)
    data: dict[str, Any] = {}

    result = await middleware(mock_handler, event, data)

    mock_handler.assert_not_awaited()
    assert result is None


async def test_blocked_user_gets_message(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Blocked user receives the denial message via message.answer()."""
    event = _make_message(user_id=999999999)
    data: dict[str, Any] = {}

    await middleware(mock_handler, event, data)

    event.answer.assert_awaited_once()
    assert event.answer.call_args.args[0] == _DENIAL_TEXT


async def test_blocked_user_logged(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocked attempt is logged at WARNING level."""
    mock_logger = MagicMock()
    monkeypatch.setattr("voice_bot.middleware.logger", mock_logger)

    event = _make_message(user_id=999999999, username="intruder")
    data: dict[str, Any] = {}

    await middleware(mock_handler, event, data)

    mock_logger.warning.assert_called_once()
    call_args = mock_logger.warning.call_args
    assert call_args.args[0] == "unauthorized_access_attempt"
    assert call_args.kwargs["user_id"] == 999999999
    assert call_args.kwargs["username"] == "intruder"


# --- Edge case tests ------------------------------------------------------------


async def test_no_from_user_returns_none(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Event without from_user is rejected silently — handler not called."""
    event = MagicMock(spec=Message)
    event.from_user = None
    event.answer = AsyncMock()
    data: dict[str, Any] = {}

    result = await middleware(mock_handler, event, data)

    mock_handler.assert_not_awaited()
    assert result is None


async def test_no_from_user_logged(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Event without from_user logs a WARNING."""
    mock_logger = MagicMock()
    monkeypatch.setattr("voice_bot.middleware.logger", mock_logger)

    event = MagicMock(spec=Message)
    event.from_user = None
    event.answer = AsyncMock()
    data: dict[str, Any] = {}

    await middleware(mock_handler, event, data)

    mock_logger.warning.assert_called_once()
    call_args = mock_logger.warning.call_args
    assert call_args.args[0] == "access_control_no_user"
    assert "event_type" in call_args.kwargs


async def test_blocked_callback_query_gets_alert(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Blocked CallbackQuery receives a denial alert with show_alert=True."""
    event = _make_callback_query(user_id=999999999)
    data: dict[str, Any] = {}

    await middleware(mock_handler, event, data)

    event.answer.assert_awaited_once()
    assert event.answer.call_args.args[0] == _DENIAL_TEXT
    assert event.answer.call_args.kwargs["show_alert"] is True


async def test_allowed_callback_query_passes(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Allowed CallbackQuery passes through to the handler."""
    event = _make_callback_query(user_id=222222222)
    data: dict[str, Any] = {}

    result = await middleware(mock_handler, event, data)

    mock_handler.assert_awaited_once_with(event, data)
    assert result == "handler_result"


async def test_empty_whitelist_blocks_all(
    mock_handler: AsyncMock,
) -> None:
    """Middleware with an empty whitelist blocks every user."""
    mw = AccessControlMiddleware([])
    event = _make_message(user_id=111111111)
    data: dict[str, Any] = {}

    result = await mw(mock_handler, event, data)

    mock_handler.assert_not_awaited()
    assert result is None


async def test_allowed_user_does_not_get_denial_message(
    middleware: AccessControlMiddleware,
    mock_handler: AsyncMock,
) -> None:
    """Allowed user does NOT receive the denial message."""
    event = _make_message(user_id=111111111)
    data: dict[str, Any] = {}

    await middleware(mock_handler, event, data)

    event.answer.assert_not_awaited()
