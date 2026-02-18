"""Tests for the tools/errors.py module."""

from __future__ import annotations

from snow_discovery_agent.tools.errors import (
    InvalidParameterError,
    RecordNotFoundError,
    ToolError,
    ToolPermissionError,
)


class TestToolError:
    def test_default_values(self):
        err = ToolError()
        assert str(err) == "Tool error"
        assert err.message == "Tool error"
        assert err.error_code == "TOOL_ERROR"
        assert err.details == {}

    def test_custom_values(self):
        err = ToolError(
            message="Custom error",
            error_code="CUSTOM",
            details={"key": "value"},
        )
        assert err.message == "Custom error"
        assert err.error_code == "CUSTOM"
        assert err.details == {"key": "value"}

    def test_to_dict(self):
        err = ToolError(message="msg", error_code="CODE")
        d = err.to_dict()
        assert d["error"] == "msg"
        assert d["error_code"] == "CODE"
        assert "details" not in d  # Empty details not included

    def test_to_dict_with_details(self):
        err = ToolError(details={"key": "value"})
        d = err.to_dict()
        assert d["details"] == {"key": "value"}

    def test_is_exception(self):
        err = ToolError()
        assert isinstance(err, Exception)


class TestInvalidParameterError:
    def test_defaults(self):
        err = InvalidParameterError()
        assert err.error_code == "INVALID_PARAMETER"
        assert isinstance(err, ToolError)

    def test_custom_message(self):
        err = InvalidParameterError(
            message="Bad param",
            details={"param": "sys_id"},
        )
        assert err.message == "Bad param"
        assert err.details["param"] == "sys_id"


class TestRecordNotFoundError:
    def test_defaults(self):
        err = RecordNotFoundError()
        assert err.error_code == "RECORD_NOT_FOUND"
        assert isinstance(err, ToolError)


class TestToolPermissionError:
    def test_defaults(self):
        err = ToolPermissionError()
        assert err.error_code == "TOOL_PERMISSION_DENIED"
        assert isinstance(err, ToolError)

    def test_custom_message(self):
        err = ToolPermissionError(message="Cannot modify credentials")
        assert err.message == "Cannot modify credentials"
