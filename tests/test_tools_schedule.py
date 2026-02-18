"""Tests for the schedule_discovery_scan MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowError,
    ServiceNowNotFoundError,
)
from snow_discovery_agent.tools.schedule import (
    _VALID_ACTIONS,
    _VALID_DISCOVER_TYPES,
    SCHEDULE_TABLE,
    _validate_sys_id,
    schedule_discovery_scan,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
VALID_SYS_ID_2 = "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3"

SAMPLE_SCHEDULE_RECORD: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Daily IP Scan",
    "active": "true",
    "discover": "IP",
    "max_run_time": "02:00:00",
    "run_dayofweek": "Monday,Wednesday,Friday",
    "run_time": "03:00:00",
    "mid_select_method": "Auto",
    "location": "",
}

SAMPLE_STATUS_RECORD: dict[str, Any] = {
    "sys_id": VALID_SYS_ID_2,
    "name": "Daily IP Scan - 2026-02-18",
    "state": "Active",
    "source": VALID_SYS_ID,
    "dscl_status": "",
    "log": "",
    "started": "2026-02-18 10:00:00",
    "completed": "",
    "ci_count": "0",
    "ip_address": "10.0.0.1",
    "mid_server": "MID1",
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


class TestValidateSysId:
    def test_valid_sys_id(self):
        assert _validate_sys_id(VALID_SYS_ID, "test") == VALID_SYS_ID

    def test_none_raises(self):
        with pytest.raises(ValueError, match="required"):
            _validate_sys_id(None, "test")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="required"):
            _validate_sys_id("", "test")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            _validate_sys_id("not-a-sys-id", "test")

    def test_whitespace_stripped(self):
        assert _validate_sys_id(f"  {VALID_SYS_ID}  ", "test") == VALID_SYS_ID


class TestScheduleDiscoveryScanInvalidAction:
    def test_invalid_action(self, patch_get_client):
        result = schedule_discovery_scan(action="invalid")
        assert result["success"] is False
        assert "INVALID_ACTION" in result["error"]

    def test_valid_actions_exist(self):
        assert "trigger" in _VALID_ACTIONS
        assert "create" in _VALID_ACTIONS


class TestScheduleDiscoveryScanClientUnavailable:
    def test_client_not_configured(self):
        with patch(
            "snow_discovery_agent.server.get_client",
            side_effect=ServiceNowError(message="Not configured", error_code="CLIENT_NOT_CONFIGURED"),
        ):
            result = schedule_discovery_scan(action="trigger", schedule_sys_id=VALID_SYS_ID)
            assert result["success"] is False
            assert result["error"] == "CLIENT_NOT_CONFIGURED"


class TestTriggerAction:
    def test_trigger_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_SCHEDULE_RECORD
        mock_client.patch.return_value = SAMPLE_SCHEDULE_RECORD
        mock_client.query_table.return_value = [SAMPLE_STATUS_RECORD]

        result = schedule_discovery_scan(action="trigger", schedule_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["action"] == "trigger"
        assert result["data"]["schedule"]["name"] == "Daily IP Scan"
        assert result["data"]["latest_scan"] is not None
        mock_client.patch.assert_called_once_with(
            SCHEDULE_TABLE, VALID_SYS_ID, {"active": "true"}
        )

    def test_trigger_no_recent_scans(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_SCHEDULE_RECORD
        mock_client.patch.return_value = SAMPLE_SCHEDULE_RECORD
        mock_client.query_table.return_value = []

        result = schedule_discovery_scan(action="trigger", schedule_sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["data"]["latest_scan"] is None

    def test_trigger_missing_sys_id(self, patch_get_client):
        result = schedule_discovery_scan(action="trigger")
        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"

    def test_trigger_invalid_sys_id(self, patch_get_client):
        result = schedule_discovery_scan(action="trigger", schedule_sys_id="bad")
        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"

    def test_trigger_not_found(self, patch_get_client, mock_client):
        mock_client.get_table_record.side_effect = ServiceNowNotFoundError(
            message="Not found"
        )
        result = schedule_discovery_scan(action="trigger", schedule_sys_id=VALID_SYS_ID)
        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"


class TestCreateAction:
    def test_create_success(self, patch_get_client, mock_client):
        created_record = {**SAMPLE_SCHEDULE_RECORD, "sys_id": VALID_SYS_ID_2}
        mock_client.post.return_value = created_record

        result = schedule_discovery_scan(
            action="create",
            name="New Schedule",
            discover_type="IP",
        )

        assert result["success"] is True
        assert result["action"] == "create"
        mock_client.post.assert_called_once()

    def test_create_with_all_options(self, patch_get_client, mock_client):
        created_record = {**SAMPLE_SCHEDULE_RECORD, "sys_id": VALID_SYS_ID_2}
        mock_client.post.return_value = created_record

        result = schedule_discovery_scan(
            action="create",
            name="Full Schedule",
            discover_type="CI",
            ip_ranges=[VALID_SYS_ID],
            mid_server="MID1",
            max_run_time="04:00:00",
        )

        assert result["success"] is True
        call_data = mock_client.post.call_args[0][1]
        assert call_data["mid_select_method"] == "Specific"
        assert call_data["mid_server"] == "MID1"

    def test_create_missing_name(self, patch_get_client):
        result = schedule_discovery_scan(action="create", discover_type="IP")
        assert result["success"] is False
        assert "name" in result["message"].lower()

    def test_create_missing_type(self, patch_get_client):
        result = schedule_discovery_scan(action="create", name="Test")
        assert result["success"] is False
        assert "discover_type" in result["message"].lower()

    def test_create_invalid_type(self, patch_get_client):
        result = schedule_discovery_scan(
            action="create", name="Test", discover_type="Invalid"
        )
        assert result["success"] is False
        assert "Invalid discover_type" in result["message"]

    def test_create_invalid_ip_range(self, patch_get_client):
        result = schedule_discovery_scan(
            action="create",
            name="Test",
            discover_type="IP",
            ip_ranges=["bad-id"],
        )
        assert result["success"] is False

    def test_create_servicenow_error(self, patch_get_client, mock_client):
        mock_client.post.side_effect = ServiceNowError(
            message="Table write error", error_code="SERVICENOW_API_ERROR"
        )
        result = schedule_discovery_scan(
            action="create", name="Test", discover_type="IP"
        )
        assert result["success"] is False
        assert result["error"] == "SERVICENOW_API_ERROR"

    def test_valid_discover_types(self):
        assert "IP" in _VALID_DISCOVER_TYPES
        assert "CI" in _VALID_DISCOVER_TYPES
        assert "Network" in _VALID_DISCOVER_TYPES
