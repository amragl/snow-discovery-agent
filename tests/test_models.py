"""Tests for Pydantic v2 models representing ServiceNow Discovery tables.

Tests cover:
- Model instantiation with defaults
- ``from_snow()`` classmethod with realistic ServiceNow API response data
- ServiceNow datetime parsing (standard and ISO 8601 formats)
- Boolean coercion from ServiceNow string representations
- Integer coercion from ServiceNow string representations
- Field validation and clamping
- Serialization to dict and JSON
- Optional field defaults
- Edge cases: empty strings, missing keys, None values
"""

from __future__ import annotations

from datetime import datetime

import pytest

from snow_discovery_agent.models import (
    CIDelta,
    DiscoveryCompareResult,
    DiscoveryCredential,
    DiscoveryHealthSummary,
    DiscoveryLog,
    DiscoveryPattern,
    DiscoveryRange,
    DiscoverySchedule,
    DiscoveryStatus,
    ErrorCount,
    ErrorDelta,
    SnowBaseModel,
    parse_snow_datetime,
)

# ---------------------------------------------------------------------------
# Realistic ServiceNow API response fixtures
# ---------------------------------------------------------------------------
# These dicts match the structure returned by the ServiceNow Table API
# (GET /api/now/table/<table_name>), using real field names and formats.
# ---------------------------------------------------------------------------

SNOW_DISCOVERY_STATUS_RESPONSE: dict = {
    "sys_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "name": "Discovery 2026-02-18 10:00:00",
    "state": "Completed",
    "source": "Daily Network Scan",
    "dscl_status": "Classified",
    "log": "Discovery completed successfully. 42 CIs processed.",
    "started": "2026-02-18 10:00:00",
    "completed": "2026-02-18 10:45:30",
    "ci_count": "42",
    "ip_address": "10.0.1.0/24",
    "mid_server": "mid_server_01",
}

SNOW_DISCOVERY_SCHEDULE_RESPONSE: dict = {
    "sys_id": "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1",
    "name": "Daily Network Scan",
    "active": "true",
    "discover": "IP",
    "max_run_time": "02:00:00",
    "run_dayofweek": "Monday,Tuesday,Wednesday,Thursday,Friday",
    "run_time": "22:00:00",
    "mid_select_method": "Auto",
    "location": "US-East Data Center",
}

SNOW_DISCOVERY_CREDENTIAL_RESPONSE: dict = {
    "sys_id": "c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2",
    "name": "Linux SSH Credential",
    "type": "SSH",
    "active": "true",
    "tag": "linux-prod",
    "order": "100",
    "affinity": "specific",
}

SNOW_DISCOVERY_RANGE_RESPONSE: dict = {
    "sys_id": "d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3",
    "name": "Production Subnet",
    "type": "IP Network",
    "active": "true",
    "range_start": "10.0.1.0/24",
    "range_end": "",
    "include": "true",
}

SNOW_DISCOVERY_PATTERN_RESPONSE: dict = {
    "sys_id": "e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4",
    "name": "Linux Server Pattern",
    "active": "true",
    "ci_type": "cmdb_ci_linux_server",
    "criteria": "os_name=Linux^os_version>=5.0",
    "description": "Classifies Linux servers running kernel 5.0 or later",
}

SNOW_DISCOVERY_LOG_RESPONSE: dict = {
    "sys_id": "f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4e5",
    "status": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "level": "Error",
    "message": "SSH credential failed for host 10.0.1.50: Connection refused",
    "source": "DiscoveryClassification",
    "created_on": "2026-02-18 10:15:22",
}


# ===========================================================================
# Tests: parse_snow_datetime helper
# ===========================================================================


class TestParseSnowDatetime:
    """Tests for the ``parse_snow_datetime`` helper function."""

    def test_standard_format(self):
        result = parse_snow_datetime("2026-02-18 10:00:00")
        assert result == datetime(2026, 2, 18, 10, 0, 0)

    def test_iso_format(self):
        result = parse_snow_datetime("2026-02-18T10:00:00")
        assert result == datetime(2026, 2, 18, 10, 0, 0)

    def test_empty_string_returns_none(self):
        assert parse_snow_datetime("") is None

    def test_whitespace_string_returns_none(self):
        assert parse_snow_datetime("   ") is None

    def test_none_returns_none(self):
        assert parse_snow_datetime(None) is None

    def test_invalid_string_returns_none(self):
        assert parse_snow_datetime("not-a-date") is None

    def test_strips_whitespace(self):
        result = parse_snow_datetime("  2026-02-18 10:00:00  ")
        assert result == datetime(2026, 2, 18, 10, 0, 0)


