"""Tests for the list_discovery_schedules MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowError,
    ServiceNowNotFoundError,
)
from snow_discovery_agent.tools.schedules_list import (
    _build_list_query,
    list_discovery_schedules,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

SAMPLE_SCHEDULE: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Daily IP Scan",
    "active": "true",
    "discover": "IP",
    "max_run_time": "02:00:00",
    "run_dayofweek": "Monday",
    "run_time": "03:00:00",
    "mid_select_method": "Auto",
    "location": "",
}

SAMPLE_INACTIVE_SCHEDULE: dict[str, Any] = {
    **SAMPLE_SCHEDULE,
    "sys_id": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
    "name": "Old Schedule",
    "active": "false",
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

    def test_active_filter(self):
        assert _build_list_query(active=True) == "active=true"
        assert _build_list_query(active=False) == "active=false"

    def test_discover_type_filter(self):
        q = _build_list_query(discover_type="IP")
        assert q == "discover=IP"

    def test_name_filter(self):
        q = _build_list_query(name_filter="Daily")
        assert q == "nameLIKEDaily"

    def test_combined_filters(self):
        q = _build_list_query(active=True, discover_type="IP", name_filter="Scan")
        assert "active=true" in q
        assert "discover=IP" in q
        assert "nameLIKEScan" in q


class TestInvalidAction:
    def test_invalid_action(self, patch_get_client):
        result = list_discovery_schedules(action="invalid")
        assert result["success"] is False
        assert "INVALID_ACTION" in result["error"]


class TestListAction:
    def test_list_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_SCHEDULE]

        result = list_discovery_schedules(action="list")

        assert result["success"] is True
        assert result["action"] == "list"
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "Daily IP Scan"

    def test_list_with_filters(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_SCHEDULE]

        result = list_discovery_schedules(
            action="list", active=True, discover_type="IP"
        )

        assert result["success"] is True
        call_kwargs = mock_client.query_table.call_args
        query = call_kwargs[1].get("query", "")
        assert "active=true" in query


class TestGetAction:
    def test_get_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_SCHEDULE

        result = list_discovery_schedules(
            action="get", schedule_sys_id=VALID_SYS_ID
        )

        assert result["success"] is True
        assert result["action"] == "get"
        assert result["data"]["name"] == "Daily IP Scan"

    def test_get_missing_sys_id(self, patch_get_client):
        result = list_discovery_schedules(action="get")
        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"

    def test_get_not_found(self, patch_get_client, mock_client):
        mock_client.get_table_record.side_effect = ServiceNowNotFoundError(
            message="Not found"
        )
        result = list_discovery_schedules(
            action="get", schedule_sys_id=VALID_SYS_ID
        )
        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"


class TestSummaryAction:
    def test_summary_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [
            SAMPLE_SCHEDULE,
            SAMPLE_INACTIVE_SCHEDULE,
        ]

        result = list_discovery_schedules(action="summary")

        assert result["success"] is True
        assert result["action"] == "summary"
        data = result["data"]
        assert data["total_schedules"] == 2
        assert data["active"] == 1
        assert data["inactive"] == 1
        assert "IP" in data["by_type"]

    def test_summary_empty(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []

        result = list_discovery_schedules(action="summary")

        assert result["success"] is True
        assert result["data"]["total_schedules"] == 0


class TestClientUnavailable:
    def test_client_error(self):
        with patch(
            "snow_discovery_agent.server.get_client",
            side_effect=ServiceNowError(
                message="Not configured", error_code="CLIENT_NOT_CONFIGURED"
            ),
        ):
            result = list_discovery_schedules(action="list")
            assert result["success"] is False
