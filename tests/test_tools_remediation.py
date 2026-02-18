"""Tests for the remediate_discovery_failures MCP tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.tools.remediation import (
    _categorize_error,
    remediate_discovery_failures,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

SAMPLE_STATUS: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Failed Scan",
    "state": "Error",
    "source": "",
    "dscl_status": "",
    "log": "Scan failed",
    "started": "2026-02-18 10:00:00",
    "completed": "2026-02-18 10:05:00",
    "ci_count": "0",
    "ip_address": "10.0.0.5",
    "mid_server": "MID1",
}

CRED_ERROR_LOG: dict[str, Any] = {
    "sys_id": "1234567890abcdef1234567890abcdef",
    "status": VALID_SYS_ID,
    "level": "Error",
    "message": "Authentication failed for credential SSH-Admin",
    "source": "Discovery",
    "created_on": "2026-02-18 10:01:00",
}

NET_ERROR_LOG: dict[str, Any] = {
    "sys_id": "abcdef1234567890abcdef1234567890",
    "status": VALID_SYS_ID,
    "level": "Error",
    "message": "Connection timeout for 10.0.0.5",
    "source": "Discovery",
    "created_on": "2026-02-18 10:02:00",
}

CLASS_ERROR_LOG: dict[str, Any] = {
    "sys_id": "fedcba9876543210fedcba9876543210",
    "status": VALID_SYS_ID,
    "level": "Warning",
    "message": "Classification failed: unclassified device",
    "source": "Discovery",
    "created_on": "2026-02-18 10:03:00",
}

SAMPLE_CREDENTIAL: dict[str, Any] = {
    "sys_id": "c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1",
    "name": "SSH-Admin",
    "type": "SSH",
    "active": "true",
    "tag": "",
    "order": "100",
    "affinity": "",
}

INACTIVE_CREDENTIAL: dict[str, Any] = {
    **SAMPLE_CREDENTIAL,
    "sys_id": "d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2",
    "name": "Old Cred",
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


class TestCategorizeError:
    def test_credential(self):
        assert _categorize_error("authentication failed") == "credential"

    def test_network(self):
        assert _categorize_error("connection timeout") == "network"

    def test_classification(self):
        assert _categorize_error("classification failed") == "classification"

    def test_other(self):
        assert _categorize_error("generic error") == "other"


class TestInvalidAction:
    def test_invalid(self, patch_get_client):
        result = remediate_discovery_failures(action="invalid")
        assert result["success"] is False


class TestDiagnoseAction:
    def test_diagnose_success(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.return_value = [
            CRED_ERROR_LOG, NET_ERROR_LOG, CLASS_ERROR_LOG,
        ]

        result = remediate_discovery_failures(
            action="diagnose", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["total_errors"] == 3
        assert data["primary_root_cause"] in (
            "credential", "network", "classification",
        )
        assert len(data["suggestions"]) > 0

    def test_diagnose_no_errors(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.return_value = []

        result = remediate_discovery_failures(
            action="diagnose", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["total_errors"] == 0
        assert result["data"]["primary_root_cause"] == "none"


class TestCredentialFixAction:
    def test_credential_fix_dry_run(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.side_effect = [
            [CRED_ERROR_LOG],  # Error logs
            [SAMPLE_CREDENTIAL, INACTIVE_CREDENTIAL],  # Credentials
        ]

        result = remediate_discovery_failures(
            action="credential_fix",
            scan_sys_id=VALID_SYS_ID,
            confirm=False,
        )

        assert result["success"] is True
        data = result["data"]
        assert data["dry_run"] is True
        assert data["credential_errors"] == 1
        assert data["inactive_credentials"] == 1
        assert len(data["recommendations"]) > 0

    def test_credential_fix_with_confirm(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.side_effect = [
            [],  # No credential errors
            [SAMPLE_CREDENTIAL],  # All active
        ]

        result = remediate_discovery_failures(
            action="credential_fix",
            scan_sys_id=VALID_SYS_ID,
            confirm=True,
        )

        assert result["success"] is True
        assert result["data"]["dry_run"] is False


class TestNetworkFixAction:
    def test_network_fix(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.side_effect = [
            [NET_ERROR_LOG],  # Error logs
            [{"sys_id": "r1", "name": "Range 1"}],  # Ranges
        ]

        result = remediate_discovery_failures(
            action="network_fix", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["network_errors"] == 1

    def test_network_fix_no_ranges(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.side_effect = [
            [],  # No errors
            [],  # No ranges
        ]

        result = remediate_discovery_failures(
            action="network_fix", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert any(
            "No active" in r["description"]
            for r in result["data"]["recommendations"]
        )


class TestClassificationFixAction:
    def test_classification_fix(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.side_effect = [
            [CLASS_ERROR_LOG],  # Error logs
            [{"sys_id": "p1", "name": "Linux"}],  # Patterns
        ]

        result = remediate_discovery_failures(
            action="classification_fix", scan_sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert result["data"]["classification_errors"] == 1


class TestBulkRemediateAction:
    def test_bulk_remediate_dry_run(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.return_value = [CRED_ERROR_LOG]

        result = remediate_discovery_failures(
            action="bulk_remediate",
            scan_sys_id=VALID_SYS_ID,
            remediation_type="re_scan",
            confirm=False,
        )

        assert result["success"] is True
        assert result["data"]["dry_run"] is True
        assert result["data"]["total_items"] > 0

    def test_bulk_remediate_with_targets(self, patch_get_client, mock_client):
        mock_client.get_table_record.return_value = SAMPLE_STATUS
        mock_client.query_table.return_value = []

        result = remediate_discovery_failures(
            action="bulk_remediate",
            scan_sys_id=VALID_SYS_ID,
            remediation_type="re_scan",
            target_items=["10.0.0.1", "10.0.0.2"],
        )

        assert result["success"] is True
        assert result["data"]["total_items"] == 2

    def test_bulk_remediate_missing_type(self, patch_get_client, mock_client):
        result = remediate_discovery_failures(
            action="bulk_remediate",
            scan_sys_id=VALID_SYS_ID,
        )
        assert result["success"] is False
        assert "remediation_type" in result["message"]
