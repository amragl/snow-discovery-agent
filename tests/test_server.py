"""Tests for the FastMCP server module."""

from __future__ import annotations

import asyncio
import importlib
import logging
from unittest.mock import patch

import pytest

from snow_discovery_agent.config import _reset_config
from snow_discovery_agent.exceptions import (
    ServiceNowAuthError,
    ServiceNowConnectionError,
    ServiceNowError,
    ServiceNowNotFoundError,
    ServiceNowPermissionError,
    ServiceNowRateLimitError,
)

# ---------------------------------------------------------------------------
# Helper to reset server state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_server_state(monkeypatch: pytest.MonkeyPatch):
    """Reset server module state and config singleton between tests."""
    _reset_config()

    from snow_discovery_agent import server

    server._config = None
    server._client = None
    server._config_error = None

    yield

    _reset_config()
    server._config = None
    server._client = None
    server._config_error = None


@pytest.fixture()
def _set_snow_env(monkeypatch: pytest.MonkeyPatch):
    """Set valid ServiceNow env vars for tests that need config."""
    monkeypatch.setenv("SNOW_INSTANCE", "https://dev99999.service-now.com")
    monkeypatch.setenv("SNOW_USERNAME", "testuser")
    monkeypatch.setenv("SNOW_PASSWORD", "testpass")


# ===========================================================================
# Test: MCP server instantiation
# ===========================================================================


class TestMCPServerInstance:
    """Verify the FastMCP server instance is configured correctly."""

    def test_mcp_instance_exists(self):
        from snow_discovery_agent.server import mcp

        assert mcp is not None

    def test_mcp_name(self):
        from snow_discovery_agent.server import mcp

        assert mcp.name == "snow-discovery-agent"

    def test_mcp_is_fastmcp_instance(self):
        from fastmcp import FastMCP

        from snow_discovery_agent.server import mcp

        assert isinstance(mcp, FastMCP)


# ===========================================================================
# Test: get_server_info tool registration
# ===========================================================================


class TestGetServerInfoRegistration:
    """Verify the get_server_info tool is registered with the MCP server."""

    def test_tool_is_registered(self):
        from snow_discovery_agent.server import mcp

        async def _get_tools():
            return await mcp.get_tools()

        tools = asyncio.run(_get_tools())
        assert "get_server_info" in tools

    def test_tool_has_description(self):
        from snow_discovery_agent.server import mcp

        async def _get_tools():
            return await mcp.get_tools()

        tools = asyncio.run(_get_tools())
        tool = tools["get_server_info"]
        assert "server metadata" in tool.description.lower()


# ===========================================================================
# Test: get_server_info tool output (degraded mode)
# ===========================================================================


