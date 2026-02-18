"""Tests for the manage_discovery_credentials MCP tool.

Covers all five CRUD operations (list, get, create, update, delete),
security filtering (no secrets in responses), input validation,
error handling, and edge cases.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowError,
    ServiceNowNotFoundError,
)
from snow_discovery_agent.tools.credentials import (
    SAFE_FIELDS,
    SECRET_FIELD_PATTERNS,
    TABLE_NAME,
    _build_list_query,
    _is_secret_field,
    _strip_secrets,
    _validate_sys_id,
    manage_discovery_credentials,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
VALID_SYS_ID_2 = "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3"

SAMPLE_CREDENTIAL_RECORD: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Linux SSH Credential",
    "type": "SSH",
    "active": "true",
    "tag": "linux-servers",
    "order": "100",
    "affinity": "",
}

SAMPLE_CREDENTIAL_WITH_SECRETS: dict[str, Any] = {
    "sys_id": VALID_SYS_ID,
    "name": "Linux SSH Credential",
    "type": "SSH",
    "active": "true",
    "tag": "linux-servers",
    "order": "100",
    "affinity": "",
    "password": "super_secret_password",
    "ssh_private_key": "-----BEGIN RSA PRIVATE KEY-----",
    "community_string": "public",
    "passphrase": "my_passphrase",
}


@pytest.fixture
def mock_client():
    """Create a mock ServiceNowClient."""
    client = MagicMock()
    return client


@pytest.fixture
def patch_get_client(mock_client):
    """Patch get_client to return the mock client.

    The credentials tool imports get_client from ..server inside the
    function body, so we patch it at the server module level.
    """
    with patch(
        "snow_discovery_agent.server.get_client",
        return_value=mock_client,
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# _is_secret_field tests
# ---------------------------------------------------------------------------


class TestIsSecretField:
    """Tests for the _is_secret_field helper."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "password",
            "ssh_password",
            "secret",
            "client_secret",
            "private_key",
            "ssh_private_key",
            "community_string",
            "community",
            "passphrase",
            "token",
            "auth_key",
            "key_file",
            "pem",
            "cert_body",
        ],
    )
    def test_detects_secret_fields(self, field_name: str):
        assert _is_secret_field(field_name) is True

    @pytest.mark.parametrize(
        "field_name",
        [
            "sys_id",
            "name",
            "type",
            "active",
            "tag",
            "order",
            "affinity",
            "sys_created_on",
            "sys_updated_on",
            "description",
        ],
    )
    def test_allows_safe_fields(self, field_name: str):
        assert _is_secret_field(field_name) is False

    def test_case_insensitive(self):
        assert _is_secret_field("PASSWORD") is True
        assert _is_secret_field("Password") is True
        assert _is_secret_field("SSH_PRIVATE_KEY") is True


# ---------------------------------------------------------------------------
# _strip_secrets tests
# ---------------------------------------------------------------------------


class TestStripSecrets:
    """Tests for the _strip_secrets helper."""

    def test_removes_known_secret_fields(self):
        result = _strip_secrets(SAMPLE_CREDENTIAL_WITH_SECRETS)
        assert "password" not in result
        assert "ssh_private_key" not in result
        assert "community_string" not in result
        assert "passphrase" not in result

    def test_preserves_safe_fields(self):
        result = _strip_secrets(SAMPLE_CREDENTIAL_WITH_SECRETS)
        for field in SAFE_FIELDS:
            assert field in result

    def test_preserves_metadata_fields(self):
        record = {
            **SAMPLE_CREDENTIAL_RECORD,
            "sys_created_on": "2026-01-01 00:00:00",
            "sys_updated_on": "2026-02-01 00:00:00",
        }
        result = _strip_secrets(record)
        assert "sys_created_on" in result
        assert "sys_updated_on" in result

    def test_empty_record(self):
        result = _strip_secrets({})
        assert result == {}

    def test_record_with_only_secrets(self):
        record = {
            "password": "secret",
            "private_key": "key",
        }
        result = _strip_secrets(record)
        assert "password" not in result
        assert "private_key" not in result


# ---------------------------------------------------------------------------
# _validate_sys_id tests
# ---------------------------------------------------------------------------