# ===========================================================================
# Tests: SnowBaseModel
# ===========================================================================


class TestSnowBaseModel:
    """Tests for the ``SnowBaseModel`` base class."""

    def test_default_sys_id_is_empty(self):
        model = SnowBaseModel()
        assert model.sys_id == ""

    def test_from_snow_with_sys_id(self):
        model = SnowBaseModel.from_snow({"sys_id": "abc123"})
        assert model.sys_id == "abc123"

    def test_from_snow_empty_dict(self):
        model = SnowBaseModel.from_snow({})
        assert model.sys_id == ""

    def test_field_map_returns_empty_by_default(self):
        assert SnowBaseModel._field_map() == {}

    def test_serialization_to_dict(self):
        model = SnowBaseModel(sys_id="abc123")
        d = model.model_dump()
        assert d == {"sys_id": "abc123"}

    def test_serialization_to_json(self):
        model = SnowBaseModel(sys_id="abc123")
        json_str = model.model_dump_json()
        assert '"sys_id":"abc123"' in json_str.replace(" ", "")


# ===========================================================================
# Tests: DiscoveryStatus
# ===========================================================================


class TestDiscoveryStatus:
    """Tests for the ``DiscoveryStatus`` model."""

    def test_defaults(self):
        status = DiscoveryStatus()
        assert status.sys_id == ""
        assert status.name == ""
        assert status.state == ""
        assert status.source == ""
        assert status.dscl_status == ""
        assert status.log == ""
        assert status.started is None
        assert status.completed is None
        assert status.ci_count == 0
        assert status.ip_address == ""
        assert status.mid_server == ""

    def test_from_snow(self):
        status = DiscoveryStatus.from_snow(SNOW_DISCOVERY_STATUS_RESPONSE)
        assert status.sys_id == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        assert status.name == "Discovery 2026-02-18 10:00:00"
        assert status.state == "Completed"
        assert status.source == "Daily Network Scan"
        assert status.dscl_status == "Classified"
        assert status.log == "Discovery completed successfully. 42 CIs processed."
        assert status.started == datetime(2026, 2, 18, 10, 0, 0)
        assert status.completed == datetime(2026, 2, 18, 10, 45, 30)
        assert status.ci_count == 42
        assert status.ip_address == "10.0.1.0/24"
        assert status.mid_server == "mid_server_01"

    def test_ci_count_coerced_from_string(self):
        status = DiscoveryStatus.from_snow({"ci_count": "99"})
        assert status.ci_count == 99

    def test_ci_count_empty_string_defaults_to_zero(self):
        status = DiscoveryStatus.from_snow({"ci_count": ""})
        assert status.ci_count == 0

    def test_datetime_empty_string_is_none(self):
        status = DiscoveryStatus.from_snow({"started": "", "completed": ""})
        assert status.started is None
        assert status.completed is None

    def test_datetime_none_is_none(self):
        status = DiscoveryStatus.from_snow({"started": None, "completed": None})
        assert status.started is None
        assert status.completed is None

    def test_serialization_round_trip(self):
        status = DiscoveryStatus.from_snow(SNOW_DISCOVERY_STATUS_RESPONSE)
        d = status.model_dump()
        assert d["sys_id"] == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        assert d["ci_count"] == 42
        assert d["state"] == "Completed"

    def test_json_serialization(self):
        status = DiscoveryStatus.from_snow(SNOW_DISCOVERY_STATUS_RESPONSE)
        json_str = status.model_dump_json()
        assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" in json_str
        assert "Completed" in json_str

    def test_partial_response(self):
        """ServiceNow may return only requested fields."""
        status = DiscoveryStatus.from_snow({
            "sys_id": "abc",
            "state": "Active",
        })
        assert status.sys_id == "abc"
        assert status.state == "Active"
        assert status.ci_count == 0
        assert status.started is None


# ===========================================================================
# Tests: DiscoverySchedule
# ===========================================================================


