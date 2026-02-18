"""Tests for the analyze_discovery_results MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.tools.analysis import (
    _categorize_error,
    analyze_discovery_results,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

SAMPLE_STATUS: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Daily Scan",
    "state": "Completed",
    "source": "",
    "dscl_status": "",
    "log": "",
    "started": "2026-02-18 10:00:00",
    "completed": "2026-02-18 10:30:00",
    "ci_count": "42",
    "ip_address": "10.0.0.1",
    "mid_server": "MID1",
}

SAMPLE_LOG_ERROR: dict[str, Any] = {
    "sys_id": "1234567890abcdef1234567890abcdef",
    "status": VALID_SYS_ID,
    "level": "Error",
    "message": "Authentication failed for credential SSH-Admin",
    "source": "Discovery",
    "created_on": "2026-02-18 10:15:00",
}

SAMPLE_LOG_WARNING: dict[str, Any] = {
    "sys_id": "abcdef1234567890abcdef1234567890",
    "status": VALID_SYS_ID,
    "level": "Warning",
    "message": "Connection timeout for 10.0.0.5",
    "source": "Discovery",
    "created_on": "2026-02-18 10:16:00",
}


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def patch_get_client(mock_client):
    with patch(
        "snow_discovery_agent.server.get_client",
        return_value=mock_client,
    ):
        yield mock_client


class TestCategorizeError:
    def test_credential_failure(self):
        assert _categorize_error("Authentication failed") == "credential_failure"

    def test_network_timeout(self):
        assert _categorize_error("Connection timeout") == "network_timeout"

    def test_classification_failure(self):
        assert _categorize_error("Classification failed") == "classification_failure"

    def test_port_scan_failure(self):
        assert _categorize_error("Port scan failed") == "port_scan_failure"

    def test_snmp_failure(self):
        # "SNMP community string error" matches snmp before timeout
        assert _categorize_error("SNMP community string error") == "snmp_failure"

    def test_ssh_failure(self):
        assert _categorize_error("SSH key exchange failed") == "ssh_failure"

    def test_wmi_failure(self):
        assert _categorize_error("WMI connection failed") == "wmi_failure"

    def test_other(self):
        assert _categorize_error("Some unknown error") == "other"


class TestInvalidAction:
    def test_invalid(self, patch_get_client):
        result = analyze_discovery_results(action="invalid")
        assert result["success"] is False
        assert "INVALID_ACTION" in result["error"]


class TestAnalyzeAction:
    def test_analyze_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.return_value = [
            SAMPLE_LOG_ERROR, SAMPLE_LOG_WARNING,
        ]

        result = analyze_discovery_results(
            action="analyze", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["ci_count"] == 42
        assert data["duration_seconds"] == 1800.0  # 30 minutes
        assert data["log_summary"]["errors"] == 1
        assert data["log_summary"]["warnings"] == 1

    def test_analyze_missing_sys_id(self, patch_get_client):
        result = analyze_discovery_results(action="analyze")
        assert result["success"] is False


class TestErrorsAction:
    def test_errors_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [
            SAMPLE_LOG_ERROR, SAMPLE_LOG_WARNING,
        ]

        result = analyze_discovery_results(
            action="errors", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["total_errors"] == 2
        assert len(data["by_category"]) > 0


class TestTrendAction:
    def test_trend_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [
            SAMPLE_STATUS,
            {**SAMPLE_STATUS, "ci_count": "30", "state": "Error"},
        ]

        result = analyze_discovery_results(action="trend", last_n_scans=10)

        assert result["success"] is True
        data = result["data"]
        assert data["scan_count"] == 2
        assert data["success_rate_percent"] == 50.0

    def test_trend_no_scans(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []

        result = analyze_discovery_results(action="trend")

        assert result["success"] is True
        assert result["data"]["trend"] == "no_data"

    def test_trend_with_schedule(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_STATUS]

        result = analyze_discovery_results(
            action="trend", schedule_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True


class TestCoverageAction:
    def test_coverage_success(self, patch_get_client, mock_client):
        mock_client.query_table.side_effect = [
            [SAMPLE_STATUS],  # Scan records
            [{"sys_id": "range1", "name": "R1"}],  # Range records
        ]

        result = analyze_discovery_results(
            action="coverage", schedule_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["unique_ips_discovered"] == 1
        assert data["configured_ranges"] == 1

    def test_coverage_missing_schedule(self, patch_get_client):
        result = analyze_discovery_results(action="coverage")
        assert result["success"] is False
