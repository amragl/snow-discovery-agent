"""Tests for the get_discovery_status MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowError,
    ServiceNowNotFoundError,
)
from snow_discovery_agent.tools.status import (
    _VALID_STATES,
    _build_list_query,
    get_discovery_status,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

SAMPLE_STATUS_RECORD: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Daily Scan - 2026-02-18",
    "state": "Completed",
    "source": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
    "dscl_status": "",
    "log": "Scan completed successfully",
    "started": "2026-02-18 10:00:00",
    "completed": "2026-02-18 10:30:00",
    "ci_count": "42",
    "ip_address": "10.0.0.0/24",
    "mid_server": "MID1",
}

SAMPLE_LOG_RECORD: dict[str, Any] = {
    "sys_id": "1234567890abcdef1234567890abcdef",
    "status": VALID_SYS_ID,
    "level": "Error",
    "message": "Connection timeout",
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


class TestBuildListQuery:
    def test_no_filters(self):
        assert _build_list_query() is None

    def test_state_filter(self):
        q = _build_list_query(state="Completed")
        assert q == "state=Completed"

    def test_date_filters(self):
        q = _build_list_query(date_from="2026-01-01", date_to="2026-02-01")
        assert "started>=2026-01-01" in q
        assert "started<=2026-02-01" in q

    def test_combined_filters(self):
        q = _build_list_query(state="Active", date_from="2026-01-01")
        assert "state=Active" in q
        assert "started>=2026-01-01" in q


class TestGetDiscoveryStatusInvalidAction:
    def test_invalid_action(self, patch_get_client):
        result = get_discovery_status(action="invalid")
        assert result["success"] is False
        assert "INVALID_ACTION" in result["error"]


class TestGetDiscoveryStatusClientUnavailable:
    def test_client_not_configured(self):
        with patch(
            "snow_discovery_agent.server.get_client",
            side_effect=ServiceNowError(message="Not configured", error_code="CLIENT_NOT_CONFIGURED"),
        ):
            result = get_discovery_status(action="get", scan_sys_id=VALID_SYS_ID)
            assert result["success"] is False


class TestGetAction:
    def test_get_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS_RECORD

        result = get_discovery_status(action="get", scan_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["action"] == "get"
        assert result["data"]["state"] == "Completed"
        assert result["data"]["ci_count"] == 42

    def test_get_missing_sys_id(self, patch_get_client):
        result = get_discovery_status(action="get")
        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"

    def test_get_not_found(self, patch_get_client, mock_client):
        mock_client.get_table_record.side_effect = ServiceNowNotFoundError(message="Not found")
        result = get_discovery_status(action="get", scan_sys_id=VALID_SYS_ID)
        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"


class TestListAction:
    def test_list_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_STATUS_RECORD]

        result = get_discovery_status(action="list")

        assert result["success"] is True
        assert result["action"] == "list"
        assert len(result["data"]) == 1

    def test_list_with_state_filter(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []

        result = get_discovery_status(action="list", state="Completed")

        assert result["success"] is True
        call_kwargs = mock_client.query_table.call_args
        assert "Completed" in (call_kwargs[1].get("query") or "")

    def test_list_invalid_state(self, patch_get_client, mock_client):
        result = get_discovery_status(action="list", state="InvalidState")
        assert result["success"] is False
        assert "Invalid state" in result["message"]

    def test_list_empty_results(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []
        result = get_discovery_status(action="list")
        assert result["success"] is True
        assert result["data"] == []


class TestDetailsAction:
    def test_details_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS_RECORD
        mock_client.query_table.return_value = [SAMPLE_LOG_RECORD]

        result = get_discovery_status(action="details", scan_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["action"] == "details"
        assert result["data"]["log_entry_count"] == 1
        assert result["data"]["duration_seconds"] is not None

    def test_details_missing_sys_id(self, patch_get_client):
        result = get_discovery_status(action="details")
        assert result["success"] is False


class TestPollAction:
    def test_poll_completed(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS_RECORD

        result = get_discovery_status(action="poll", scan_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["data"]["is_complete"] is True
        assert result["data"]["state"] == "Completed"

    def test_poll_active(self, patch_get_client, mock_client):
        active_record = {**SAMPLE_STATUS_RECORD, "state": "Active", "completed": ""}
        mock_client.get_table_record.return_value = active_record

        result = get_discovery_status(action="poll", scan_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["data"]["is_complete"] is False

    def test_poll_error_state(self, patch_get_client, mock_client):
        error_record = {**SAMPLE_STATUS_RECORD, "state": "Error"}
        mock_client.get_table_record.return_value = error_record

        result = get_discovery_status(action="poll", scan_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["data"]["is_complete"] is True

    def test_valid_states(self):
        for state in ("Starting", "Active", "Completed", "Cancelled", "Error"):
            assert state in _VALID_STATES