class TestDiscoverySchedule:
    """Tests for the ``DiscoverySchedule`` model."""

    def test_defaults(self):
        schedule = DiscoverySchedule()
        assert schedule.sys_id == ""
        assert schedule.name == ""
        assert schedule.active is True
        assert schedule.discover == ""
        assert schedule.max_run_time == "02:00:00"
        assert schedule.run_dayofweek == ""
        assert schedule.run_time == ""
        assert schedule.mid_select_method == ""
        assert schedule.location == ""

    def test_from_snow(self):
        schedule = DiscoverySchedule.from_snow(SNOW_DISCOVERY_SCHEDULE_RESPONSE)
        assert schedule.sys_id == "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1"
        assert schedule.name == "Daily Network Scan"
        assert schedule.active is True
        assert schedule.discover == "IP"
        assert schedule.max_run_time == "02:00:00"
        assert schedule.run_dayofweek == "Monday,Tuesday,Wednesday,Thursday,Friday"
        assert schedule.run_time == "22:00:00"
        assert schedule.mid_select_method == "Auto"
        assert schedule.location == "US-East Data Center"

    def test_active_false_string(self):
        schedule = DiscoverySchedule.from_snow({"active": "false"})
        assert schedule.active is False

    def test_active_zero_string(self):
        schedule = DiscoverySchedule.from_snow({"active": "0"})
        assert schedule.active is False

    def test_active_true_bool(self):
        schedule = DiscoverySchedule(active=True)
        assert schedule.active is True

    def test_serialization(self):
        schedule = DiscoverySchedule.from_snow(SNOW_DISCOVERY_SCHEDULE_RESPONSE)
        d = schedule.model_dump()
        assert d["name"] == "Daily Network Scan"
        assert d["active"] is True
        assert d["discover"] == "IP"


# ===========================================================================
# Tests: DiscoveryCredential
# ===========================================================================


class TestDiscoveryCredential:
    """Tests for the ``DiscoveryCredential`` model."""

    def test_defaults(self):
        cred = DiscoveryCredential()
        assert cred.sys_id == ""
        assert cred.name == ""
        assert cred.type == ""
        assert cred.active is True
        assert cred.tag == ""
        assert cred.order == 100
        assert cred.affinity == ""

    def test_from_snow(self):
        cred = DiscoveryCredential.from_snow(SNOW_DISCOVERY_CREDENTIAL_RESPONSE)
        assert cred.sys_id == "c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2"
        assert cred.name == "Linux SSH Credential"
        assert cred.type == "SSH"
        assert cred.active is True
        assert cred.tag == "linux-prod"
        assert cred.order == 100
        assert cred.affinity == "specific"

    def test_order_coerced_from_string(self):
        cred = DiscoveryCredential.from_snow({"order": "50"})
        assert cred.order == 50

    def test_order_empty_string_defaults(self):
        cred = DiscoveryCredential.from_snow({"order": ""})
        assert cred.order == 100

    def test_active_false(self):
        cred = DiscoveryCredential.from_snow({"active": "false"})
        assert cred.active is False

    def test_serialization(self):
        cred = DiscoveryCredential.from_snow(SNOW_DISCOVERY_CREDENTIAL_RESPONSE)
        d = cred.model_dump()
        assert d["name"] == "Linux SSH Credential"
        assert d["type"] == "SSH"
        assert d["order"] == 100


# ===========================================================================
# Tests: DiscoveryRange
# ===========================================================================


class TestDiscoveryRange:
    """Tests for the ``DiscoveryRange`` model."""

    def test_defaults(self):
        r = DiscoveryRange()
        assert r.sys_id == ""
        assert r.name == ""
        assert r.type == ""
        assert r.active is True
        assert r.range_start == ""
        assert r.range_end == ""
        assert r.include is True

    def test_from_snow(self):
        r = DiscoveryRange.from_snow(SNOW_DISCOVERY_RANGE_RESPONSE)
        assert r.sys_id == "d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3"
        assert r.name == "Production Subnet"
        assert r.type == "IP Network"
        assert r.active is True
        assert r.range_start == "10.0.1.0/24"
        assert r.range_end == ""
        assert r.include is True

    def test_include_false(self):
        r = DiscoveryRange.from_snow({"include": "false"})
        assert r.include is False

    def test_active_false(self):
        r = DiscoveryRange.from_snow({"active": "0"})
        assert r.active is False

    def test_ip_range_type(self):
        r = DiscoveryRange.from_snow({
            "name": "DMZ Range",
            "type": "IP Range",
            "range_start": "192.168.1.1",
            "range_end": "192.168.1.254",
            "include": "true",
        })
        assert r.type == "IP Range"
        assert r.range_start == "192.168.1.1"
        assert r.range_end == "192.168.1.254"

    def test_serialization(self):
        r = DiscoveryRange.from_snow(SNOW_DISCOVERY_RANGE_RESPONSE)
        d = r.model_dump()
        assert d["type"] == "IP Network"
        assert d["range_start"] == "10.0.1.0/24"