class TestValidateSysId:
    """Tests for the _validate_sys_id helper."""

    def test_valid_sys_id(self):
        result = _validate_sys_id(VALID_SYS_ID, "get")
        assert result == VALID_SYS_ID

    def test_none_raises(self):
        with pytest.raises(ValueError, match="sys_id is required"):
            _validate_sys_id(None, "get")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="sys_id is required"):
            _validate_sys_id("", "get")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="sys_id is required"):
            _validate_sys_id("   ", "get")

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="Invalid sys_id format"):
            _validate_sys_id("abc123", "get")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="Invalid sys_id format"):
            _validate_sys_id("a" * 33, "get")

    def test_non_hex_raises(self):
        with pytest.raises(ValueError, match="Invalid sys_id format"):
            _validate_sys_id("g" * 32, "get")

    def test_strips_whitespace(self):
        padded = f"  {VALID_SYS_ID}  "
        result = _validate_sys_id(padded, "get")
        assert result == VALID_SYS_ID

    def test_uppercase_hex_accepted(self):
        upper = VALID_SYS_ID.upper()
        result = _validate_sys_id(upper, "get")
        assert result == upper

    def test_error_includes_action_name(self):
        with pytest.raises(ValueError, match="'delete' action"):
            _validate_sys_id(None, "delete")


# ---------------------------------------------------------------------------
# _build_list_query tests
# ---------------------------------------------------------------------------


class TestBuildListQuery:
    """Tests for the _build_list_query helper."""

    def test_no_filters_returns_none(self):
        assert _build_list_query() is None

    def test_type_filter(self):
        query = _build_list_query(credential_type="SSH")
        assert query == "type=SSH"

    def test_active_true_filter(self):
        query = _build_list_query(active=True)
        assert query == "active=true"

    def test_active_false_filter(self):
        query = _build_list_query(active=False)
        assert query == "active=false"

    def test_tag_filter(self):
        query = _build_list_query(tag="linux-servers")
        assert query == "tag=linux-servers"

    def test_combined_filters(self):
        query = _build_list_query(
            credential_type="SSH",
            active=True,
            tag="linux",
        )
        assert "type=SSH" in query
        assert "active=true" in query
        assert "tag=linux" in query
        assert "^" in query

    def test_empty_type_ignored(self):
        query = _build_list_query(credential_type="")
        assert query is None

    def test_empty_tag_ignored(self):
        query = _build_list_query(tag="")
        assert query is None

    def test_strips_whitespace(self):
        query = _build_list_query(credential_type="  SSH  ", tag="  linux  ")
        assert "type=SSH" in query
        assert "tag=linux" in query


# ---------------------------------------------------------------------------
# manage_discovery_credentials — LIST action
# ---------------------------------------------------------------------------


