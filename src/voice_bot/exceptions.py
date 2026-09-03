"""Custom exception classes for the voice-to-PDF Telegram bot domain.

All domain errors inherit from :class:`VoiceBotError`, allowing handlers to
catch every bot-specific exception with a single ``except`` clause while still
distinguishing individual error scenarios by type.

Every exception accepts a human-readable *message* and an optional *cause*
(the original exception that triggered the domain error).  When *cause* is
provided it is also assigned to ``__cause__`` so that standard Python
exception chaining (``raise … from …``) works naturally and traceback
printouts include the original error.
"""

from __future__ import annotations


class VoiceBotError(Exception):
    """Base class for all domain-specific errors raised by the voice bot.

    Parameters:
        message: Human-readable description of the error.
        cause: The original exception that triggered this domain error,
            if any.  When supplied, it is also set as ``__cause__`` so
            that Python's built-in exception chaining displays it.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self._message: str = message
        self._cause: Exception | None = cause
        if cause is not None:
            self.__cause__ = cause

    @property
    def message(self) -> str:
        """Return the human-readable error message."""
        return self._message

    @property
    def cause(self) -> Exception | None:
        """Return the original exception that triggered this error, if any."""
        return self._cause

    def __str__(self) -> str:
        if self._cause is not None:
            cause_name = type(self._cause).__name__
            return f"{self._message} (caused by: {cause_name}: {self._cause})"
        return self._message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(message={self._message!r}, cause={self._cause!r})"


class TranscriptionError(VoiceBotError):
    """Raised when the OpenAI Whisper transcription API call fails.

    Covers timeout, authentication, rate-limit, and invalid-audio scenarios.
    """


class ExtractionError(VoiceBotError):
    """Raised when the GPT-4o-mini structured-output extraction fails.

    Covers API errors (timeout, auth, rate-limit) as well as cases where
    the model returns ``None`` or unparseable data.
    """


class PDFGenerationError(VoiceBotError):
    """Raised when WeasyPrint fails to render the PDF document.

    Covers template rendering errors, missing CSS, and WeasyPrint
    internal failures.
    """


class VoiceDownloadError(VoiceBotError):
    """Raised when downloading a voice file from the Telegram Bot API fails.

    Covers network errors, file-not-found, and Telegram API rate limits.
    """


class AccessDeniedError(VoiceBotError):
    """Raised when a user not in the whitelist attempts to interact with the bot.

    Parameters:
        message: Human-readable description of the denial.
        user_id: The Telegram user ID of the unauthorized user, if known.
        cause: The original exception, if any.
    """

    def __init__(
        self,
        message: str,
        user_id: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self._user_id: int | None = user_id

    @property
    def user_id(self) -> int | None:
        """Return the Telegram user ID of the denied user, if known."""
        return self._user_id

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"message={self._message!r}, "
            f"user_id={self._user_id!r}, "
            f"cause={self._cause!r})"
        )