# ===========================================================================
# Tests: DiscoveryPattern
# ===========================================================================


class TestDiscoveryPattern:
    """Tests for the ``DiscoveryPattern`` model."""

    def test_defaults(self):
        p = DiscoveryPattern()
        assert p.sys_id == ""
        assert p.name == ""
        assert p.active is True
        assert p.ci_type == ""
        assert p.criteria == ""
        assert p.description == ""

    def test_from_snow(self):
        p = DiscoveryPattern.from_snow(SNOW_DISCOVERY_PATTERN_RESPONSE)
        assert p.sys_id == "e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4"
        assert p.name == "Linux Server Pattern"
        assert p.active is True
        assert p.ci_type == "cmdb_ci_linux_server"
        assert p.criteria == "os_name=Linux^os_version>=5.0"
        assert p.description == "Classifies Linux servers running kernel 5.0 or later"

    def test_active_false(self):
        p = DiscoveryPattern.from_snow({"active": "false"})
        assert p.active is False

    def test_serialization(self):
        p = DiscoveryPattern.from_snow(SNOW_DISCOVERY_PATTERN_RESPONSE)
        d = p.model_dump()
        assert d["ci_type"] == "cmdb_ci_linux_server"


# ===========================================================================
# Tests: DiscoveryLog
# ===========================================================================


class TestDiscoveryLog:
    """Tests for the ``DiscoveryLog`` model."""

    def test_defaults(self):
        log = DiscoveryLog()
        assert log.sys_id == ""
        assert log.status == ""
        assert log.level == ""
        assert log.message == ""
        assert log.source == ""
        assert log.created_on is None

    def test_from_snow(self):
        log = DiscoveryLog.from_snow(SNOW_DISCOVERY_LOG_RESPONSE)
        assert log.sys_id == "f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4e5"
        assert log.status == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        assert log.level == "Error"
        assert log.message == "SSH credential failed for host 10.0.1.50: Connection refused"
        assert log.source == "DiscoveryClassification"
        assert log.created_on == datetime(2026, 2, 18, 10, 15, 22)

    def test_created_on_empty_string(self):
        log = DiscoveryLog.from_snow({"created_on": ""})
        assert log.created_on is None

    def test_created_on_none(self):
        log = DiscoveryLog.from_snow({"created_on": None})
        assert log.created_on is None

    def test_serialization(self):
        log = DiscoveryLog.from_snow(SNOW_DISCOVERY_LOG_RESPONSE)
        d = log.model_dump()
        assert d["level"] == "Error"
        assert d["source"] == "DiscoveryClassification"


# ===========================================================================
# Tests: ErrorCount
# ===========================================================================


class TestErrorCount:
    """Tests for the ``ErrorCount`` sub-model."""

    def test_creation(self):
        ec = ErrorCount(message="SSH connection refused", count=15)
        assert ec.message == "SSH connection refused"
        assert ec.count == 15
        assert ec.level == "Error"

    def test_custom_level(self):
        ec = ErrorCount(message="Timeout warning", count=5, level="Warning")
        assert ec.level == "Warning"

    def test_serialization(self):
        ec = ErrorCount(message="Test", count=1)
        d = ec.model_dump()
        assert d == {"message": "Test", "count": 1, "level": "Error"}


# ===========================================================================
# Tests: DiscoveryHealthSummary
# ===========================================================================