class TestGetServerInfoDegradedMode:
    """Test get_server_info when config is missing (degraded mode)."""

    def test_returns_dict(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert isinstance(result, dict)

    def test_server_name(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["server_name"] == "snow-discovery-agent"

    def test_version_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert "version" in result
        assert isinstance(result["version"], str)
        assert result["version"] == "0.1.0"

    def test_status_running(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["status"] == "running"

    def test_config_not_loaded(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["config_loaded"] is False

    def test_client_not_ready(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["client_ready"] is False

    def test_instance_hostname_is_none(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["instance_hostname"] is None

    def test_config_error_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert "config_error" in result
        assert result["config_error"] is not None
        assert "validation error" in result["config_error"].lower()


# ===========================================================================
# Test: get_server_info tool output (configured mode)
# ===========================================================================


class TestGetServerInfoConfigured:
    """Test get_server_info when valid config is provided."""

    @pytest.fixture(autouse=True)
    def _setup_env(self, _set_snow_env):
        pass

    def test_config_loaded(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["config_loaded"] is True

    def test_client_ready(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["client_ready"] is True

    def test_instance_hostname_sanitized(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["instance_hostname"] == "dev99999.service-now.com"
        # Must not contain the full URL or credentials
        assert "https://" not in str(result["instance_hostname"])

    def test_log_level_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["log_level"] == "INFO"

    def test_timeout_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["timeout"] == 30

    def test_max_results_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["max_results"] == 100

    def test_no_config_error_key(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert "config_error" not in result

    def test_server_name_always_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["server_name"] == "snow-discovery-agent"

    def test_version_always_present(self):
        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["version"] == "0.1.0"


# ===========================================================================
# Test: get_server_info with custom config values
# ===========================================================================


class TestGetServerInfoCustomConfig:
    """Test get_server_info with non-default config values."""

    def test_custom_log_level(self, monkeypatch):
        monkeypatch.setenv("SNOW_INSTANCE", "https://custom.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "user")
        monkeypatch.setenv("SNOW_PASSWORD", "pass")
        monkeypatch.setenv("SNOW_LOG_LEVEL", "DEBUG")

        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["log_level"] == "DEBUG"

    def test_custom_timeout(self, monkeypatch):
        monkeypatch.setenv("SNOW_INSTANCE", "https://custom.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "user")
        monkeypatch.setenv("SNOW_PASSWORD", "pass")
        monkeypatch.setenv("SNOW_TIMEOUT", "60")

        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["timeout"] == 60

    def test_custom_max_results(self, monkeypatch):
        monkeypatch.setenv("SNOW_INSTANCE", "https://custom.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "user")
        monkeypatch.setenv("SNOW_PASSWORD", "pass")
        monkeypatch.setenv("SNOW_MAX_RESULTS", "500")

        from snow_discovery_agent.server import _init_server, get_server_info

        _init_server()
        result = get_server_info.fn()
        assert result["max_results"] == 500


# ===========================================================================
# Test: main() entry point exists
# ===========================================================================


class TestMainEntryPoint:
    """Verify the main() entry point is callable and defined."""

    def test_main_exists(self):
        from snow_discovery_agent.server import main

        assert callable(main)

    def test_main_is_importable_from_package(self):
        from snow_discovery_agent.server import main

        assert main.__name__ == "main"


# ===========================================================================
# Test: get_client() function
# ===========================================================================


class TestGetClient:
    """Test the get_client() helper function."""

    def test_raises_when_no_client(self):
        from snow_discovery_agent.server import get_client

        with pytest.raises(ServiceNowError) as exc_info:
            get_client()
        assert exc_info.value.error_code == "CLIENT_NOT_CONFIGURED"

    def test_raises_with_config_error_message(self):
        from snow_discovery_agent.server import _init_server, get_client

        _init_server()  # Will fail without env vars
        with pytest.raises(ServiceNowError) as exc_info:
            get_client()
        assert "validation error" in exc_info.value.message.lower()

    def test_returns_client_when_configured(self, _set_snow_env):
        from snow_discovery_agent.client import ServiceNowClient
        from snow_discovery_agent.server import _init_server, get_client

        _init_server()
        client = get_client()
        assert isinstance(client, ServiceNowClient)

    def test_client_has_correct_instance(self, _set_snow_env):
        from snow_discovery_agent.server import _init_server, get_client

        _init_server()
        client = get_client()
        assert client.instance == "https://dev99999.service-now.com"


# ===========================================================================
# Test: get_server_config() function
# ===========================================================================


class TestGetServerConfig:
    """Test the get_server_config() helper function."""

    def test_returns_none_when_not_initialized(self):
        from snow_discovery_agent.server import get_server_config

        assert get_server_config() is None

    def test_returns_none_after_failed_init(self):
        from snow_discovery_agent.server import _init_server, get_server_config

        _init_server()  # Will fail without env vars
        assert get_server_config() is None

    def test_returns_config_when_initialized(self, _set_snow_env):
        from snow_discovery_agent.config import DiscoveryAgentConfig
        from snow_discovery_agent.server import _init_server, get_server_config

        _init_server()
        config = get_server_config()
        assert isinstance(config, DiscoveryAgentConfig)
        assert config.instance == "https://dev99999.service-now.com"


# ===========================================================================
# Test: handle_tool_error()
# ===========================================================================


class TestHandleToolError:
    """Test the error handling wrapper function."""

    def test_handles_service_now_error(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowError("test error", error_code="TEST", status_code=500)
        result = handle_tool_error(exc)
        assert result["error"] == "test error"
        assert result["error_code"] == "TEST"
        assert result["status_code"] == 500

    def test_handles_auth_error(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowAuthError("bad creds", status_code=401)
        result = handle_tool_error(exc)
        assert result["error_code"] == "AUTHENTICATION_ERROR"
        assert result["status_code"] == 401

    def test_handles_permission_error(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowPermissionError("forbidden")
        result = handle_tool_error(exc)
        assert result["error_code"] == "PERMISSION_ERROR"
        assert result["status_code"] == 403

    def test_handles_not_found_error(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowNotFoundError("missing")
        result = handle_tool_error(exc)
        assert result["error_code"] == "NOT_FOUND"
        assert result["status_code"] == 404

    def test_handles_rate_limit_error(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowRateLimitError("too many requests")
        result = handle_tool_error(exc)
        assert result["error_code"] == "RATE_LIMIT_ERROR"
        assert result["status_code"] == 429

    def test_handles_connection_error(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowConnectionError("timeout")
        result = handle_tool_error(exc)
        assert result["error_code"] == "CONNECTION_ERROR"
        assert "status_code" not in result  # Connection errors have no HTTP status

    def test_handles_unexpected_exception(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ValueError("something unexpected")
        result = handle_tool_error(exc)
        assert result["error_code"] == "UNEXPECTED_ERROR"
        assert "something unexpected" in result["error"]

    def test_handles_error_with_details(self):
        from snow_discovery_agent.server import handle_tool_error

        exc = ServiceNowError(
            "test",
            error_code="TEST",
            details={"extra": "info"},
        )
        result = handle_tool_error(exc)
        assert result["details"] == {"extra": "info"}


# ===========================================================================
# Test: _init_server() behavior
# ===========================================================================


class TestInitServer:
    """Test server initialization logic."""

    def test_degraded_mode_without_config(self):
        from snow_discovery_agent import server

        server._init_server()
        assert server._config is None
        assert server._client is None
        assert server._config_error is not None

    def test_successful_init_with_config(self, _set_snow_env):
        from snow_discovery_agent import server

        server._init_server()
        assert server._config is not None
        assert server._client is not None
        assert server._config_error is None

    def test_sets_log_level_from_config(self, monkeypatch):
        monkeypatch.setenv("SNOW_INSTANCE", "https://test.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "user")
        monkeypatch.setenv("SNOW_PASSWORD", "pass")
        monkeypatch.setenv("SNOW_LOG_LEVEL", "DEBUG")

        from snow_discovery_agent import server

        server._init_server()

        agent_logger = logging.getLogger("snow_discovery_agent")
        assert agent_logger.level == logging.DEBUG

    def test_handles_client_creation_failure(self, monkeypatch):
        monkeypatch.setenv("SNOW_INSTANCE", "https://test.service-now.com")
        monkeypatch.setenv("SNOW_USERNAME", "user")
        monkeypatch.setenv("SNOW_PASSWORD", "pass")

        from snow_discovery_agent import server
        from snow_discovery_agent.config import DiscoveryAgentConfig

        with patch.object(
            DiscoveryAgentConfig,
            "create_client",
            side_effect=RuntimeError("connection refused"),
        ):
            server._init_server()

        assert server._config is not None
        assert server._client is None
        assert server._config_error is not None
        assert "Client creation failed" in server._config_error


# ===========================================================================
# Test: module-level __main__ guard
# ===========================================================================


class TestModuleRunnable:
    """Verify server can be invoked as a module."""

    def test_server_module_has_main_guard(self):
        source = importlib.util.find_spec("snow_discovery_agent.server")
        assert source is not None
        assert source.origin is not None
        with open(source.origin) as f:
            content = f.read()
        assert 'if __name__ == "__main__":' in content
        assert "main()" in content


# ===========================================================================
# Test: package exports
# ===========================================================================


class TestPackageExports:
    """Verify server components are exported from the package."""

    def test_mcp_exported(self):
        from snow_discovery_agent import mcp

        assert mcp is not None

    def test_get_client_exported(self):
        from snow_discovery_agent import get_client

        assert callable(get_client)

    def test_get_server_config_exported(self):
        from snow_discovery_agent import get_server_config

        assert callable(get_server_config)

    def test_handle_tool_error_exported(self):
        from snow_discovery_agent import handle_tool_error

        assert callable(handle_tool_error)
