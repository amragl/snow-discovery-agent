"""
Integration tests for snow-discovery-agent (DISC-019).

These tests exercise the full stack: MCP tool → ServiceNow client → real ServiceNow API.
They are skipped automatically when ServiceNow credentials are not configured.

Run with:
    SERVICENOW_INSTANCE=https://devXXXX.service-now.com \
    SERVICENOW_USERNAME=admin \
    SERVICENOW_PASSWORD=secret \
    pytest tests/integration/ -m integration -v
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Skip guard — skip all tests in this module when credentials absent
# ---------------------------------------------------------------------------

_HAS_CREDENTIALS = bool(
    os.environ.get("SERVICENOW_INSTANCE")
    and os.environ.get("SERVICENOW_USERNAME")
    and os.environ.get("SERVICENOW_PASSWORD")
)

requires_servicenow = pytest.mark.skipif(
    not _HAS_CREDENTIALS,
    reason="Skipped: SERVICENOW_INSTANCE, SERVICENOW_USERNAME, and SERVICENOW_PASSWORD must be set",
)

pytestmark = [pytest.mark.integration, requires_servicenow]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Real ServiceNow client connected to the configured instance."""
    from snow_discovery_agent.client import ServiceNowClient
    from snow_discovery_agent.config import get_config

    cfg = get_config()
    return ServiceNowClient(cfg)


# ---------------------------------------------------------------------------
# Client connectivity
# ---------------------------------------------------------------------------


class TestClientConnectivity:
    """Verify the REST client can reach the ServiceNow instance."""

    def test_get_record_returns_response(self, client):
        """A basic table query returns a response structure (not a connection error)."""
        result = client.get_records(
            table="discovery_schedule",
            fields=["sys_id", "name"],
            limit=1,
        )
        # result is a list (possibly empty — that's fine)
        assert isinstance(result, list)

    def test_client_uses_configured_instance(self, client):
        """Client base URL matches SERVICENOW_INSTANCE environment variable."""
        instance = os.environ["SERVICENOW_INSTANCE"].rstrip("/")
        assert client.base_url.startswith(instance)


# ---------------------------------------------------------------------------
# Discovery schedule operations
# ---------------------------------------------------------------------------


class TestDiscoveryScheduleIntegration:
    """Integration tests for schedule listing and retrieval."""

    def test_list_discovery_schedules_returns_list(self):
        """list_discovery_schedules tool returns a list of schedules."""
        from snow_discovery_agent.tools.schedules_list import list_discovery_schedules

        result = list_discovery_schedules()
        assert "schedules" in result
        assert isinstance(result["schedules"], list)

    def test_get_discovery_status_returns_status(self):
        """get_discovery_status tool returns a status structure."""
        from snow_discovery_agent.tools.status import get_discovery_status

        result = get_discovery_status()
        assert "status" in result or "error" in result


# ---------------------------------------------------------------------------
# Discovery health
# ---------------------------------------------------------------------------


class TestDiscoveryHealthIntegration:
    """Integration tests for the health summary tool."""

    def test_get_discovery_health_returns_summary(self):
        """get_discovery_health returns a structured health summary."""
        from snow_discovery_agent.tools.health import get_discovery_health

        result = get_discovery_health()
        assert isinstance(result, dict)
        # Must not be a bare connection error
        assert result.get("error_code") != "SN_CONNECTION_ERROR"


# ---------------------------------------------------------------------------
# Discovery patterns
# ---------------------------------------------------------------------------


class TestDiscoveryPatternsIntegration:
    """Integration tests for pattern listing."""

    def test_get_discovery_patterns_returns_list(self):
        """get_discovery_patterns tool returns a list of patterns."""
        from snow_discovery_agent.tools.patterns import get_discovery_patterns

        result = get_discovery_patterns(active_only=True, limit=5)
        assert "patterns" in result
        assert isinstance(result["patterns"], list)


# ---------------------------------------------------------------------------
# Discovery ranges
# ---------------------------------------------------------------------------


class TestDiscoveryRangesIntegration:
    """Integration tests for IP range management."""

    def test_list_ranges_returns_list(self):
        """manage_discovery_ranges list action returns IP ranges."""
        from snow_discovery_agent.tools.ranges import manage_discovery_ranges

        result = manage_discovery_ranges(action="list", limit=5)
        assert "ranges" in result
        assert isinstance(result["ranges"], list)


# ---------------------------------------------------------------------------
# Discovery credentials (read-only — never write in integration tests)
# ---------------------------------------------------------------------------


class TestDiscoveryCredentialsIntegration:
    """Integration tests for credential listing (no secret values returned)."""

    def test_list_credentials_returns_list(self):
        """manage_discovery_credentials list returns credentials without secrets."""
        from snow_discovery_agent.tools.credentials import manage_discovery_credentials

        result = manage_discovery_credentials(action="list", limit=5)
        assert "credentials" in result
        creds = result["credentials"]
        assert isinstance(creds, list)
        # Ensure no password / secret fields are exposed
        for cred in creds:
            for sensitive_key in ("password", "passphrase", "private_key", "secret"):
                assert sensitive_key not in cred, (
                    f"Sensitive field '{sensitive_key}' exposed in credential listing"
                )


# ---------------------------------------------------------------------------
# Discovery analysis
# ---------------------------------------------------------------------------


class TestDiscoveryAnalysisIntegration:
    """Integration tests for analyze_discovery_results tool."""

    def test_analyze_returns_structure(self):
        """analyze_discovery_results returns a structured analysis."""
        from snow_discovery_agent.tools.analysis import analyze_discovery_results

        result = analyze_discovery_results(limit=10)
        assert isinstance(result, dict)
        assert result.get("error_code") != "SN_CONNECTION_ERROR"
