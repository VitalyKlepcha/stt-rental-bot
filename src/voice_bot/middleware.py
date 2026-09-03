"""Access control middleware — restricts bot usage to a whitelist of Telegram user IDs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = structlog.get_logger(__name__)

_DENIAL_TEXT = "У вас нет доступа к этому боту."


class AccessControlMiddleware(BaseMiddleware):
    """Middleware that blocks updates from users not in the whitelist.

    Checks ``event.from_user.id`` against the allowed user IDs.  Unauthorized
    updates are logged at WARNING level and the handler is **not** called.
    When the event is a :class:`Message`, a denial message is sent to the chat.
    For :class:`CallbackQuery` events, a short alert is shown via ``answer``.
    """

    def __init__(self, allowed_user_ids: list[int]) -> None:
        """Store the whitelist of Telegram user IDs as a frozenset for O(1) lookup.

        Parameters:
            allowed_user_ids: Telegram user IDs permitted to interact with the bot.
        """
        self._allowed_user_ids: frozenset[int] = frozenset(allowed_user_ids)
        logger.debug(
            "access_control_initialized",
            allowed_count=len(self._allowed_user_ids),
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Check the user ID against the whitelist before passing to the handler.

        Parameters:
            handler: The next handler in the middleware chain.
            event: The incoming Telegram event (Message, CallbackQuery, etc.).
            data: Contextual data dict passed through the middleware chain.

        Returns:
            The result of the handler, or ``None`` if access was denied.
        """
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            logger.warning(
                "access_control_no_user",
                event_type=type(event).__name__,
            )
            return None

        user_id = from_user.id

        if user_id not in self._allowed_user_ids:
            logger.warning(
                "unauthorized_access_attempt",
                user_id=user_id,
                username=from_user.username,
            )
            if isinstance(event, Message):
                await event.answer(_DENIAL_TEXT)
            elif isinstance(event, CallbackQuery):
                await event.answer(_DENIAL_TEXT, show_alert=True)
            return None

        return await handler(event, data)