class TestActionList:
    """Tests for the list action."""

    def test_list_returns_credentials(self, patch_get_client):
        patch_get_client.query_table.return_value = [
            SAMPLE_CREDENTIAL_RECORD,
        ]

        result = manage_discovery_credentials(action="list")

        assert result["success"] is True
        assert result["action"] == "list"
        assert result["error"] is None
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "Linux SSH Credential"
        assert result["data"][0]["type"] == "SSH"

    def test_list_empty_result(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        result = manage_discovery_credentials(action="list")

        assert result["success"] is True
        assert result["data"] == []
        assert "0 credential" in result["message"]

    def test_list_with_type_filter(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        manage_discovery_credentials(action="list", filter_type="SSH")

        call_args = patch_get_client.query_table.call_args
        assert call_args.kwargs.get("query") is not None or call_args[1].get("query") is not None

    def test_list_with_active_filter(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        manage_discovery_credentials(action="list", filter_active=True)

        call_args = patch_get_client.query_table.call_args
        query = call_args.kwargs.get("query") or call_args[1].get("query")
        assert "active=true" in query

    def test_list_with_tag_filter(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        manage_discovery_credentials(action="list", filter_tag="linux")

        call_args = patch_get_client.query_table.call_args
        query = call_args.kwargs.get("query") or call_args[1].get("query")
        assert "tag=linux" in query

    def test_list_with_limit(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        manage_discovery_credentials(action="list", limit=50)

        call_args = patch_get_client.query_table.call_args
        limit = call_args.kwargs.get("limit") or call_args[1].get("limit")
        assert limit == 50

    def test_list_strips_secrets(self, patch_get_client):
        patch_get_client.query_table.return_value = [
            SAMPLE_CREDENTIAL_WITH_SECRETS,
        ]

        result = manage_discovery_credentials(action="list")

        assert result["success"] is True
        cred = result["data"][0]
        assert "password" not in cred
        assert "ssh_private_key" not in cred
        assert "community_string" not in cred
        assert "passphrase" not in cred

    def test_list_multiple_results(self, patch_get_client):
        records = [
            {**SAMPLE_CREDENTIAL_RECORD, "sys_id": VALID_SYS_ID, "name": "Cred 1"},
            {**SAMPLE_CREDENTIAL_RECORD, "sys_id": VALID_SYS_ID_2, "name": "Cred 2"},
        ]
        patch_get_client.query_table.return_value = records

        result = manage_discovery_credentials(action="list")

        assert result["success"] is True
        assert len(result["data"]) == 2

    def test_list_requests_safe_fields(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        manage_discovery_credentials(action="list")

        call_args = patch_get_client.query_table.call_args
        fields = call_args.kwargs.get("fields") or call_args[1].get("fields")
        assert fields == SAFE_FIELDS


# ---------------------------------------------------------------------------
# manage_discovery_credentials — GET action
# ---------------------------------------------------------------------------


class TestActionGet:
    """Tests for the get action."""

    def test_get_returns_credential(self, patch_get_client):
        patch_get_client.get_table_record.return_value = SAMPLE_CREDENTIAL_RECORD

        result = manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)

        assert result["success"] is True
        assert result["action"] == "get"
        assert result["data"]["sys_id"] == VALID_SYS_ID
        assert result["data"]["name"] == "Linux SSH Credential"

    def test_get_strips_secrets(self, patch_get_client):
        patch_get_client.get_table_record.return_value = SAMPLE_CREDENTIAL_WITH_SECRETS

        result = manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)

        assert result["success"] is True
        cred = result["data"]
        assert "password" not in cred
        assert "ssh_private_key" not in cred

    def test_get_missing_sys_id(self, patch_get_client):
        result = manage_discovery_credentials(action="get")

        assert result["success"] is False
        assert "sys_id is required" in result["message"]
        assert result["error"] == "VALIDATION_ERROR"

    def test_get_invalid_sys_id(self, patch_get_client):
        result = manage_discovery_credentials(action="get", sys_id="invalid")

        assert result["success"] is False
        assert "Invalid sys_id format" in result["message"]

    def test_get_not_found(self, patch_get_client):
        patch_get_client.get_table_record.side_effect = ServiceNowNotFoundError(
            message="Record not found: discovery_credential/abc123",
        )

        result = manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"

    def test_get_requests_safe_fields(self, patch_get_client):
        patch_get_client.get_table_record.return_value = SAMPLE_CREDENTIAL_RECORD

        manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)

        call_args = patch_get_client.get_table_record.call_args
        fields = call_args.kwargs.get("fields") or call_args[1].get("fields")
        assert fields == SAFE_FIELDS


# ---------------------------------------------------------------------------
# manage_discovery_credentials — CREATE action
# ---------------------------------------------------------------------------


class TestActionCreate:
    """Tests for the create action."""

    def test_create_with_required_fields(self, patch_get_client):
        patch_get_client.post.return_value = {
            **SAMPLE_CREDENTIAL_RECORD,
            "name": "New SSH Cred",
            "type": "SSH",
        }

        result = manage_discovery_credentials(
            action="create",
            name="New SSH Cred",
            credential_type="SSH",
        )

        assert result["success"] is True
        assert result["action"] == "create"
        assert result["data"]["name"] == "New SSH Cred"

    def test_create_with_all_fields(self, patch_get_client):
        patch_get_client.post.return_value = {
            **SAMPLE_CREDENTIAL_RECORD,
            "name": "Full Cred",
            "type": "SNMP",
            "tag": "network",
            "order": "50",
            "active": "false",
        }

        result = manage_discovery_credentials(
            action="create",
            name="Full Cred",
            credential_type="SNMP",
            tag="network",
            order=50,
            active=False,
        )

        assert result["success"] is True
        # Verify the data sent to ServiceNow
        post_data = patch_get_client.post.call_args[0][1]
        assert post_data["name"] == "Full Cred"
        assert post_data["type"] == "SNMP"
        assert post_data["tag"] == "network"
        assert post_data["order"] == "50"
        assert post_data["active"] == "false"

    def test_create_missing_name(self, patch_get_client):
        result = manage_discovery_credentials(
            action="create",
            credential_type="SSH",
        )

        assert result["success"] is False
        assert "'name' is required" in result["message"]

    def test_create_missing_type(self, patch_get_client):
        result = manage_discovery_credentials(
            action="create",
            name="Test Cred",
        )

        assert result["success"] is False
        assert "'credential_type' is required" in result["message"]

    def test_create_empty_name(self, patch_get_client):
        result = manage_discovery_credentials(
            action="create",
            name="",
            credential_type="SSH",
        )

        assert result["success"] is False
        assert "'name' is required" in result["message"]

    def test_create_empty_type(self, patch_get_client):
        result = manage_discovery_credentials(
            action="create",
            name="Test",
            credential_type="",
        )

        assert result["success"] is False
        assert "'credential_type' is required" in result["message"]

    def test_create_defaults_active_true(self, patch_get_client):
        patch_get_client.post.return_value = SAMPLE_CREDENTIAL_RECORD

        manage_discovery_credentials(
            action="create",
            name="Test",
            credential_type="SSH",
        )

        post_data = patch_get_client.post.call_args[0][1]
        assert post_data["active"] == "true"

    def test_create_strips_secrets_from_response(self, patch_get_client):
        patch_get_client.post.return_value = SAMPLE_CREDENTIAL_WITH_SECRETS

        result = manage_discovery_credentials(
            action="create",
            name="Test",
            credential_type="SSH",
        )

        assert result["success"] is True
        assert "password" not in result["data"]

    def test_create_posts_to_correct_table(self, patch_get_client):
        patch_get_client.post.return_value = SAMPLE_CREDENTIAL_RECORD

        manage_discovery_credentials(
            action="create",
            name="Test",
            credential_type="SSH",
        )

        assert patch_get_client.post.call_args[0][0] == TABLE_NAME


# ---------------------------------------------------------------------------
# manage_discovery_credentials — UPDATE action
# ---------------------------------------------------------------------------


class TestActionUpdate:
    """Tests for the update action."""

    def test_update_single_field(self, patch_get_client):
        patch_get_client.patch.return_value = {
            **SAMPLE_CREDENTIAL_RECORD,
            "name": "Updated Name",
        }

        result = manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
            name="Updated Name",
        )

        assert result["success"] is True
        assert result["action"] == "update"
        patch_data = patch_get_client.patch.call_args[0][2]
        assert patch_data == {"name": "Updated Name"}

    def test_update_multiple_fields(self, patch_get_client):
        patch_get_client.patch.return_value = SAMPLE_CREDENTIAL_RECORD

        manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
            name="New Name",
            credential_type="SNMP",
            tag="updated-tag",
            order=50,
            active=False,
        )

        patch_data = patch_get_client.patch.call_args[0][2]
        assert patch_data["name"] == "New Name"
        assert patch_data["type"] == "SNMP"
        assert patch_data["tag"] == "updated-tag"
        assert patch_data["order"] == "50"
        assert patch_data["active"] == "false"

    def test_update_no_fields_raises(self, patch_get_client):
        result = manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
        )

        assert result["success"] is False
        assert "At least one field" in result["message"]

    def test_update_missing_sys_id(self, patch_get_client):
        result = manage_discovery_credentials(
            action="update",
            name="Test",
        )

        assert result["success"] is False
        assert "sys_id is required" in result["message"]

    def test_update_invalid_sys_id(self, patch_get_client):
        result = manage_discovery_credentials(
            action="update",
            sys_id="bad-id",
            name="Test",
        )

        assert result["success"] is False
        assert "Invalid sys_id format" in result["message"]

    def test_update_not_found(self, patch_get_client):
        patch_get_client.patch.side_effect = ServiceNowNotFoundError(
            message="Record not found",
        )

        result = manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
            name="Test",
        )

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"

    def test_update_strips_secrets(self, patch_get_client):
        patch_get_client.patch.return_value = SAMPLE_CREDENTIAL_WITH_SECRETS

        result = manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
            name="Test",
        )

        assert result["success"] is True
        assert "password" not in result["data"]

    def test_update_uses_patch_method(self, patch_get_client):
        patch_get_client.patch.return_value = SAMPLE_CREDENTIAL_RECORD

        manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
            name="Test",
        )

        patch_get_client.patch.assert_called_once()
        args = patch_get_client.patch.call_args[0]
        assert args[0] == TABLE_NAME
        assert args[1] == VALID_SYS_ID


