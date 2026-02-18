"""Tests for the ServiceNow exception hierarchy."""

from __future__ import annotations

import pytest

from snow_discovery_agent.exceptions import (
    ServiceNowAPIError,
    ServiceNowAuthError,
    ServiceNowConnectionError,
    ServiceNowError,
    ServiceNowNotFoundError,
    ServiceNowPermissionError,
    ServiceNowRateLimitError,
)


class TestServiceNowErrorBase:
    """Tests for the base ServiceNowError class."""

    def test_default_attributes(self) -> None:
        err = ServiceNowError()
        assert err.message == "ServiceNow error"
        assert err.error_code == "SERVICENOW_ERROR"
        assert err.status_code is None
        assert err.details == {}
        assert str(err) == "ServiceNow error"

    def test_custom_attributes(self) -> None:
        err = ServiceNowError(
            message="Something broke",
            error_code="CUSTOM_CODE",
            status_code=418,
            details={"key": "value"},
        )
        assert err.message == "Something broke"
        assert err.error_code == "CUSTOM_CODE"
        assert err.status_code == 418
        assert err.details == {"key": "value"}

    def test_to_dict_minimal(self) -> None:
        err = ServiceNowError(message="Fail")
        d = err.to_dict()
        assert d == {"error": "Fail", "error_code": "SERVICENOW_ERROR"}
        assert "status_code" not in d
        assert "details" not in d

    def test_to_dict_full(self) -> None:
        err = ServiceNowError(
            message="Fail",
            error_code="MY_CODE",
            status_code=500,
            details={"ctx": "test"},
        )
        d = err.to_dict()
        assert d["error"] == "Fail"
        assert d["error_code"] == "MY_CODE"
        assert d["status_code"] == 500
        assert d["details"] == {"ctx": "test"}

    def test_is_exception(self) -> None:
        err = ServiceNowError("test")
        assert isinstance(err, Exception)


class TestServiceNowAuthError:
    """Tests for ServiceNowAuthError (401)."""

    def test_defaults(self) -> None:
        err = ServiceNowAuthError()
        assert err.message == "Authentication failed"
        assert err.error_code == "AUTHENTICATION_ERROR"
        assert err.status_code == 401
        assert isinstance(err, ServiceNowError)

    def test_custom_message(self) -> None:
        err = ServiceNowAuthError(message="Bad creds", status_code=401)
        assert err.message == "Bad creds"
        assert err.status_code == 401

    def test_catchable_as_base(self) -> None:
        with pytest.raises(ServiceNowError):
            raise ServiceNowAuthError()


class TestServiceNowPermissionError:
    """Tests for ServiceNowPermissionError (403)."""

    def test_defaults(self) -> None:
        err = ServiceNowPermissionError()
        assert err.message == "Permission denied"
        assert err.error_code == "PERMISSION_ERROR"
        assert err.status_code == 403
        assert isinstance(err, ServiceNowError)

    def test_catchable_as_base(self) -> None:
        with pytest.raises(ServiceNowError):
            raise ServiceNowPermissionError()


class TestServiceNowNotFoundError:
    """Tests for ServiceNowNotFoundError (404)."""

    def test_defaults(self) -> None:
        err = ServiceNowNotFoundError()
        assert err.message == "Resource not found"
        assert err.error_code == "NOT_FOUND"
        assert err.status_code == 404
        assert isinstance(err, ServiceNowError)

    def test_with_details(self) -> None:
        err = ServiceNowNotFoundError(
            message="Record gone",
            details={"table": "incident", "sys_id": "abc123"},
        )
        d = err.to_dict()
        assert d["details"]["table"] == "incident"


class TestServiceNowRateLimitError:
    """Tests for ServiceNowRateLimitError (429)."""

    def test_defaults(self) -> None:
        err = ServiceNowRateLimitError()
        assert err.message == "Rate limit exceeded"
        assert err.error_code == "RATE_LIMIT_ERROR"
        assert err.status_code == 429
        assert isinstance(err, ServiceNowError)

    def test_with_retry_after(self) -> None:
        err = ServiceNowRateLimitError(
            details={"retry_after": "60"},
        )
        assert err.details["retry_after"] == "60"


class TestServiceNowAPIError:
    """Tests for ServiceNowAPIError (5xx)."""

    def test_defaults(self) -> None:
        err = ServiceNowAPIError()
        assert err.message == "ServiceNow API error"
        assert err.error_code == "SERVICENOW_API_ERROR"
        assert err.status_code == 500
        assert isinstance(err, ServiceNowError)

    def test_custom_status(self) -> None:
        err = ServiceNowAPIError(message="Bad gateway", status_code=502)
        assert err.status_code == 502


class TestServiceNowConnectionError:
    """Tests for ServiceNowConnectionError (network/timeout)."""

    def test_defaults(self) -> None:
        err = ServiceNowConnectionError()
        assert err.message == "Connection failed"
        assert err.error_code == "CONNECTION_ERROR"
        assert err.status_code is None
        assert isinstance(err, ServiceNowError)

    def test_with_original_error(self) -> None:
        err = ServiceNowConnectionError(
            message="Timed out",
            details={"original_error": "ReadTimeout"},
        )
        assert err.details["original_error"] == "ReadTimeout"
        assert err.status_code is None


class TestExceptionHierarchy:
    """Tests that all exceptions maintain correct inheritance."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ServiceNowAuthError,
            ServiceNowPermissionError,
            ServiceNowNotFoundError,
            ServiceNowRateLimitError,
            ServiceNowAPIError,
            ServiceNowConnectionError,
        ],
    )
    def test_all_inherit_from_base(self, exc_class: type) -> None:
        assert issubclass(exc_class, ServiceNowError)
        assert issubclass(exc_class, Exception)

    @pytest.mark.parametrize(
        "exc_class",
        [
            ServiceNowAuthError,
            ServiceNowPermissionError,
            ServiceNowNotFoundError,
            ServiceNowRateLimitError,
            ServiceNowAPIError,
            ServiceNowConnectionError,
        ],
    )
    def test_all_have_to_dict(self, exc_class: type) -> None:
        err = exc_class()
        d = err.to_dict()
        assert "error" in d
        assert "error_code" in d
