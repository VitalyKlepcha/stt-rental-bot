"""Unit tests for the Firestore-backed usage limit service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from voice_bot.services.usage_limit import (
    GLOBAL_LIMIT,
    PER_USER_LIMIT,
    UsageCheckResult,
    UsageLimitService,
    _check_and_increment_txn,
    create_usage_limit_service,
)


# --- Helpers ------------------------------------------------------------------


def _make_snapshot(count: int | None, exists: bool = True) -> MagicMock:
    """Create a mock DocumentSnapshot with the given count and existence."""
    snapshot = MagicMock()
    snapshot.exists = exists
    snapshot.get.return_value = count
    return snapshot


def _make_refs(
    user_count: int | None = 0,
    global_count: int | None = 0,
    user_exists: bool = True,
    global_exists: bool = True,
) -> tuple[MagicMock, MagicMock, AsyncMock]:
    """Create mock document refs and a mock transaction for testing core logic.

    Returns:
        A tuple of (user_ref, global_ref, transaction) mocks.
    """
    user_ref = MagicMock()
    global_ref = MagicMock()

    user_snapshot = _make_snapshot(user_count, user_exists)
    global_snapshot = _make_snapshot(global_count, global_exists)

    user_ref.get = AsyncMock(return_value=user_snapshot)
    global_ref.get = AsyncMock(return_value=global_snapshot)

    transaction = AsyncMock()
    transaction.set = MagicMock()

    return user_ref, global_ref, transaction


# The @firestore.async_transactional decorator wraps _check_and_increment_txn
# in an _AsyncTransactional object. Access the original function via .to_wrap
# to test core logic without Firestore internals.
_txn_fn = _check_and_increment_txn.to_wrap


# --- Core logic tests ---------------------------------------------------------


async def test_user_below_limit_allowed() -> None:
    """User below the per-user limit is allowed and counters incremented."""
    user_ref, global_ref, transaction = _make_refs(
        user_count=10,
        global_count=100,
    )

    result = await _txn_fn(transaction, user_ref, global_ref)

    assert result.allowed is True
    assert result.reason == "ok"
    transaction.set.assert_any_call(user_ref, {"count": 11})
    transaction.set.assert_any_call(global_ref, {"count": 101})


async def test_user_at_limit_blocked() -> None:
    """User at the per-user limit is blocked with user_limit_reached."""
    user_ref, global_ref, transaction = _make_refs(
        user_count=PER_USER_LIMIT,
        global_count=100,
    )

    result = await _txn_fn(transaction, user_ref, global_ref)

    assert result.allowed is False
    assert result.reason == "user_limit_reached"
    transaction.set.assert_not_called()


async def test_global_limit_reached_blocked() -> None:
    """Global limit reached blocks all users with global_limit_reached."""
    user_ref, global_ref, transaction = _make_refs(
        user_count=10,
        global_count=GLOBAL_LIMIT,
    )

    result = await _txn_fn(transaction, user_ref, global_ref)

    assert result.allowed is False
    assert result.reason == "global_limit_reached"
    transaction.set.assert_not_called()


async def test_new_user_allowed() -> None:
    """New user (document doesn't exist) is allowed with count starting at 1."""
    user_ref, global_ref, transaction = _make_refs(
        user_count=None,
        global_count=100,
        user_exists=False,
        global_exists=True,
    )

    result = await _txn_fn(transaction, user_ref, global_ref)

    assert result.allowed is True
    assert result.reason == "ok"
    transaction.set.assert_any_call(user_ref, {"count": 1})
    transaction.set.assert_any_call(global_ref, {"count": 101})


# --- Service-level tests ------------------------------------------------------


async def test_close_calls_client_close() -> None:
    """close() calls the Firestore client's close method."""
    service = UsageLimitService()
    mock_client = AsyncMock()
    service._client = mock_client

    await service.close()

    mock_client.close.assert_awaited_once()
    assert service._client is None


async def test_close_when_client_not_created() -> None:
    """close() is a no-op when the client was never created."""
    service = UsageLimitService()

    await service.close()

    assert service._client is None


async def test_fail_open_on_firestore_error() -> None:
    """Service fails open (allows request) when Firestore is unavailable."""
    service = UsageLimitService()
    mock_client = MagicMock()
    mock_client.collection = MagicMock(side_effect=RuntimeError("Connection refused"))
    service._client = mock_client

    result = await service.check_and_increment(123)

    assert result.allowed is True
    assert result.reason == "ok"


def test_create_usage_limit_service_returns_instance() -> None:
    """Factory function returns a UsageLimitService instance."""
    service = create_usage_limit_service()
    assert isinstance(service, UsageLimitService)


def test_usage_check_result_model() -> None:
    """UsageCheckResult model accepts valid reason values."""
    ok = UsageCheckResult(allowed=True, reason="ok")
    assert ok.allowed is True
    assert ok.reason == "ok"

    blocked = UsageCheckResult(allowed=False, reason="user_limit_reached")
    assert blocked.allowed is False
    assert blocked.reason == "user_limit_reached"