# ---------------------------------------------------------------------------
# manage_discovery_credentials — DELETE action
# ---------------------------------------------------------------------------


class TestActionDelete:
    """Tests for the delete action."""

    def test_delete_success(self, patch_get_client):
        patch_get_client.delete.return_value = True

        result = manage_discovery_credentials(
            action="delete",
            sys_id=VALID_SYS_ID,
        )

        assert result["success"] is True
        assert result["action"] == "delete"
        assert result["data"]["sys_id"] == VALID_SYS_ID

    def test_delete_missing_sys_id(self, patch_get_client):
        result = manage_discovery_credentials(action="delete")

        assert result["success"] is False
        assert "sys_id is required" in result["message"]

    def test_delete_invalid_sys_id(self, patch_get_client):
        result = manage_discovery_credentials(
            action="delete",
            sys_id="not-valid",
        )

        assert result["success"] is False
        assert "Invalid sys_id format" in result["message"]

    def test_delete_not_found(self, patch_get_client):
        patch_get_client.delete.side_effect = ServiceNowNotFoundError(
            message="Record not found",
        )

        result = manage_discovery_credentials(
            action="delete",
            sys_id=VALID_SYS_ID,
        )

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"

    def test_delete_calls_correct_table(self, patch_get_client):
        patch_get_client.delete.return_value = True

        manage_discovery_credentials(
            action="delete",
            sys_id=VALID_SYS_ID,
        )

        patch_get_client.delete.assert_called_once_with(TABLE_NAME, VALID_SYS_ID)