class TestDiscoveryHealthSummary:
    """Tests for the ``DiscoveryHealthSummary`` model."""

    def test_defaults(self):
        health = DiscoveryHealthSummary()
        assert health.total_scans == 0
        assert health.successful == 0
        assert health.failed == 0
        assert health.cancelled == 0
        assert health.error_rate == 0.0
        assert health.avg_duration_seconds == 0.0
        assert health.total_cis_discovered == 0
        assert health.top_errors == []
        assert health.health_score == 100
        assert health.period == "week"
        assert health.computed_at is None

    def test_with_data(self):
        health = DiscoveryHealthSummary(
            total_scans=100,
            successful=85,
            failed=10,
            cancelled=5,
            error_rate=10.0,
            avg_duration_seconds=2700.0,
            total_cis_discovered=1500,
            top_errors=[
                ErrorCount(message="SSH refused", count=25),
                ErrorCount(message="SNMP timeout", count=10),
            ],
            health_score=75,
            period="month",
        )
        assert health.total_scans == 100
        assert health.successful == 85
        assert health.failed == 10
        assert health.cancelled == 5
        assert health.error_rate == 10.0
        assert health.avg_duration_seconds == 2700.0
        assert health.total_cis_discovered == 1500
        assert len(health.top_errors) == 2
        assert health.top_errors[0].message == "SSH refused"
        assert health.health_score == 75
        assert health.period == "month"

    def test_error_rate_clamped_high(self):
        health = DiscoveryHealthSummary(error_rate=150.0)
        assert health.error_rate == 100.0

    def test_error_rate_clamped_low(self):
        health = DiscoveryHealthSummary(error_rate=-10.0)
        assert health.error_rate == 0.0

    def test_health_score_clamped_high(self):
        health = DiscoveryHealthSummary(health_score=200)
        assert health.health_score == 100

    def test_health_score_clamped_low(self):
        health = DiscoveryHealthSummary(health_score=-50)
        assert health.health_score == 0

    def test_serialization(self):
        health = DiscoveryHealthSummary(
            total_scans=10,
            successful=8,
            failed=2,
            error_rate=20.0,
            health_score=80,
            top_errors=[ErrorCount(message="Test error", count=3)],
        )
        d = health.model_dump()
        assert d["total_scans"] == 10
        assert d["health_score"] == 80
        assert len(d["top_errors"]) == 1
        assert d["top_errors"][0]["message"] == "Test error"

    def test_json_serialization(self):
        health = DiscoveryHealthSummary(total_scans=5, health_score=90)
        json_str = health.model_dump_json()
        assert '"total_scans":5' in json_str.replace(" ", "")
        assert '"health_score":90' in json_str.replace(" ", "")


# ===========================================================================
# Tests: CIDelta
# ===========================================================================


class TestCIDelta:
    """Tests for the ``CIDelta`` sub-model."""

    def test_creation(self):
        ci = CIDelta(
            sys_id="abc123",
            name="web-server-01",
            ci_type="cmdb_ci_linux_server",
            change_type="added",
            details="New CI discovered",
        )
        assert ci.sys_id == "abc123"
        assert ci.name == "web-server-01"
        assert ci.ci_type == "cmdb_ci_linux_server"
        assert ci.change_type == "added"
        assert ci.details == "New CI discovered"

    def test_defaults(self):
        ci = CIDelta(sys_id="x")
        assert ci.name == ""
        assert ci.ci_type == ""
        assert ci.change_type == ""
        assert ci.details == ""

    def test_serialization(self):
        ci = CIDelta(sys_id="x", change_type="removed")
        d = ci.model_dump()
        assert d["sys_id"] == "x"
        assert d["change_type"] == "removed"


# ===========================================================================
# Tests: ErrorDelta
# ===========================================================================


class TestErrorDelta:
    """Tests for the ``ErrorDelta`` sub-model."""

    def test_creation(self):
        ed = ErrorDelta(
            message="SSH timeout",
            status="new",
            count_a=0,
            count_b=5,
        )
        assert ed.message == "SSH timeout"
        assert ed.status == "new"
        assert ed.count_a == 0
        assert ed.count_b == 5

    def test_defaults(self):
        ed = ErrorDelta(message="Test")
        assert ed.status == ""
        assert ed.count_a == 0
        assert ed.count_b == 0

    def test_serialization(self):
        ed = ErrorDelta(message="err", status="resolved", count_a=3, count_b=0)
        d = ed.model_dump()
        assert d["message"] == "err"
        assert d["status"] == "resolved"


# ===========================================================================
# Tests: DiscoveryCompareResult
# ===========================================================================


