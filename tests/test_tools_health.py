"""Tests for the get_discovery_health MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import ServiceNowError
from snow_discovery_agent.tools.health import (
    _VALID_PERIODS,
    get_discovery_health,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

COMPLETED_SCAN: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Scan 1",
    "state": "Completed",
    "started": "2026-02-18 10:00:00",
    "completed": "2026-02-18 10:30:00",
    "ci_count": "42",
    "ip_address": "10.0.0.1",
}

ERROR_SCAN: dict[str, Any] = {
    "sys_id": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
    "name": "Scan 2",
    "state": "Error",
    "started": "2026-02-18 11:00:00",
    "completed": "2026-02-18 11:05:00",
    "ci_count": "0",
    "ip_address": "10.0.0.2",
}

ACTIVE_SCHEDULE: dict[str, Any] = {
    "sys_id": "s1s1s1s1s1s1s1s1s1s1s1s1s1s1s1s1",
    "name": "Schedule 1",
    "active": "true",
    "discover": "IP",
}

ACTIVE_CREDENTIAL: dict[str, Any] = {
    "sys_id": "c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1",
    "name": "SSH Cred",
    "active": "true",
    "type": "SSH",
}

ACTIVE_RANGE: dict[str, Any] = {
    "sys_id": "r1r1r1r1r1r1r1r1r1r1r1r1r1r1r1r1",
    "name": "Office Range",
    "active": "true",
    "type": "IP Range",
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


def _setup_healthy_responses(mock_client):
    """Configure mock client to return healthy data."""
    mock_client.query_table.side_effect = [
        [COMPLETED_SCAN],                # Scans
        [ACTIVE_SCHEDULE],               # Schedules
        [ACTIVE_CREDENTIAL],             # Credentials
        [ACTIVE_RANGE],                  # Ranges
    ]


def _setup_unhealthy_responses(mock_client):
    """Configure mock client to return unhealthy data."""
    mock_client.query_table.side_effect = [
        [COMPLETED_SCAN, ERROR_SCAN],    # Scans (50% failure)
        [ACTIVE_SCHEDULE],               # Schedules
        [ACTIVE_CREDENTIAL],             # Credentials
        [ACTIVE_RANGE],                  # Ranges
        [{"sys_id": "e1", "message": "Auth failure", "level": "Error"}],  # Error logs
    ]


class TestInvalidPeriod:
    def test_invalid_period(self, patch_get_client):
        result = get_discovery_health(period="invalid")
        assert result["success"] is False
        assert "VALIDATION_ERROR" in result["error"]

    def test_valid_periods(self):
        assert "day" in _VALID_PERIODS
        assert "week" in _VALID_PERIODS
        assert "month" in _VALID_PERIODS


class TestClientUnavailable:
    def test_client_error(self):
        with patch(
            "snow_discovery_agent.server.get_client",
            side_effect=ServiceNowError(
                message="Not configured", error_code="CLIENT_NOT_CONFIGURED"
            ),
        ):
            result = get_discovery_health()
            assert result["success"] is False


class TestHealthyInstance:
    def test_healthy_score(self, patch_get_client, mock_client):
        _setup_healthy_responses(mock_client)

        result = get_discovery_health(period="week")

        assert result["success"] is True
        data = result["data"]
        assert data["status"] == "healthy"
        assert data["summary"]["health_score"] >= 80
        assert data["summary"]["total_scans"] == 1
        assert data["summary"]["successful"] == 1
        assert data["summary"]["failed"] == 0

    def test_sub_metrics_present(self, patch_get_client, mock_client):
        _setup_healthy_responses(mock_client)

        result = get_discovery_health()

        data = result["data"]
        assert "scan_health" in data["sub_metrics"]
        assert "schedule_health" in data["sub_metrics"]
        assert "credential_health" in data["sub_metrics"]
        assert "range_health" in data["sub_metrics"]

    def test_recommendations_included(self, patch_get_client, mock_client):
        _setup_healthy_responses(mock_client)

        result = get_discovery_health(include_recommendations=True)

        assert "recommendations" in result["data"]
        assert isinstance(result["data"]["recommendations"], list)

    def test_recommendations_excluded(self, patch_get_client, mock_client):
        _setup_healthy_responses(mock_client)

        result = get_discovery_health(include_recommendations=False)

        assert result["data"]["recommendations"] == []


class TestUnhealthyInstance:
    def test_error_rate_affects_score(self, patch_get_client, mock_client):
        _setup_unhealthy_responses(mock_client)

        result = get_discovery_health(period="week")

        assert result["success"] is True
        data = result["data"]
        summary = data["summary"]
        assert summary["failed"] == 1
        assert summary["error_rate"] == 50.0
        assert summary["health_score"] < 100

    def test_top_errors_populated(self, patch_get_client, mock_client):
        _setup_unhealthy_responses(mock_client)

        result = get_discovery_health()

        data = result["data"]
        summary = data["summary"]
        assert len(summary["top_errors"]) > 0


class TestPeriodBehavior:
    def test_day_period(self, patch_get_client, mock_client):
        _setup_healthy_responses(mock_client)

        result = get_discovery_health(period="day")

        assert result["success"] is True
        assert result["data"]["summary"]["period"] == "day"

    def test_month_period(self, patch_get_client, mock_client):
        _setup_healthy_responses(mock_client)

        result = get_discovery_health(period="month")

        assert result["success"] is True
        assert result["data"]["summary"]["period"] == "month"


class TestNoData:
    def test_no_scans(self, patch_get_client, mock_client):
        mock_client.query_table.side_effect = [
            [],  # No scans
            [],  # No schedules
            [],  # No credentials
            [],  # No ranges
        ]

        result = get_discovery_health()

        assert result["success"] is True
        summary = result["data"]["summary"]
        assert summary["total_scans"] == 0
        # With no scans: scan_score=100 (0% error rate), schedule/cred/range=50 each
        # Weighted: 100*0.4 + 50*0.2 + 50*0.2 + 50*0.2 = 70
        assert summary["health_score"] == 70
