"""Tests for the snow_discovery_agent.config module.

Covers:
- Loading config from environment variables
- Missing required fields raise clear ValidationError
- URL validation (must be HTTPS)
- Defaults for optional fields
- get_config() singleton behavior
- _reset_config() teardown
- .env file loading
- create_client() integration
- Log level validation
"""

from __future__ import annotations

import textwrap

import pytest
from pydantic import ValidationError

from snow_discovery_agent.config import (
    DiscoveryAgentConfig,
    _reset_config,
    get_config,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Reset the config singleton before each test."""
    _reset_config()
    yield  # type: ignore[misc]
    _reset_config()


VALID_ENV = {
    "SNOW_INSTANCE": "https://dev12345.service-now.com",
    "SNOW_USERNAME": "admin",
    "SNOW_PASSWORD": "secret",
}


@pytest.fixture()
def valid_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set valid SNOW_ env vars and return them."""
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(VALID_ENV)


# ------------------------------------------------------------------
# Required field validation
# ------------------------------------------------------------------


class TestRequiredFields:
    """Tests that missing required fields raise clear errors."""

    def test_missing_all_required_raises(self) -> None:
        """All three required fields missing should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "instance" in field_names
        assert "username" in field_names
        assert "password" in field_names

    def test_missing_instance_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing SNOW_INSTANCE should raise a clear error."""
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"][0] == "instance" for e in errors)

    def test_missing_username_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing SNOW_USERNAME should raise a clear error."""
        monkeypatch.setenv("SNOW_INSTANCE", "https://dev.service-now.com")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"][0] == "username" for e in errors)

    def test_missing_password_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing SNOW_PASSWORD should raise a clear error."""
        monkeypatch.setenv("SNOW_INSTANCE", "https://dev.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"][0] == "password" for e in errors)

    def test_empty_username_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty SNOW_USERNAME should raise ValidationError."""
        monkeypatch.setenv("SNOW_INSTANCE", "https://dev.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"][0] == "username" for e in errors)

    def test_empty_password_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty SNOW_PASSWORD should raise ValidationError."""
        monkeypatch.setenv("SNOW_INSTANCE", "https://dev.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"][0] == "password" for e in errors)


# ------------------------------------------------------------------
# Instance URL validation
# ------------------------------------------------------------------


