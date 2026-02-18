"""FastMCP server for the Snow Discovery Agent.

Entry point for the MCP server that exposes ServiceNow Discovery tools
via the Model Context Protocol.  Initializes the FastMCP server instance,
loads configuration, creates a ``ServiceNowClient``, and registers tools
using ``@mcp.tool()`` decorators.

The server is designed for graceful degradation: it starts even when
ServiceNow configuration is missing, but tools that require a client
will return structured error responses indicating the configuration issue.

Usage::

    # Via entry point
    snow-discovery-agent

    # Via module
    python -m snow_discovery_agent.server
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from fastmcp import FastMCP

from .config import DiscoveryAgentConfig, get_config
from .exceptions import ServiceNowError

if TYPE_CHECKING:
    from .client import ServiceNowClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    "snow-discovery-agent",
    instructions=(
        "ServiceNow Discovery Agent -- an MCP server for managing and "
        "analyzing ServiceNow Discovery operations including scheduling "
        "scans, checking status, managing credentials, ranges, and patterns, "
        "and computing discovery health metrics."
    ),
)

# ---------------------------------------------------------------------------
# Server state -- populated during startup
# ---------------------------------------------------------------------------

_config: DiscoveryAgentConfig | None = None
_client: ServiceNowClient | None = None
_config_error: str | None = None


def _init_server() -> None:
    """Load configuration and create the ServiceNow client.

    Called once at server startup.  If configuration is missing or
    invalid, the error is captured and the server continues in degraded
    mode.  The ``get_server_info`` tool reports the configuration status
    so callers can understand why operations may fail.
    """
    global _config, _client, _config_error

    try:
        _config = get_config()
    except Exception as exc:
        _config_error = str(exc)
        logger.warning(
            "Configuration not available -- server running in degraded mode: %s",
            _config_error,
        )
        return

    # Configure logging level from the loaded config
    log_level = getattr(logging, _config.log_level, logging.INFO)
    logging.getLogger("snow_discovery_agent").setLevel(log_level)

    try:
        _client = _config.create_client()
        logger.info(
            "ServiceNow client created for instance: %s",
            _config.instance,
        )
    except Exception as exc:
        _config_error = f"Client creation failed: {exc}"
        logger.warning("Failed to create ServiceNow client: %s", exc)


def get_client() -> ServiceNowClient:
    """Return the server-wide ``ServiceNowClient``.

    Raises:
        ServiceNowError: If no client is available (configuration missing
            or client creation failed).
    """
    if _client is None:
        msg = _config_error or "ServiceNow client not initialized -- check configuration"
        raise ServiceNowError(
            message=msg,
            error_code="CLIENT_NOT_CONFIGURED",
        )
    return _client


def get_server_config() -> DiscoveryAgentConfig | None:
    """Return the server-wide ``DiscoveryAgentConfig``, or None if unavailable."""
    return _config


# ---------------------------------------------------------------------------
# Error handling helper
# ---------------------------------------------------------------------------


def handle_tool_error(exc: Exception) -> dict[str, Any]:
    """Convert an exception into a structured MCP tool error response.

    Catches ``ServiceNowError`` subclasses and formats them as a dict
    with ``error``, ``error_code``, and optional ``status_code`` and
    ``details`` keys.  For unexpected exceptions, returns a generic
    error response.

    Args:
        exc: The exception raised during tool execution.

    Returns:
        A structured error dict suitable for returning from an MCP tool.
    """
    if isinstance(exc, ServiceNowError):
        return exc.to_dict()

    logger.exception("Unexpected error in tool execution: %s", exc)
    return {
        "error": str(exc),
        "error_code": "UNEXPECTED_ERROR",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_server_info() -> dict[str, Any]:
    """Return server metadata and configuration status.

    Provides information about the running server instance including
    the server name, version, configured ServiceNow instance hostname
    (sanitized -- no credentials), and whether the configuration is
    loaded and the client is ready.

    Returns:
        A dict with server name, version, instance hostname,
        configuration status, and client readiness.
    """
    from . import __version__

    info: dict[str, Any] = {
        "server_name": "snow-discovery-agent",
        "version": __version__,
        "status": "running",
    }

    if _config is not None:
        # Sanitize: extract hostname only, never expose credentials or full URL
        parsed = urlparse(_config.instance)
        info["instance_hostname"] = parsed.hostname or "unknown"
        info["config_loaded"] = True
        info["log_level"] = _config.log_level
        info["timeout"] = _config.timeout
        info["max_results"] = _config.max_results
    else:
        info["instance_hostname"] = None
        info["config_loaded"] = False
        info["config_error"] = _config_error

    info["client_ready"] = _client is not None

    return info


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Snow Discovery Agent MCP server.

    Initializes configuration, creates the ServiceNow client (with
    graceful degradation if config is missing), and starts the FastMCP
    server for stdio transport.
    """
    # Set up root logging for the package
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    logger.info("Starting snow-discovery-agent MCP server")

    _init_server()

    if _config is not None:
        logger.info(
            "Server initialized: instance=%s, log_level=%s",
            _config.instance,
            _config.log_level,
        )
    else:
        logger.warning("Server started in degraded mode -- no ServiceNow configuration")

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
