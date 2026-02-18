"""Tests for the get_discovery_patterns MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowNotFoundError,
)
from snow_discovery_agent.tools.patterns import (
    _build_list_query,
    get_discovery_patterns,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

SAMPLE_PATTERN: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Linux Server Pattern",
    "active": "true",
    "ci_type": "cmdb_ci_linux_server",
    "criteria": '{"os_name": "Linux"}',
    "description": "Matches Linux servers",
}

SAMPLE_PATTERN_2: dict[str, Any] = {
    "sys_id": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
    "name": "Windows Server Pattern",
    "active": "true",
    "ci_type": "cmdb_ci_win_server",
    "criteria": '{"os_name": "Windows"}',
    "description": "Matches Windows servers",
}

INACTIVE_PATTERN: dict[str, Any] = {
    **SAMPLE_PATTERN,
    "sys_id": "1111111122222222333333334444444",
    "name": "Old Pattern",
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

    def test_ci_type_filter(self):
        q = _build_list_query(ci_type="cmdb_ci_linux_server")
        assert q == "ci_type=cmdb_ci_linux_server"

    def test_active_filter(self):
        q = _build_list_query(active=True)
        assert q == "active=true"

    def test_name_filter(self):
        q = _build_list_query(name_filter="Linux")
        assert q == "nameLIKELinux"


class TestInvalidAction:
    def test_invalid(self, patch_get_client):
        result = get_discovery_patterns(action="invalid")
        assert result["success"] is False


class TestListAction:
    def test_list_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_PATTERN, SAMPLE_PATTERN_2]

        result = get_discovery_patterns(action="list")

        assert result["success"] is True
        assert len(result["data"]) == 2

    def test_list_with_filters(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_PATTERN]

        result = get_discovery_patterns(
            action="list", ci_type="cmdb_ci_linux_server", active=True,
        )

        assert result["success"] is True


class TestGetAction:
    def test_get_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_PATTERN

        result = get_discovery_patterns(
            action="get", pattern_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["name"] == "Linux Server Pattern"

    def test_get_missing_sys_id(self, patch_get_client):
        result = get_discovery_patterns(action="get")
        assert result["success"] is False

    def test_get_not_found(self, patch_get_client, mock_client):
        mock_client.get_table_record.side_effect = ServiceNowNotFoundError(
            message="Not found"
        )
        result = get_discovery_patterns(
            action="get", pattern_sys_id=VALID_SYS_ID,
        )
        assert result["success"] is False


class TestAnalyzeAction:
    def test_analyze_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_PATTERN]

        result = get_discovery_patterns(
            action="analyze", ci_type="cmdb_ci_linux_server",
        )

        assert result["success"] is True
        data = result["data"]
        assert data["ci_type"] == "cmdb_ci_linux_server"
        assert data["total_patterns"] == 1
        assert data["conflicts"] == []

    def test_analyze_detects_conflicts(self, patch_get_client, mock_client):
        # Two active patterns for same CI type
        pattern2 = {
            **SAMPLE_PATTERN,
            "sys_id": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
            "name": "Another Linux Pattern",
        }
        mock_client.query_table.return_value = [SAMPLE_PATTERN, pattern2]

        result = get_discovery_patterns(
            action="analyze", ci_type="cmdb_ci_linux_server",
        )

        assert result["success"] is True
        assert len(result["data"]["conflicts"]) > 0

    def test_analyze_missing_ci_type(self, patch_get_client):
        result = get_discovery_patterns(action="analyze")
        assert result["success"] is False


class TestCoverageAction:
    def test_coverage_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [
            SAMPLE_PATTERN, SAMPLE_PATTERN_2, INACTIVE_PATTERN,
        ]

        result = get_discovery_patterns(action="coverage")

        assert result["success"] is True
        data = result["data"]
        assert data["total_patterns"] == 3
        assert data["total_ci_types"] >= 1
        assert data["covered_types"] >= 1

    def test_coverage_empty(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []

        result = get_discovery_patterns(action="coverage")

        assert result["success"] is True
        assert result["data"]["total_patterns"] == 0