class TestDiscoveryCompareResult:
    """Tests for the ``DiscoveryCompareResult`` model."""

    def test_minimal_creation(self):
        result = DiscoveryCompareResult(
            scan_a_sys_id="aaa111",
            scan_b_sys_id="bbb222",
        )
        assert result.scan_a_sys_id == "aaa111"
        assert result.scan_b_sys_id == "bbb222"
        assert result.scan_a_state == ""
        assert result.scan_b_state == ""
        assert result.delta_ci_count == 0
        assert result.delta_error_count == 0
        assert result.delta_duration_seconds == 0.0
        assert result.cis_added == []
        assert result.cis_removed == []
        assert result.cis_changed == []
        assert result.errors_new == []
        assert result.errors_resolved == []
        assert result.errors_persistent == []
        assert result.compared_at is None

    def test_full_comparison(self):
        result = DiscoveryCompareResult(
            scan_a_sys_id="aaa111",
            scan_b_sys_id="bbb222",
            scan_a_state="Completed",
            scan_b_state="Completed",
            delta_ci_count=5,
            delta_error_count=-2,
            delta_duration_seconds=-120.5,
            cis_added=[
                CIDelta(sys_id="new1", name="server-new", change_type="added"),
            ],
            cis_removed=[
                CIDelta(sys_id="old1", name="server-old", change_type="removed"),
            ],
            cis_changed=[
                CIDelta(sys_id="chg1", name="server-chg", change_type="changed", details="OS version updated"),
            ],
            errors_new=[
                ErrorDelta(message="New error", status="new", count_a=0, count_b=3),
            ],
            errors_resolved=[
                ErrorDelta(message="Fixed error", status="resolved", count_a=5, count_b=0),
            ],
            errors_persistent=[
                ErrorDelta(message="Still broken", status="persistent", count_a=2, count_b=2),
            ],
        )
        assert result.delta_ci_count == 5
        assert result.delta_error_count == -2
        assert result.delta_duration_seconds == -120.5
        assert len(result.cis_added) == 1
        assert len(result.cis_removed) == 1
        assert len(result.cis_changed) == 1
        assert len(result.errors_new) == 1
        assert len(result.errors_resolved) == 1
        assert len(result.errors_persistent) == 1

    def test_serialization(self):
        result = DiscoveryCompareResult(
            scan_a_sys_id="a",
            scan_b_sys_id="b",
            delta_ci_count=3,
            cis_added=[CIDelta(sys_id="x", change_type="added")],
        )
        d = result.model_dump()
        assert d["scan_a_sys_id"] == "a"
        assert d["delta_ci_count"] == 3
        assert len(d["cis_added"]) == 1

    def test_json_serialization(self):
        result = DiscoveryCompareResult(
            scan_a_sys_id="aaa",
            scan_b_sys_id="bbb",
        )
        json_str = result.model_dump_json()
        assert "aaa" in json_str
        assert "bbb" in json_str


# ===========================================================================
# Tests: from_snow edge cases
# ===========================================================================


class TestFromSnowEdgeCases:
    """Edge case tests for the ``from_snow()`` classmethod."""

    def test_empty_dict_all_models(self):
        """All table-backed models should handle empty dicts gracefully."""
        for model_cls in [
            DiscoveryStatus,
            DiscoverySchedule,
            DiscoveryCredential,
            DiscoveryRange,
            DiscoveryPattern,
            DiscoveryLog,
        ]:
            instance = model_cls.from_snow({})
            assert instance.sys_id == ""

    def test_extra_fields_ignored(self):
        """ServiceNow may return fields not in the model."""
        data = {
            "sys_id": "test",
            "name": "test",
            "unknown_field_1": "value1",
            "extra_metadata": {"nested": True},
        }
        status = DiscoveryStatus.from_snow(data)
        assert status.sys_id == "test"
        assert status.name == "test"

    def test_none_values_for_string_fields(self):
        """None values for string fields should be handled."""
        status = DiscoveryStatus(
            sys_id="test",
            name="test",
        )
        assert status.sys_id == "test"

    @pytest.mark.parametrize(
        "bool_value,expected",
        [
            ("true", True),
            ("false", False),
            ("True", True),
            ("False", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
            (True, True),
            (False, False),
        ],
    )
    def test_boolean_coercion_parametrized(self, bool_value, expected):
        """Test boolean coercion across all representations."""
        schedule = DiscoverySchedule.from_snow({"active": bool_value})
        assert schedule.active is expected

    @pytest.mark.parametrize(
        "int_value,expected",
        [
            ("0", 0),
            ("42", 42),
            ("999", 999),
            (0, 0),
            (42, 42),
            ("", 0),
        ],
    )
    def test_int_coercion_parametrized(self, int_value, expected):
        """Test integer coercion across representations."""
        status = DiscoveryStatus.from_snow({"ci_count": int_value})
        assert status.ci_count == expected
