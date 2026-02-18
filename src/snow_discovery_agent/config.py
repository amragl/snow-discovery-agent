"""Configuration management for Snow Discovery Agent.

Provides a Pydantic Settings-based configuration class that loads settings
from environment variables (with ``SNOW_`` prefix) and ``.env`` files.

All ServiceNow connection parameters, optional tuning settings, and logging
configuration are managed here. A singleton-style ``get_config()`` factory
function avoids re-reading the environment on every call.

Usage::

    from snow_discovery_agent.config import get_config

    config = get_config()
    print(config.instance)       # https://dev12345.service-now.com
    print(config.timeout)        # 30
    print(config.log_level)      # INFO

To create a ``ServiceNowClient`` from the config::

    from snow_discovery_agent.config import get_config
    from snow_discovery_agent.client import ServiceNowClient

    config = get_config()
    client = config.create_client()
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .client import ServiceNowClient

logger = logging.getLogger(__name__)

# Valid Python logging level names (upper-cased for comparison)
_VALID_LOG_LEVELS: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)


class DiscoveryAgentConfig(BaseSettings):
    """Type-safe configuration for the Snow Discovery Agent.

    Loads values from environment variables with the ``SNOW_`` prefix and
    from a ``.env`` file if present. Required fields (``instance``,
    ``username``, ``password``) raise a ``ValidationError`` with a clear
    message when missing.

    Environment variables:
        SNOW_INSTANCE:    ServiceNow instance URL (required, must be HTTPS).
        SNOW_USERNAME:    ServiceNow username (required, non-empty).
        SNOW_PASSWORD:    ServiceNow password (required, non-empty).
        SNOW_TIMEOUT:     Request timeout in seconds (default 30).
        SNOW_MAX_RESULTS: Max results per query (default 100).
        SNOW_LOG_LEVEL:   Logging level (default INFO).
    """

    model_config = SettingsConfigDict(
        env_prefix="SNOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Required settings
    # ------------------------------------------------------------------

    instance: str = Field(
        ...,
        description="ServiceNow instance URL (e.g., https://dev12345.service-now.com)",
    )
    username: str = Field(
        ...,
        min_length=1,
        description="ServiceNow username for basic auth",
    )
    password: str = Field(
        ...,
        min_length=1,
        description="ServiceNow password for basic auth",
    )

    # ------------------------------------------------------------------
    # Optional settings
    # ------------------------------------------------------------------

    timeout: int = Field(
        default=30,
        gt=0,
        description="Request timeout in seconds",
    )
    max_results: int = Field(
        default=100,
        gt=0,
        description="Maximum number of results per API query",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("instance")
    @classmethod
    def _validate_instance_url(cls, value: str, info: ValidationInfo) -> str:
        """Validate and normalize the instance URL.

        The instance URL must use the HTTPS scheme. Trailing slashes are
        stripped for consistent URL construction.
        """
        url = value.strip().rstrip("/")
        if not url:
            raise ValueError(
                "SNOW_INSTANCE must not be empty. "
                "Provide your ServiceNow instance URL (e.g., https://dev12345.service-now.com)"
            )
        if not url.startswith("https://"):
            raise ValueError(
                f"SNOW_INSTANCE must use HTTPS. Got: {url!r}. "
                "Example: https://dev12345.service-now.com"
            )
        return url

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str, info: ValidationInfo) -> str:
        """Validate that the log level is a recognized Python logging level."""
        normalized = value.strip().upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"SNOW_LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}. "
                f"Got: {value!r}"
            )
        return normalized

    @model_validator(mode="after")
    def _log_config_loaded(self) -> DiscoveryAgentConfig:
        """Log that configuration was successfully loaded (debug level)."""
        logger.debug(
            "Configuration loaded: instance=%s, timeout=%d, max_results=%d, log_level=%s",
            self.instance,
            self.timeout,
            self.max_results,
            self.log_level,
        )
        return self

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    def create_client(self, **overrides: Any) -> ServiceNowClient:
        """Create a ``ServiceNowClient`` from this configuration.

        Any keyword arguments are forwarded to the ``ServiceNowClient``
        constructor, overriding the config-derived defaults.

        Args:
            **overrides: Optional keyword arguments passed to
                ``ServiceNowClient.__init__``.

        Returns:
            A configured ``ServiceNowClient`` instance.
        """
        kwargs: dict[str, Any] = {
            "instance": self.instance,
            "username": self.username,
            "password": self.password,
            "timeout": self.timeout,
        }
        kwargs.update(overrides)
        return ServiceNowClient(**kwargs)


# ------------------------------------------------------------------
# Singleton / factory
# ------------------------------------------------------------------

_config_instance: DiscoveryAgentConfig | None = None


def get_config(**overrides: Any) -> DiscoveryAgentConfig:
    """Return the global ``DiscoveryAgentConfig`` singleton.

    On the first call the config is loaded from environment variables and
    the ``.env`` file. Subsequent calls return the cached instance, avoiding
    redundant file I/O and environment reads.

    Args:
        **overrides: Optional field overrides passed to the
            ``DiscoveryAgentConfig`` constructor on first call only.
            Ignored on subsequent calls when the config is already cached.

    Returns:
        The global ``DiscoveryAgentConfig`` instance.

    Raises:
        pydantic.ValidationError: If required fields are missing or
            validation fails.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = DiscoveryAgentConfig(**overrides)
        logger.info(
            "Configuration initialized: instance=%s",
            _config_instance.instance,
        )
    return _config_instance


def _reset_config() -> None:
    """Reset the cached configuration singleton.

    Intended for test teardown so that each test can start with a clean
    configuration state. Should not be called in production code.
    """
    global _config_instance
    _config_instance = None
    logger.debug("Configuration singleton reset")
