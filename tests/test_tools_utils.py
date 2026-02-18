"""Tests for the tools/utils.py shared utility module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from snow_discovery_agent.tools.utils import (
    build_query,
    format_snow_datetime,
    make_response,
    paginate,
    truncate_description,
    validate_sys_id,
)

VALID_SYS_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


class TestFormatSnowDatetime:
    def test_snow_format(self):
        result = format_snow_datetime("2026-02-18 10:30:00")
        assert result == "2026-02-18T10:30:00Z"

    def test_iso_format(self):
        result = format_snow_datetime("2026-02-18T10:30:00")
        assert result is not None
        assert "2026-02-18" in result

    def test_none_returns_none(self):
        assert format_snow_datetime(None) is None

    def test_empty_returns_none(self):
        assert format_snow_datetime("") is None

    def test_whitespace_returns_none(self):
        assert format_snow_datetime("   ") is None

    def test_invalid_returns_none(self):
        assert format_snow_datetime("not-a-date") is None


class TestBuildQuery:
    def test_empty_filters(self):
        assert build_query({}) is None

    def test_all_none_values(self):
        assert build_query({"a": None, "b": None}) is None

    def test_single_string_filter(self):
        result = build_query({"state": "Completed"})
        assert result == "state=Completed"

    def test_boolean_filter(self):
        result = build_query({"active": True})
        assert result == "active=true"

    def test_boolean_false_filter(self):
        result = build_query({"active": False})
        assert result == "active=false"

    def test_multiple_filters(self):
        result = build_query({"active": True, "state": "Completed"})
        assert "active=true" in result
        assert "state=Completed" in result
        assert "^" in result

    def test_none_values_skipped(self):
        result = build_query({"active": True, "state": None})
        assert result == "active=true"


class TestPaginate:
    def test_single_page(self):
        client = MagicMock()
        client.query_table.return_value = [{"sys_id": "1"}, {"sys_id": "2"}]

        results = paginate(client, "test_table", limit=10)

        assert len(results) == 2
        client.query_table.assert_called_once()

    def test_multiple_pages(self):
        client = MagicMock()
        page1 = [{"sys_id": str(i)} for i in range(100)]
        page2 = [{"sys_id": str(i)} for i in range(100, 150)]

        client.query_table.side_effect = [page1, page2]

        results = paginate(client, "test_table", limit=100)

        assert len(results) == 150
        assert client.query_table.call_count == 2

    def test_empty_results(self):
        client = MagicMock()
        client.query_table.return_value = []

        results = paginate(client, "test_table")

        assert results == []

    def test_max_pages_limit(self):
        client = MagicMock()
        client.query_table.return_value = [{"sys_id": str(i)} for i in range(100)]

        paginate(client, "test_table", limit=100, max_pages=2)

        assert client.query_table.call_count == 2

    def test_query_and_fields_forwarded(self):
        client = MagicMock()
        client.query_table.return_value = []

        paginate(
            client, "test_table",
            query="active=true",
            fields=["sys_id", "name"],
            order_by="-created_on",
        )

        call_kwargs = client.query_table.call_args[1]
        assert call_kwargs["query"] == "active=true"
        assert call_kwargs["fields"] == ["sys_id", "name"]
        assert call_kwargs["order_by"] == "-created_on"


class TestValidateSysId:
    def test_valid(self):
        assert validate_sys_id(VALID_SYS_ID) == VALID_SYS_ID

    def test_none_raises(self):
        with pytest.raises(ValueError, match="required"):
            validate_sys_id(None)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="required"):
            validate_sys_id("")

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_sys_id("bad-id")

    def test_custom_label(self):
        with pytest.raises(ValueError, match="custom_field"):
            validate_sys_id(None, label="custom_field")


class TestTruncateDescription:
    def test_short_text(self):
        assert truncate_description("short") == "short"

    def test_long_text(self):
        text = "x" * 300
        result = truncate_description(text, max_length=200)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

    def test_none_returns_empty(self):
        assert truncate_description(None) == ""

    def test_empty_returns_empty(self):
        assert truncate_description("") == ""

    def test_exact_length(self):
        text = "x" * 200
        result = truncate_description(text, max_length=200)
        assert result == text


class TestMakeResponse:
    def test_success_response(self):
        result = make_response(
            success=True,
            data={"key": "value"},
            message="OK",
            action="test",
        )
        assert result["success"] is True
        assert result["data"] == {"key": "value"}
        assert result["error"] is None

    def test_error_response(self):
        result = make_response(
            success=False,
            message="Failed",
            action="test",
            error="TEST_ERROR",
        )
        assert result["success"] is False
        assert result["error"] == "TEST_ERROR"
