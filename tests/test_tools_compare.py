"""Tests for the compare_discovery_runs MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowNotFoundError,
)
from snow_discovery_agent.models import DiscoveryStatus
from snow_discovery_agent.tools.compare import (
    _compute_duration,
    compare_discovery_runs,
)

VALID_SYS_ID_A = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
VALID_SYS_ID_B = "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3"
SCHEDULE_SYS_ID = "1111111122222222333333334444444a"

SCAN_A: dict[str, Any] = {
    "sys_id": VALID_SYS_ID_A,
    "name": "Scan A",
    "state": "Completed",
    "source": SCHEDULE_SYS_ID,
    "dscl_status": "",
    "log": "",
    "started": "2026-02-17 10:00:00",
    "completed": "2026-02-17 10:30:00",
    "ci_count": "40",
    "ip_address": "10.0.0.1",
    "mid_server": "MID1",
}

SCAN_B: dict[str, Any] = {
    "sys_id": VALID_SYS_ID_B,
    "name": "Scan B",
    "state": "Completed",
    "source": SCHEDULE_SYS_ID,
    "dscl_status": "",
    "log": "",
    "started": "2026-02-18 10:00:00",
    "completed": "2026-02-18 10:25:00",
    "ci_count": "45",
    "ip_address": "10.0.0.1",
    "mid_server": "MID1",
}

ERROR_LOG_A: dict[str, Any] = {
    "sys_id": "e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1",
    "status": VALID_SYS_ID_A,
    "level": "Error",
    "message": "Auth failure for SSH credential",
    "source": "Discovery",
    "created_on": "2026-02-17 10:15:00",
}

ERROR_LOG_B: dict[str, Any] = {
    "sys_id": "e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2",
    "status": VALID_SYS_ID_B,
    "level": "Error",
    "message": "Network timeout for 10.0.0.5",
    "source": "Discovery",
    "created_on": "2026-02-18 10:15:00",
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


class TestComputeDuration:
    def test_with_both_timestamps(self):
        status = DiscoveryStatus.from_snow(SCAN_A)
        assert _compute_duration(status) == 1800.0  # 30 minutes

    def test_without_completed(self):
        no_complete = {**SCAN_A, "completed": ""}
        status = DiscoveryStatus.from_snow(no_complete)
        assert _compute_duration(status) == 0.0


class TestInvalidAction:
    def test_invalid(self, patch_get_client):
        result = compare_discovery_runs(action="invalid")
        assert result["success"] is False
        assert "INVALID_ACTION" in result["error"]


class TestCompareAction:
    def test_compare_success(self, patch_get_client, mock_client):
        # Setup: get_table_record for scan A and B, query_table for errors A and B
        mock_client.get_table_record.side_effect = [SCAN_A, SCAN_B]
        mock_client.query_table.side_effect = [
            [ERROR_LOG_A],  # Errors for scan A
            [ERROR_LOG_B],  # Errors for scan B
        ]

        result = compare_discovery_runs(
            action="compare",
            scan_a_sys_id=VALID_SYS_ID_A,
            scan_b_sys_id=VALID_SYS_ID_B,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["scan_a_sys_id"] == VALID_SYS_ID_A
        assert data["scan_b_sys_id"] == VALID_SYS_ID_B
        assert data["delta_ci_count"] == 5  # 45 - 40
        assert data["scan_a_state"] == "Completed"
        assert data["scan_b_state"] == "Completed"

    def test_compare_error_deltas(self, patch_get_client, mock_client):
        mock_client.get_table_record.side_effect = [SCAN_A, SCAN_B]
        # Scan A has auth error, Scan B has network error (different errors)
        mock_client.query_table.side_effect = [
            [ERROR_LOG_A],  # Errors for scan A
            [ERROR_LOG_B],  # Errors for scan B
        ]

        result = compare_discovery_runs(
            action="compare",
            scan_a_sys_id=VALID_SYS_ID_A,
            scan_b_sys_id=VALID_SYS_ID_B,
        )

        data = result["data"]
        # Auth error was in A but not B -> resolved
        assert len(data["errors_resolved"]) > 0
        # Network error was in B but not A -> new
        assert len(data["errors_new"]) > 0

    def test_compare_missing_scan_a(self, patch_get_client):
        result = compare_discovery_runs(
            action="compare",
            scan_b_sys_id=VALID_SYS_ID_B,
        )
        assert result["success"] is False

    def test_compare_missing_scan_b(self, patch_get_client):
        result = compare_discovery_runs(
            action="compare",
            scan_a_sys_id=VALID_SYS_ID_A,
        )
        assert result["success"] is False

    def test_compare_not_found(self, patch_get_client, mock_client):
        mock_client.get_table_record.side_effect = ServiceNowNotFoundError(
            message="Not found"
        )
        result = compare_discovery_runs(
            action="compare",
            scan_a_sys_id=VALID_SYS_ID_A,
            scan_b_sys_id=VALID_SYS_ID_B,
        )
        assert result["success"] is False


class TestSequentialAction:
    def test_sequential_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SCAN_B, SCAN_A]  # Newer first

        result = compare_discovery_runs(
            action="sequential",
            schedule_sys_id=SCHEDULE_SYS_ID,
            last_n=5,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["scans_analyzed"] == 2
        assert len(data["comparisons"]) == 1
        assert data["comparisons"][0]["delta_ci_count"] == 5  # 45 - 40
        assert data["trend"] == "improving"

    def test_sequential_single_scan(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SCAN_A]

        result = compare_discovery_runs(
            action="sequential",
            schedule_sys_id=SCHEDULE_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["scans_found"] == 1
        assert result["data"]["comparisons"] == []

    def test_sequential_no_scans(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []

        result = compare_discovery_runs(
            action="sequential",
            schedule_sys_id=SCHEDULE_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["scans_found"] == 0

    def test_sequential_missing_schedule(self, patch_get_client):
        result = compare_discovery_runs(action="sequential")
        assert result["success"] is False

    def test_sequential_degrading_trend(self, patch_get_client, mock_client):
        # Newer scan has fewer CIs -> degrading
        degrading_b = {**SCAN_B, "ci_count": "30"}
        mock_client.query_table.return_value = [degrading_b, SCAN_A]

        result = compare_discovery_runs(
            action="sequential",
            schedule_sys_id=SCHEDULE_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["trend"] == "degrading"