# ---------------------------------------------------------------------------
# Invalid action and client errors
# ---------------------------------------------------------------------------


class TestInvalidAction:
    """Tests for invalid action handling."""

    def test_invalid_action(self, patch_get_client):
        result = manage_discovery_credentials(action="invalid")

        assert result["success"] is False
        assert "Invalid action" in result["message"]
        assert "INVALID_ACTION" in result["error"]

    def test_empty_action(self, patch_get_client):
        result = manage_discovery_credentials(action="")

        assert result["success"] is False
        assert "Invalid action" in result["message"]

    def test_action_case_insensitive(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        result = manage_discovery_credentials(action="LIST")

        assert result["success"] is True
        assert result["action"] == "list"

    def test_action_whitespace_stripped(self, patch_get_client):
        patch_get_client.query_table.return_value = []

        result = manage_discovery_credentials(action="  list  ")

        assert result["success"] is True
        assert result["action"] == "list"


class TestClientErrors:
    """Tests for ServiceNow client error handling."""

    def test_client_not_configured(self):
        with patch(
            "snow_discovery_agent.server.get_client",
            side_effect=ServiceNowError(
                message="ServiceNow client not initialized",
                error_code="CLIENT_NOT_CONFIGURED",
            ),
        ):
            result = manage_discovery_credentials(action="list")

        assert result["success"] is False
        assert "not available" in result["message"]
        assert result["error"] == "CLIENT_NOT_CONFIGURED"

    def test_api_error_during_list(self, patch_get_client):
        patch_get_client.query_table.side_effect = ServiceNowError(
            message="HTTP 500: Internal error",
            error_code="SERVICENOW_API_ERROR",
        )

        result = manage_discovery_credentials(action="list")

        assert result["success"] is False
        assert "HTTP 500" in result["message"]

    def test_api_error_during_get(self, patch_get_client):
        patch_get_client.get_table_record.side_effect = ServiceNowError(
            message="HTTP 500",
            error_code="SERVICENOW_API_ERROR",
        )

        result = manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)

        assert result["success"] is False

    def test_api_error_during_create(self, patch_get_client):
        patch_get_client.post.side_effect = ServiceNowError(
            message="HTTP 400: Bad request",
            error_code="SERVICENOW_API_ERROR",
        )

        result = manage_discovery_credentials(
            action="create",
            name="Test",
            credential_type="SSH",
        )

        assert result["success"] is False


# ---------------------------------------------------------------------------
# Security: ensure secrets are NEVER exposed
# ---------------------------------------------------------------------------


