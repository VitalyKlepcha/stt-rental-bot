"""Unit tests for the configuration module (voice_bot.config)."""

from __future__ import annotations

import os

# Set dummy env vars *before* importing voice_bot.config, because the module
# creates a singleton `settings = get_settings()` at import time which requires
# TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, and ALLOWED_USER_IDS to be present.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy_token")
os.environ.setdefault("OPENAI_API_KEY", "dummy_key")
os.environ.setdefault("ALLOWED_USER_IDS", "1,2")

from pydantic import ValidationError

from voice_bot.config import Settings, get_settings

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REQUIRED_ENV: dict[str, str] = {
    "TELEGRAM_BOT_TOKEN": "123456:ABC_token",
    "OPENAI_API_KEY": "sk-test-key",
    "ALLOWED_USER_IDS": "111,222,333",
}


@pytest.fixture
def clear_get_settings_cache() -> None:
    """Clear the lru_cache on get_settings before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set required env vars (and nothing else) for testing Settings loading."""
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    return _REQUIRED_ENV


# ---------------------------------------------------------------------------
# Tests: loading from environment variables
# ---------------------------------------------------------------------------


class TestSettingsFromEnv:
    """Tests that Settings loads correctly from environment variables."""

    def test_settings_load_from_env(
        self,
        env_vars: dict[str, str],
    ) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.telegram_bot_token == env_vars["TELEGRAM_BOT_TOKEN"]
        assert settings.openai_api_key == env_vars["OPENAI_API_KEY"]
        assert settings.allowed_user_ids == [111, 222, 333]

    def test_settings_load_from_dotenv(
        self,
        tmp_path: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Create a temporary .env file
        env_file = tmp_path / ".env"  # type: ignore[operator]
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=token_from_dotenv\n"
            "OPENAI_API_KEY=key_from_dotenv\n"
            "ALLOWED_USER_IDS=10,20,30\n"
            "LOG_LEVEL=WARNING\n"
            "PORT=9000\n",
            encoding="utf-8",
        )
        # Ensure env vars are NOT set in the environment
        for key in _REQUIRED_ENV:
            monkeypatch.delenv(key, raising=False)

        settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
        assert settings.telegram_bot_token == "token_from_dotenv"
        assert settings.openai_api_key == "key_from_dotenv"
        assert settings.allowed_user_ids == [10, 20, 30]
        assert settings.log_level == "WARNING"
        assert settings.port == 9000


# ---------------------------------------------------------------------------
# Tests: missing required fields
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    """Tests that missing required fields raise ValidationError."""

    def test_missing_telegram_bot_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "key")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert "telegram_bot_token" in str(exc_info.value)

    def test_missing_openai_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert "openai_api_key" in str(exc_info.value)

    def test_missing_allowed_user_ids(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OPENAI_API_KEY", "key")
        monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert "allowed_user_ids" in str(exc_info.value)

    def test_missing_all_required(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Tests: allowed_user_ids parsing
# ---------------------------------------------------------------------------


class TestAllowedUserIdsParsing:
    """Tests for parsing ALLOWED_USER_IDS from comma-separated string."""

    def test_multiple_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "123,456,789")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.allowed_user_ids == [123, 456, 789]
        assert all(isinstance(uid, int) for uid in settings.allowed_user_ids)

    def test_single_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "42")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.allowed_user_ids == [42]

    def test_ids_with_spaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", " 111 , 222 , 333 ")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.allowed_user_ids == [111, 222, 333]

    def test_empty_string_between_commas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "111,,222")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.allowed_user_ids == [111, 222]

    def test_trailing_comma(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "111,222,")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.allowed_user_ids == [111, 222]

    def test_invalid_id_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "123,abc,456")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Tests: webhook mode validation
# ---------------------------------------------------------------------------


class TestWebhookModeValidation:
    """Tests for webhook mode validation logic."""

    def test_webhook_true_without_url_or_secret(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("USE_WEBHOOK", "true")
        monkeypatch.delenv("WEBHOOK_URL", raising=False)
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert "webhook_url" in str(exc_info.value)
        assert "webhook_secret" in str(exc_info.value)

    def test_webhook_true_without_url_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("USE_WEBHOOK", "true")
        monkeypatch.setenv("WEBHOOK_SECRET", "secret123")
        monkeypatch.delenv("WEBHOOK_URL", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert "webhook_url" in str(exc_info.value)
        assert "webhook_secret" not in str(exc_info.value)

    def test_webhook_true_without_secret_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("USE_WEBHOOK", "true")
        monkeypatch.setenv("WEBHOOK_URL", "https://example.com")
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]
        assert "webhook_secret" in str(exc_info.value)
        assert "webhook_url" not in str(exc_info.value)

    def test_webhook_true_with_all_fields(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("USE_WEBHOOK", "true")
        monkeypatch.setenv("WEBHOOK_URL", "https://bot.example.com")
        monkeypatch.setenv("WEBHOOK_SECRET", "my_secret")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.use_webhook is True
        assert settings.webhook_url == "https://bot.example.com"
        assert settings.webhook_secret == "my_secret"

    def test_webhook_false_without_url_or_secret(
        self,
        env_vars: dict[str, str],
    ) -> None:
        # use_webhook defaults to False, so no validation error should occur
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.use_webhook is False
        assert settings.webhook_url is None
        assert settings.webhook_secret is None


# ---------------------------------------------------------------------------
# Tests: default values
# ---------------------------------------------------------------------------


class TestDefaultValues:
    """Tests that default values are correct when not overridden."""

    def test_default_webhook_path(self, env_vars: dict[str, str]) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.webhook_path == "/webhook"

    def test_default_log_level(self, env_vars: dict[str, str]) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.log_level == "INFO"

    def test_default_port(self, env_vars: dict[str, str]) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.port == 8080

    def test_default_use_webhook(self, env_vars: dict[str, str]) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.use_webhook is False

    def test_default_webhook_url_is_none(self, env_vars: dict[str, str]) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.webhook_url is None

    def test_default_webhook_secret_is_none(self, env_vars: dict[str, str]) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.webhook_secret is None


# ---------------------------------------------------------------------------
# Tests: extra / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge-case tests for robustness."""

    def test_extra_env_vars_ignored(
        self,
        env_vars: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOME_RANDOM_VAR", "should_be_ignored")
        # Should not raise — extra="ignore" in model_config
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.telegram_bot_token == env_vars["TELEGRAM_BOT_TOKEN"]

    def test_port_parsed_as_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("PORT", "3000")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.port == 3000
        assert isinstance(settings.port, int)

    def test_use_webhook_bool_parsing(
        self,
        env_vars: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("USE_WEBHOOK", "false")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.use_webhook is False

    def test_get_settings_caching(
        self,
        env_vars: dict[str, str],
        clear_get_settings_cache: None,
    ) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_cache_clear_returns_new_instance(
        self,
        env_vars: dict[str, str],
        clear_get_settings_cache: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        s1 = get_settings()
        get_settings.cache_clear()
        monkeypatch.setenv("PORT", "9999")
        s2 = get_settings()
        assert s1 is not s2
        assert s2.port == 9999
