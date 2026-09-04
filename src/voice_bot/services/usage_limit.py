"""Firestore-backed usage limits with atomic check-and-increment.

Enforces two limits:
- Per-user limit: ``PER_USER_LIMIT`` requests per Telegram user.
- Global limit: ``GLOBAL_LIMIT`` requests across all users.

Both counters live in the ``usage_limits`` Firestore collection.
A Firestore transaction ensures atomicity under concurrent access.
On Firestore errors the service fails open (allows the request).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog
from google.cloud import firestore
from pydantic import BaseModel

if TYPE_CHECKING:
    from google.cloud.firestore import AsyncClient, AsyncDocumentReference, AsyncTransaction

logger = structlog.get_logger(__name__)

PER_USER_LIMIT = 50
GLOBAL_LIMIT = 5000
COLLECTION_NAME = "usage_limits"
GLOBAL_DOC_ID = "global"
FIRESTORE_DATABASE_ID = "voice-bot-usage"


class UsageCheckResult(BaseModel):
    """Result of a usage limit check."""

    allowed: bool
    reason: Literal["ok", "user_limit_reached", "global_limit_reached"]


@firestore.async_transactional
async def _check_and_increment_txn(
    transaction: AsyncTransaction,
    user_ref: AsyncDocumentReference,
    global_ref: AsyncDocumentReference,
) -> UsageCheckResult:
    """Atomically check limits and increment counters within a Firestore transaction.

    Reads both the per-user and global documents, checks limits, and — if
    allowed — writes incremented counts.  If a limit is reached, no writes
    are performed and the transaction returns a denial result.
    """
    user_snapshot = await user_ref.get(transaction=transaction)
    global_snapshot = await global_ref.get(transaction=transaction)

    user_count = user_snapshot.get("count") if user_snapshot.exists else 0
    if user_count is None:
        user_count = 0

    global_count = global_snapshot.get("count") if global_snapshot.exists else 0
    if global_count is None:
        global_count = 0

    if user_count >= PER_USER_LIMIT:
        return UsageCheckResult(allowed=False, reason="user_limit_reached")

    if global_count >= GLOBAL_LIMIT:
        return UsageCheckResult(allowed=False, reason="global_limit_reached")

    transaction.set(user_ref, {"count": user_count + 1})
    transaction.set(global_ref, {"count": global_count + 1})

    return UsageCheckResult(allowed=True, reason="ok")


class UsageLimitService:
    """Async service that checks and enforces usage limits via Firestore.

    The underlying ``firestore.AsyncClient`` is created lazily on the first
    ``check_and_increment`` call so that constructing the service never
    performs I/O.
    """

    def __init__(self, database_id: str = FIRESTORE_DATABASE_ID) -> None:
        """Store the Firestore database ID; the client is created on first use.

        Parameters:
            database_id: Firestore database ID (named, not default).
        """
        self._database_id = database_id
        self._client: AsyncClient | None = None

    def _get_client(self) -> AsyncClient:
        """Return the lazy ``AsyncClient`` instance, creating it if needed."""
        if self._client is None:
            self._client = firestore.AsyncClient(database=self._database_id)
        return self._client

    async def check_and_increment(self, user_id: int) -> UsageCheckResult:
        """Check usage limits and increment counters atomically.

        Parameters:
            user_id: Telegram user ID (or 0 if ``from_user`` is None).

        Returns:
            ``UsageCheckResult`` with ``allowed=True`` if the request is
            within limits, or ``allowed=False`` with a reason otherwise.

        On Firestore errors, fails open — returns ``allowed=True`` so that
        infrastructure issues do not block users.
        """
        try:
            client = self._get_client()
            user_ref = client.collection(COLLECTION_NAME).document(f"user_{user_id}")
            global_ref = client.collection(COLLECTION_NAME).document(GLOBAL_DOC_ID)
            transaction = client.transaction()
            return await _check_and_increment_txn(transaction, user_ref, global_ref)
        except Exception as exc:
            logger.error(
                "usage_limit_check_failed",
                user_id=user_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return UsageCheckResult(allowed=True, reason="ok")

    async def close(self) -> None:
        """Close the underlying Firestore client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.debug("usage_limit_client_closed")


def create_usage_limit_service() -> UsageLimitService:
    """Create a ``UsageLimitService`` using the default Firestore database ID."""
    return UsageLimitService()