class TestSecurityNoSecrets:
    """Ensure credential secrets are never exposed in any operation."""

    def test_list_never_exposes_secrets(self, patch_get_client):
        patch_get_client.query_table.return_value = [SAMPLE_CREDENTIAL_WITH_SECRETS]

        result = manage_discovery_credentials(action="list")

        for cred in result["data"]:
            for pattern in SECRET_FIELD_PATTERNS:
                for key in cred:
                    assert pattern not in key.lower(), (
                        f"Secret field pattern '{pattern}' found in key '{key}'"
                    )

    def test_get_never_exposes_secrets(self, patch_get_client):
        patch_get_client.get_table_record.return_value = SAMPLE_CREDENTIAL_WITH_SECRETS

        result = manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)

        cred = result["data"]
        for pattern in SECRET_FIELD_PATTERNS:
            for key in cred:
                assert pattern not in key.lower(), (
                    f"Secret field pattern '{pattern}' found in key '{key}'"
                )

    def test_create_never_exposes_secrets(self, patch_get_client):
        patch_get_client.post.return_value = SAMPLE_CREDENTIAL_WITH_SECRETS

        result = manage_discovery_credentials(
            action="create",
            name="Test",
            credential_type="SSH",
        )

        cred = result["data"]
        for pattern in SECRET_FIELD_PATTERNS:
            for key in cred:
                assert pattern not in key.lower(), (
                    f"Secret field pattern '{pattern}' found in key '{key}'"
                )

    def test_update_never_exposes_secrets(self, patch_get_client):
        patch_get_client.patch.return_value = SAMPLE_CREDENTIAL_WITH_SECRETS

        result = manage_discovery_credentials(
            action="update",
            sys_id=VALID_SYS_ID,
            name="Test",
        )

        cred = result["data"]
        for pattern in SECRET_FIELD_PATTERNS:
            for key in cred:
                assert pattern not in key.lower(), (
                    f"Secret field pattern '{pattern}' found in key '{key}'"
                )


# ---------------------------------------------------------------------------
# Response format consistency
# ---------------------------------------------------------------------------


class TestResponseFormat:
    """Ensure all responses follow the expected format."""

    EXPECTED_KEYS = {"success", "data", "message", "action", "error"}

    def test_list_response_format(self, patch_get_client):
        patch_get_client.query_table.return_value = []
        result = manage_discovery_credentials(action="list")
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_get_response_format(self, patch_get_client):
        patch_get_client.get_table_record.return_value = SAMPLE_CREDENTIAL_RECORD
        result = manage_discovery_credentials(action="get", sys_id=VALID_SYS_ID)
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_create_response_format(self, patch_get_client):
        patch_get_client.post.return_value = SAMPLE_CREDENTIAL_RECORD
        result = manage_discovery_credentials(
            action="create", name="T", credential_type="SSH"
        )
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_update_response_format(self, patch_get_client):
        patch_get_client.patch.return_value = SAMPLE_CREDENTIAL_RECORD
        result = manage_discovery_credentials(
            action="update", sys_id=VALID_SYS_ID, name="T"
        )
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_delete_response_format(self, patch_get_client):
        patch_get_client.delete.return_value = True
        result = manage_discovery_credentials(
            action="delete", sys_id=VALID_SYS_ID
        )
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_error_response_format(self, patch_get_client):
        result = manage_discovery_credentials(action="invalid")
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_success_responses_have_none_error(self, patch_get_client):
        patch_get_client.query_table.return_value = []
        result = manage_discovery_credentials(action="list")
        assert result["error"] is None

    def test_failure_responses_have_non_none_error(self, patch_get_client):
        result = manage_discovery_credentials(action="get")  # missing sys_id
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# Tool registration in server
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """Test that the tool is properly registered in the MCP server."""

    def test_manage_discovery_credentials_is_registered(self):
        from snow_discovery_agent import server

        # Verify the function exists on the server module
        assert hasattr(server, "manage_discovery_credentials")
        # FastMCP wraps decorated functions in FunctionTool objects;
        # check it has the expected tool name attribute
        tool_obj = server.manage_discovery_credentials
        assert getattr(tool_obj, "name", None) == "manage_discovery_credentials"

    def test_tool_is_importable_from_package(self):
        from snow_discovery_agent import manage_discovery_credentials as tool
        assert callable(tool)

    def test_tool_is_importable_from_tools_package(self):
        from snow_discovery_agent.tools import manage_discovery_credentials as tool
        assert callable(tool)

    def test_tool_in_all_exports(self):
        import snow_discovery_agent
        assert "manage_discovery_credentials" in snow_discovery_agent.__all__


# ---------------------------------------------------------------------------
# Constants and module-level checks
# ---------------------------------------------------------------------------


class TestConstants:
    """Test module constants are properly defined."""

    def test_table_name(self):
        assert TABLE_NAME == "discovery_credential"

    def test_safe_fields_contains_required_fields(self):
        required = {"sys_id", "name", "type", "active", "tag", "order", "affinity"}
        assert required == set(SAFE_FIELDS)

    def test_secret_patterns_not_empty(self):
        assert len(SECRET_FIELD_PATTERNS) > 0

    def test_safe_fields_no_overlap_with_secret_patterns(self):
        for field in SAFE_FIELDS:
            assert not _is_secret_field(field), (
                f"Safe field '{field}' matches a secret pattern"
            )
