"""Tests for the ServiceNow REST client.

Tests cover client initialization, URL construction, query parameter
handling, response parsing, and error handling. Tests use real HTTP
response structures (not mocked ServiceNow APIs) to validate the
client's parsing and error-mapping logic.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from snow_discovery_agent.client import (
    ServiceNowClient,
    _raise_for_status,
)
from snow_discovery_agent.exceptions import (
    ServiceNowAPIError,
    ServiceNowAuthError,
    ServiceNowConnectionError,
    ServiceNowNotFoundError,
    ServiceNowPermissionError,
    ServiceNowRateLimitError,
)


# ---------------------------------------------------------------------------
# Helpers: create realistic HTTP responses for testing parsing logic
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int = 200,
    json_body: dict[str, Any] | None = None,
    text: str = "",
    headers: dict[str, str] | None = None,
    url: str = "https://dev.service-now.com/api/now/table/test",
    method: str = "GET",
) -> requests.Response:
    """Build a real ``requests.Response`` object with the given attributes.

    This creates an actual Response object (not a mock) so that the client's
    parsing logic is tested against the real interface.
    """
    resp = requests.Response()
    resp.status_code = status_code
    resp.url = url
    resp.headers.update(headers or {})
    resp.encoding = "utf-8"

    if json_body is not None:
        resp._content = json.dumps(json_body).encode("utf-8")
    elif text:
        resp._content = text.encode("utf-8")
    else:
        resp._content = b""

    # Attach a request object for method inspection
    resp.request = requests.PreparedRequest()
    resp.request.method = method
    resp.request.url = url

    return resp


# ---------------------------------------------------------------------------
# Test: Client initialization
# ---------------------------------------------------------------------------


class TestClientInit:
    """Tests for ServiceNowClient.__init__."""

    def test_basic_init(self) -> None:
        client = ServiceNowClient(
            instance="https://dev12345.service-now.com",
            username="admin",
            password="secret",
        )
        assert client.instance == "https://dev12345.service-now.com"
        assert client.base_url == "https://dev12345.service-now.com/api/now/table"

    def test_strips_trailing_slash(self) -> None:
        client = ServiceNowClient(
            instance="https://dev12345.service-now.com/",
            username="admin",
            password="secret",
        )
        assert client.instance == "https://dev12345.service-now.com"
        assert client.base_url == "https://dev12345.service-now.com/api/now/table"

    def test_custom_timeout(self) -> None:
        client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            timeout=60,
        )
        assert client._timeout == 60

    def test_tuple_timeout(self) -> None:
        client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            timeout=(10, 30),
        )
        assert client._timeout == (10, 30)

    def test_session_is_created(self) -> None:
        client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
        )
        assert client.session is not None
        assert isinstance(client.session, requests.Session)

    def test_custom_session(self) -> None:
        custom_session = requests.Session()
        client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            session=custom_session,
        )
        assert client.session is custom_session

    def test_context_manager(self) -> None:
        with ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
        ) as client:
            assert client.instance == "https://dev.service-now.com"


# ---------------------------------------------------------------------------
# Test: URL construction
# ---------------------------------------------------------------------------


class TestURLConstruction:
    """Tests for URL building methods."""

    def setup_method(self) -> None:
        self.client = ServiceNowClient(
            instance="https://dev12345.service-now.com",
            username="admin",
            password="secret",
        )

    def test_table_url_no_sys_id(self) -> None:
        url = self.client._build_table_url("discovery_status")
        assert url == "https://dev12345.service-now.com/api/now/table/discovery_status"

    def test_table_url_with_sys_id(self) -> None:
        url = self.client._build_table_url("discovery_status", "abc123def456")
        assert url == "https://dev12345.service-now.com/api/now/table/discovery_status/abc123def456"

    def test_api_url(self) -> None:
        url = self.client._build_api_url("/api/now/stats/incident")
        assert url == "https://dev12345.service-now.com/api/now/stats/incident"


# ---------------------------------------------------------------------------
# Test: _raise_for_status error mapping
# ---------------------------------------------------------------------------


class TestRaiseForStatus:
    """Tests for the _raise_for_status function."""

    def test_200_does_not_raise(self) -> None:
        resp = _make_response(200, json_body={"result": []})
        _raise_for_status(resp)  # Should not raise

    def test_201_does_not_raise(self) -> None:
        resp = _make_response(201, json_body={"result": {}})
        _raise_for_status(resp)

    def test_401_raises_auth_error(self) -> None:
        resp = _make_response(
            401,
            json_body={"error": {"message": "Invalid credentials"}},
        )
        with pytest.raises(ServiceNowAuthError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 401
        assert "Invalid credentials" in exc_info.value.message

    def test_403_raises_permission_error(self) -> None:
        resp = _make_response(
            403,
            json_body={"error": {"message": "Insufficient rights"}},
        )
        with pytest.raises(ServiceNowPermissionError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 403

    def test_404_raises_not_found(self) -> None:
        resp = _make_response(
            404,
            json_body={"error": {"message": "Record not found"}},
        )
        with pytest.raises(ServiceNowNotFoundError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 404

    def test_429_raises_rate_limit(self) -> None:
        resp = _make_response(
            429,
            json_body={"error": {"message": "Rate limit exceeded"}},
            headers={"Retry-After": "60"},
        )
        with pytest.raises(ServiceNowRateLimitError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 429
        assert exc_info.value.details.get("retry_after") == "60"

    def test_429_without_retry_after(self) -> None:
        resp = _make_response(
            429,
            json_body={"error": {"message": "Rate limit exceeded"}},
        )
        with pytest.raises(ServiceNowRateLimitError) as exc_info:
            _raise_for_status(resp)
        assert "retry_after" not in exc_info.value.details

    def test_500_raises_api_error(self) -> None:
        resp = _make_response(
            500,
            json_body={"error": {"message": "Internal error"}},
        )
        with pytest.raises(ServiceNowAPIError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 500

    def test_502_raises_api_error(self) -> None:
        resp = _make_response(502, text="Bad Gateway")
        with pytest.raises(ServiceNowAPIError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 502

    def test_400_raises_api_error(self) -> None:
        """Other 4xx errors should raise ServiceNowAPIError."""
        resp = _make_response(
            400,
            json_body={"error": {"message": "Bad request"}},
        )
        with pytest.raises(ServiceNowAPIError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 400

    def test_error_with_non_dict_error_field(self) -> None:
        """Error field can be a string instead of a dict."""
        resp = _make_response(
            500,
            json_body={"error": "Something went wrong"},
        )
        with pytest.raises(ServiceNowAPIError) as exc_info:
            _raise_for_status(resp)
        assert "Something went wrong" in exc_info.value.message

    def test_error_with_invalid_json(self) -> None:
        """Non-JSON error body should still raise with status text."""
        resp = _make_response(500, text="<html>Error</html>")
        with pytest.raises(ServiceNowAPIError) as exc_info:
            _raise_for_status(resp)
        assert "HTTP 500" in exc_info.value.message

    def test_error_details_include_url_and_method(self) -> None:
        resp = _make_response(
            404,
            json_body={"error": {"message": "Not found"}},
            url="https://dev.service-now.com/api/now/table/incident/abc",
            method="GET",
        )
        with pytest.raises(ServiceNowNotFoundError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.details["url"] == "https://dev.service-now.com/api/now/table/incident/abc"
        assert exc_info.value.details["method"] == "GET"


# ---------------------------------------------------------------------------
# Test: Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    """Tests for the _extract_result method."""

    def setup_method(self) -> None:
        self.client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
        )

    def test_extracts_result_list(self) -> None:
        resp = _make_response(
            200,
            json_body={
                "result": [
                    {"sys_id": "abc", "name": "test"},
                    {"sys_id": "def", "name": "test2"},
                ]
            },
        )
        result = self.client._extract_result(resp)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["sys_id"] == "abc"

    def test_extracts_result_dict(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"sys_id": "abc", "name": "record1"}},
        )
        result = self.client._extract_result(resp)
        assert isinstance(result, dict)
        assert result["sys_id"] == "abc"

    def test_extracts_empty_result(self) -> None:
        resp = _make_response(200, json_body={"result": []})
        result = self.client._extract_result(resp)
        assert result == []

    def test_no_result_key_returns_full_body(self) -> None:
        resp = _make_response(200, json_body={"stats": {"count": 5}})
        result = self.client._extract_result(resp)
        assert result == {"stats": {"count": 5}}

    def test_invalid_json_raises_api_error(self) -> None:
        resp = _make_response(200, text="not json at all")
        with pytest.raises(ServiceNowAPIError) as exc_info:
            self.client._extract_result(resp)
        assert "Invalid JSON" in exc_info.value.message


# ---------------------------------------------------------------------------
# Test: Client HTTP methods with a controlled session
# ---------------------------------------------------------------------------


class TestClientHTTPMethods:
    """Tests for the public HTTP methods using a controlled session.

    These tests inject a session whose ``request`` method returns
    pre-built ``requests.Response`` objects, allowing us to test the
    client's parameter assembly, URL construction, and response parsing
    without making actual network calls.
    """

    def _make_client_with_response(
        self,
        response: requests.Response,
    ) -> ServiceNowClient:
        """Create a client with a session that returns the given response."""
        session = MagicMock(spec=requests.Session)
        session.request.return_value = response
        return ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            session=session,
        )

    def test_get_collection(self) -> None:
        resp = _make_response(
            200,
            json_body={
                "result": [
                    {"sys_id": "aaa", "name": "Schedule A"},
                    {"sys_id": "bbb", "name": "Schedule B"},
                ]
            },
        )
        client = self._make_client_with_response(resp)
        result = client.get("discovery_schedule")

        assert isinstance(result, list)
        assert len(result) == 2

        # Verify the session was called with correct method, URL, and auth
        call_args = client.session.request.call_args
        assert call_args[0][0] == "GET"
        assert "discovery_schedule" in call_args[0][1]
        assert call_args[1].get("auth") == ("admin", "secret")

    def test_get_single_record(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"sys_id": "abc123", "name": "Test Record"}},
        )
        client = self._make_client_with_response(resp)
        result = client.get("discovery_status", sys_id="abc123")

        assert isinstance(result, dict)
        assert result["sys_id"] == "abc123"

    def test_get_with_params(self) -> None:
        resp = _make_response(200, json_body={"result": []})
        client = self._make_client_with_response(resp)
        client.get("discovery_status", params={"sysparm_limit": "5", "sysparm_query": "state=Active"})

        call_args = client.session.request.call_args
        assert call_args[1]["params"]["sysparm_limit"] == "5"
        assert call_args[1]["params"]["sysparm_query"] == "state=Active"

    def test_post_creates_record(self) -> None:
        resp = _make_response(
            201,
            json_body={"result": {"sys_id": "new123", "name": "New Schedule"}},
        )
        client = self._make_client_with_response(resp)
        result = client.post("discovery_schedule", data={"name": "New Schedule"})

        assert result["sys_id"] == "new123"

        call_args = client.session.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == {"name": "New Schedule"}

    def test_put_replaces_record(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"sys_id": "abc", "name": "Updated"}},
        )
        client = self._make_client_with_response(resp)
        result = client.put("discovery_schedule", "abc", data={"name": "Updated"})

        assert result["name"] == "Updated"
        call_args = client.session.request.call_args
        assert call_args[0][0] == "PUT"

    def test_patch_updates_record(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"sys_id": "abc", "active": "true"}},
        )
        client = self._make_client_with_response(resp)
        result = client.patch("discovery_schedule", "abc", data={"active": "true"})

        assert result["active"] == "true"
        call_args = client.session.request.call_args
        assert call_args[0][0] == "PATCH"

    def test_delete_returns_true(self) -> None:
        resp = _make_response(204)
        client = self._make_client_with_response(resp)
        result = client.delete("discovery_schedule", "abc")

        assert result is True
        call_args = client.session.request.call_args
        assert call_args[0][0] == "DELETE"

    def test_get_auth_error_raises(self) -> None:
        resp = _make_response(
            401,
            json_body={"error": {"message": "User not authenticated"}},
        )
        client = self._make_client_with_response(resp)
        with pytest.raises(ServiceNowAuthError):
            client.get("sys_properties")

    def test_connection_error_raises(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.request.side_effect = requests.exceptions.ConnectionError("Connection refused")
        client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            session=session,
        )
        with pytest.raises(ServiceNowConnectionError) as exc_info:
            client.get("sys_properties")
        assert "Connection" in exc_info.value.message

    def test_timeout_error_raises(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.request.side_effect = requests.exceptions.Timeout("Read timed out")
        client = ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            session=session,
        )
        with pytest.raises(ServiceNowConnectionError) as exc_info:
            client.get("sys_properties")
        assert "timed out" in exc_info.value.message


# ---------------------------------------------------------------------------
# Test: Convenience methods
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    """Tests for query_table, get_table_record, get_record_count, test_connection."""

    def _make_client_with_response(
        self,
        response: requests.Response,
    ) -> ServiceNowClient:
        session = MagicMock(spec=requests.Session)
        session.request.return_value = response
        return ServiceNowClient(
            instance="https://dev.service-now.com",
            username="admin",
            password="secret",
            session=session,
        )

    def test_query_table_with_all_params(self) -> None:
        resp = _make_response(
            200,
            json_body={
                "result": [
                    {"sys_id": "a", "name": "Record A"},
                ]
            },
        )
        client = self._make_client_with_response(resp)
        results = client.query_table(
            "discovery_status",
            query="state=Active",
            fields=["sys_id", "name", "state"],
            limit=50,
            offset=10,
        )

        assert len(results) == 1
        assert results[0]["name"] == "Record A"

        call_args = client.session.request.call_args
        params = call_args[1]["params"]
        assert params["sysparm_query"] == "state=Active"
        assert params["sysparm_fields"] == "sys_id,name,state"
        assert params["sysparm_limit"] == "50"
        assert params["sysparm_offset"] == "10"

    def test_query_table_with_order_by_ascending(self) -> None:
        resp = _make_response(200, json_body={"result": []})
        client = self._make_client_with_response(resp)
        client.query_table("discovery_status", order_by="sys_created_on")

        call_args = client.session.request.call_args
        params = call_args[1]["params"]
        assert "ORDERBYsys_created_on" in params["sysparm_query"]

    def test_query_table_with_order_by_descending(self) -> None:
        resp = _make_response(200, json_body={"result": []})
        client = self._make_client_with_response(resp)
        client.query_table("discovery_status", order_by="-sys_created_on")

        call_args = client.session.request.call_args
        params = call_args[1]["params"]
        assert "ORDERBYDESCsys_created_on" in params["sysparm_query"]

    def test_query_table_with_query_and_order(self) -> None:
        resp = _make_response(200, json_body={"result": []})
        client = self._make_client_with_response(resp)
        client.query_table(
            "discovery_status",
            query="state=Active",
            order_by="-sys_created_on",
        )

        call_args = client.session.request.call_args
        params = call_args[1]["params"]
        assert params["sysparm_query"] == "state=Active^ORDERBYDESCsys_created_on"

    def test_get_table_record(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"sys_id": "abc123", "name": "My Record"}},
        )
        client = self._make_client_with_response(resp)
        record = client.get_table_record("discovery_status", "abc123")
        assert record["sys_id"] == "abc123"

    def test_get_table_record_with_fields(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"sys_id": "abc", "name": "Test"}},
        )
        client = self._make_client_with_response(resp)
        client.get_table_record("discovery_status", "abc", fields=["sys_id", "name"])

        call_args = client.session.request.call_args
        params = call_args[1]["params"]
        assert params["sysparm_fields"] == "sys_id,name"

    def test_get_table_record_not_found(self) -> None:
        resp = _make_response(
            404,
            json_body={"error": {"message": "Record not found"}},
        )
        client = self._make_client_with_response(resp)
        with pytest.raises(ServiceNowNotFoundError):
            client.get_table_record("discovery_status", "nonexistent")

    def test_get_record_count(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": {"stats": {"count": "42"}}},
        )
        client = self._make_client_with_response(resp)
        count = client.get_record_count("discovery_status", query="state=Active")

        assert count == 42

        call_args = client.session.request.call_args
        url = call_args[0][1]
        assert "/api/now/stats/discovery_status" in url

    def test_test_connection_success(self) -> None:
        resp = _make_response(
            200,
            json_body={"result": [{"sys_id": "x", "name": "prop"}]},
        )
        client = self._make_client_with_response(resp)
        result = client.test_connection()

        assert result["success"] is True
        assert result["instance"] == "https://dev.service-now.com"
        assert result["status_code"] == 200

    def test_test_connection_auth_failure(self) -> None:
        resp = _make_response(
            401,
            json_body={"error": {"message": "Not authenticated"}},
        )
        client = self._make_client_with_response(resp)
        with pytest.raises(ServiceNowAuthError):
            client.test_connection()