class TestInstanceURLValidation:
    """Tests for SNOW_INSTANCE URL validation."""

    def test_valid_https_url(self, valid_env: dict[str, str]) -> None:
        """Valid HTTPS URL is accepted."""
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.instance == "https://dev12345.service-now.com"

    def test_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Trailing slashes are removed from the instance URL."""
        monkeypatch.setenv("SNOW_INSTANCE", "https://dev12345.service-now.com/")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.instance == "https://dev12345.service-now.com"

    def test_multiple_trailing_slashes_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple trailing slashes are removed."""
        monkeypatch.setenv("SNOW_INSTANCE", "https://dev12345.service-now.com///")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.instance == "https://dev12345.service-now.com"

    def test_http_url_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTTP (non-HTTPS) URL is rejected."""
        monkeypatch.setenv("SNOW_INSTANCE", "http://dev12345.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert "HTTPS" in str(exc_info.value)

    def test_empty_instance_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty SNOW_INSTANCE is rejected."""
        monkeypatch.setenv("SNOW_INSTANCE", "")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError):
            DiscoveryAgentConfig()  # type: ignore[call-arg]

    def test_whitespace_only_instance_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace-only SNOW_INSTANCE is rejected."""
        monkeypatch.setenv("SNOW_INSTANCE", "   ")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError):
            DiscoveryAgentConfig()  # type: ignore[call-arg]

    def test_no_scheme_url_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """URL without scheme is rejected."""
        monkeypatch.setenv("SNOW_INSTANCE", "dev12345.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "admin")
        monkeypatch.setenv("SNOW_PASSWORD", "secret")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert "HTTPS" in str(exc_info.value)


# ------------------------------------------------------------------
# Optional fields and defaults
# ------------------------------------------------------------------


class TestOptionalDefaults:
    """Tests for optional field defaults."""

    def test_default_timeout(self, valid_env: dict[str, str]) -> None:
        """Default timeout is 30."""
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.timeout == 30

    def test_default_max_results(self, valid_env: dict[str, str]) -> None:
        """Default max_results is 100."""
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.max_results == 100

    def test_default_log_level(self, valid_env: dict[str, str]) -> None:
        """Default log_level is INFO."""
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.log_level == "INFO"

    def test_custom_timeout(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom SNOW_TIMEOUT overrides default."""
        monkeypatch.setenv("SNOW_TIMEOUT", "60")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.timeout == 60

    def test_custom_max_results(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom SNOW_MAX_RESULTS overrides default."""
        monkeypatch.setenv("SNOW_MAX_RESULTS", "500")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.max_results == 500

    def test_custom_log_level(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom SNOW_LOG_LEVEL overrides default."""
        monkeypatch.setenv("SNOW_LOG_LEVEL", "DEBUG")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.log_level == "DEBUG"

    def test_zero_timeout_rejected(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Timeout of 0 is rejected (must be positive)."""
        monkeypatch.setenv("SNOW_TIMEOUT", "0")
        with pytest.raises(ValidationError):
            DiscoveryAgentConfig()  # type: ignore[call-arg]

    def test_negative_timeout_rejected(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Negative timeout is rejected."""
        monkeypatch.setenv("SNOW_TIMEOUT", "-5")
        with pytest.raises(ValidationError):
            DiscoveryAgentConfig()  # type: ignore[call-arg]

    def test_zero_max_results_rejected(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """max_results of 0 is rejected (must be positive)."""
        monkeypatch.setenv("SNOW_MAX_RESULTS", "0")
        with pytest.raises(ValidationError):
            DiscoveryAgentConfig()  # type: ignore[call-arg]

    def test_negative_max_results_rejected(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Negative max_results is rejected."""
        monkeypatch.setenv("SNOW_MAX_RESULTS", "-1")
        with pytest.raises(ValidationError):
            DiscoveryAgentConfig()  # type: ignore[call-arg]


# ------------------------------------------------------------------
# Log level validation
# ------------------------------------------------------------------


class TestLogLevelValidation:
    """Tests for SNOW_LOG_LEVEL validation."""

    @pytest.mark.parametrize(
        "level",
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    def test_valid_log_levels(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, level: str) -> None:
        """All standard Python log levels are accepted."""
        monkeypatch.setenv("SNOW_LOG_LEVEL", level)
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.log_level == level

    def test_lowercase_log_level_normalized(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Lowercase log level is normalized to uppercase."""
        monkeypatch.setenv("SNOW_LOG_LEVEL", "debug")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.log_level == "DEBUG"

    def test_mixed_case_log_level_normalized(
        self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mixed-case log level is normalized to uppercase."""
        monkeypatch.setenv("SNOW_LOG_LEVEL", "Warning")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.log_level == "WARNING"

    def test_invalid_log_level_rejected(self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid log level string is rejected."""
        monkeypatch.setenv("SNOW_LOG_LEVEL", "VERBOSE")
        with pytest.raises(ValidationError) as exc_info:
            DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert "SNOW_LOG_LEVEL" in str(exc_info.value)


# ------------------------------------------------------------------
# get_config() singleton behavior
# ------------------------------------------------------------------


class TestGetConfig:
    """Tests for the get_config() factory function."""

    def test_returns_config_instance(self, valid_env: dict[str, str]) -> None:
        """get_config() returns a DiscoveryAgentConfig instance."""
        config = get_config()
        assert isinstance(config, DiscoveryAgentConfig)

    def test_singleton_returns_same_object(self, valid_env: dict[str, str]) -> None:
        """get_config() returns the same instance on subsequent calls."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_singleton_ignores_env_changes(
        self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once cached, get_config() does not re-read environment changes."""
        config1 = get_config()
        monkeypatch.setenv("SNOW_INSTANCE", "https://other.service-now.com")
        config2 = get_config()
        assert config2.instance == config1.instance
        assert config2.instance == "https://dev12345.service-now.com"

    def test_raises_when_config_invalid(self) -> None:
        """get_config() raises ValidationError when env is not set."""
        with pytest.raises(ValidationError):
            get_config()


# ------------------------------------------------------------------
# _reset_config() teardown
# ------------------------------------------------------------------


class TestResetConfig:
    """Tests for _reset_config() teardown function."""

    def test_reset_allows_new_config(
        self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After _reset_config(), get_config() creates a new instance."""
        config1 = get_config()
        _reset_config()
        monkeypatch.setenv("SNOW_INSTANCE", "https://other.service-now.com")
        config2 = get_config()
        assert config2.instance == "https://other.service-now.com"
        assert config1 is not config2

    def test_reset_is_idempotent(self) -> None:
        """Calling _reset_config() multiple times does not raise."""
        _reset_config()
        _reset_config()
        _reset_config()


# ------------------------------------------------------------------
# .env file loading
# ------------------------------------------------------------------


class TestEnvFileLoading:
    """Tests for .env file loading support."""

    def test_loads_from_env_file(self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config loads values from a .env file."""
        env_content = textwrap.dedent("""\
            SNOW_INSTANCE=https://envfile.service-now.com
            SNOW_USERNAME=envuser
            SNOW_PASSWORD=envpass
            SNOW_TIMEOUT=45
        """)
        env_file = tmp_path / ".env"  # type: ignore[operator]
        env_file.write_text(env_content)

        # Change to the tmp directory so the config finds the .env file
        monkeypatch.chdir(tmp_path)

        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.instance == "https://envfile.service-now.com"
        assert config.username == "envuser"
        assert config.password == "envpass"
        assert config.timeout == 45

    def test_env_vars_override_env_file(
        self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables take precedence over .env file values."""
        env_content = textwrap.dedent("""\
            SNOW_INSTANCE=https://envfile.service-now.com
            SNOW_USERNAME=envuser
            SNOW_PASSWORD=envpass
        """)
        env_file = tmp_path / ".env"  # type: ignore[operator]
        env_file.write_text(env_content)
        monkeypatch.chdir(tmp_path)

        # Set environment variable to override
        monkeypatch.setenv("SNOW_INSTANCE", "https://override.service-now.com")

        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.instance == "https://override.service-now.com"


# ------------------------------------------------------------------
# create_client() integration
# ------------------------------------------------------------------


class TestCreateClient:
    """Tests for the create_client() factory method."""

    def test_creates_client_with_config_values(self, valid_env: dict[str, str]) -> None:
        """create_client() produces a ServiceNowClient with config values."""
        from snow_discovery_agent.client import ServiceNowClient

        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        client = config.create_client()
        assert isinstance(client, ServiceNowClient)
        assert client.instance == "https://dev12345.service-now.com"
        client.close()

    def test_creates_client_with_overrides(self, valid_env: dict[str, str]) -> None:
        """create_client() accepts keyword overrides."""
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        client = config.create_client(timeout=99)
        assert client._timeout == 99
        client.close()

    def test_creates_client_with_custom_timeout(
        self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """create_client() uses the config timeout value."""
        monkeypatch.setenv("SNOW_TIMEOUT", "60")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        client = config.create_client()
        assert client._timeout == 60
        client.close()


# ------------------------------------------------------------------
# Config immutability / extra fields
# ------------------------------------------------------------------


class TestConfigBehavior:
    """Tests for general config behavior."""

    def test_extra_env_vars_ignored(
        self, valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Extra SNOW_ env vars that are not defined fields are ignored."""
        monkeypatch.setenv("SNOW_UNKNOWN_SETTING", "should_be_ignored")
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert not hasattr(config, "unknown_setting")

    def test_config_field_values(self, valid_env: dict[str, str]) -> None:
        """All config field values match the env vars."""
        config = DiscoveryAgentConfig()  # type: ignore[call-arg]
        assert config.instance == "https://dev12345.service-now.com"
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.timeout == 30
        assert config.max_results == 100
        assert config.log_level == "INFO"

    def test_config_from_kwargs(self) -> None:
        """Config can be created directly with keyword arguments."""
        config = DiscoveryAgentConfig(
            instance="https://test.service-now.com",
            username="testuser",
            password="testpass",
            timeout=15,
            max_results=50,
            log_level="DEBUG",
        )
        assert config.instance == "https://test.service-now.com"
        assert config.username == "testuser"
        assert config.password == "testpass"
        assert config.timeout == 15
        assert config.max_results == 50
        assert config.log_level == "DEBUG"
