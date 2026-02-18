"""Tests for the manage_discovery_ranges MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.tools.ranges import (
    _validate_cidr,
    _validate_ip_address,
    _validate_ip_range,
    manage_discovery_ranges,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

SAMPLE_RANGE_RECORD: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Office Network",
    "type": "IP Range",
    "active": "true",
    "range_start": "10.0.0.1",
    "range_end": "10.0.0.254",
    "include": "true",
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


class TestValidateIpAddress:
    def test_valid_ipv4(self):
        assert _validate_ip_address("10.0.0.1", "test") == "10.0.0.1"

    def test_valid_ipv6(self):
        result = _validate_ip_address("::1", "test")
        assert result == "::1"

    def test_invalid_ip(self):
        with pytest.raises(ValueError, match="Invalid IP"):
            _validate_ip_address("not-an-ip", "test")

    def test_whitespace_stripped(self):
        assert _validate_ip_address("  10.0.0.1  ", "test") == "10.0.0.1"


class TestValidateCidr:
    def test_valid_ipv4_cidr(self):
        assert _validate_cidr("10.0.0.0/24", "test") == "10.0.0.0/24"

    def test_valid_ipv6_cidr(self):
        assert _validate_cidr("fe80::/10", "test") == "fe80::/10"

    def test_invalid_cidr(self):
        with pytest.raises(ValueError, match="Invalid CIDR"):
            _validate_cidr("not-a-cidr", "test")


class TestValidateIpRange:
    def test_valid_range(self):
        _validate_ip_range("10.0.0.1", "10.0.0.254")

    def test_end_less_than_start(self):
        with pytest.raises(ValueError, match="must be >="):
            _validate_ip_range("10.0.0.254", "10.0.0.1")

    def test_same_ip(self):
        _validate_ip_range("10.0.0.1", "10.0.0.1")

    def test_family_mismatch(self):
        with pytest.raises(ValueError, match="family mismatch"):
            _validate_ip_range("10.0.0.1", "::1")


class TestInvalidAction:
    def test_invalid_action(self, patch_get_client):
        result = manage_discovery_ranges(action="invalid")
        assert result["success"] is False
        assert "INVALID_ACTION" in result["error"]


class TestValidateAction:
    def test_validate_ip_range_success(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="IP Range",
            range_start="10.0.0.1",
            range_end="10.0.0.254",
        )
        assert result["success"] is True
        assert result["action"] == "validate"

    def test_validate_ip_network_success(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="IP Network",
            range_start="10.0.0.0/24",
        )
        assert result["success"] is True

    def test_validate_ip_address_success(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="IP Address",
            range_start="10.0.0.1",
        )
        assert result["success"] is True

    def test_validate_missing_type(self):
        result = manage_discovery_ranges(
            action="validate",
            range_start="10.0.0.1",
        )
        assert result["success"] is False
        assert "issues" in result["data"]

    def test_validate_invalid_type(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="Bad Type",
            range_start="10.0.0.1",
        )
        assert result["success"] is False

    def test_validate_invalid_ip(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="IP Address",
            range_start="not-an-ip",
        )
        assert result["success"] is False

    def test_validate_ip_range_missing_end(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="IP Range",
            range_start="10.0.0.1",
        )
        assert result["success"] is False

    def test_validate_ip_range_end_less_start(self):
        result = manage_discovery_ranges(
            action="validate",
            range_type="IP Range",
            range_start="10.0.0.254",
            range_end="10.0.0.1",
        )
        assert result["success"] is False


class TestListAction:
    def test_list_success(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = [SAMPLE_RANGE_RECORD]

        result = manage_discovery_ranges(action="list")

        assert result["success"] is True
        assert len(result["data"]) == 1

    def test_list_with_filters(self, patch_get_client, mock_client):
        mock_client.query_table.return_value = []

        result = manage_discovery_ranges(
            action="list", filter_type="IP Range", filter_active=True
        )

        assert result["success"] is True


class TestGetAction:
    def test_get_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_RANGE_RECORD

        result = manage_discovery_ranges(action="get", sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["data"]["name"] == "Office Network"

    def test_get_missing_sys_id(self, patch_get_client):
        result = manage_discovery_ranges(action="get")
        assert result["success"] is False


class TestCreateAction:
    def test_create_ip_range(self, patch_get_client, mock_client):
        mock_client.post.return_value = SAMPLE_RANGE_RECORD

        result = manage_discovery_ranges(
            action="create",
            name="Test Range",
            range_type="IP Range",
            range_start="10.0.0.1",
            range_end="10.0.0.254",
        )

        assert result["success"] is True
        assert result["action"] == "create"

    def test_create_ip_network(self, patch_get_client, mock_client):
        network_record = {
            **SAMPLE_RANGE_RECORD,
            "type": "IP Network",
            "range_start": "10.0.0.0/24",
            "range_end": "",
        }
        mock_client.post.return_value = network_record

        result = manage_discovery_ranges(
            action="create",
            name="Test Network",
            range_type="IP Network",
            range_start="10.0.0.0/24",
        )

        assert result["success"] is True

    def test_create_missing_name(self, patch_get_client):
        result = manage_discovery_ranges(
            action="create",
            range_type="IP Range",
            range_start="10.0.0.1",
            range_end="10.0.0.254",
        )
        assert result["success"] is False

    def test_create_ip_range_missing_end(self, patch_get_client):
        result = manage_discovery_ranges(
            action="create",
            name="Test",
            range_type="IP Range",
            range_start="10.0.0.1",
        )
        assert result["success"] is False


class TestUpdateAction:
    def test_update_success(self, patch_get_client, mock_client):
        mock_client.patch.return_value = SAMPLE_RANGE_RECORD

        result = manage_discovery_ranges(
            action="update",
            sys_id=VALID_SYS_ID,
            name="Updated Range",
        )

        assert result["success"] is True

    def test_update_no_fields(self, patch_get_client):
        result = manage_discovery_ranges(
            action="update",
            sys_id=VALID_SYS_ID,
        )
        assert result["success"] is False
        assert "At least one field" in result["message"]


class TestDeleteAction:
    def test_delete_success(self, patch_get_client, mock_client):
        mock_client.delete.return_value = True

        result = manage_discovery_ranges(
            action="delete",
            sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["sys_id"] == VALID_SYS_ID
