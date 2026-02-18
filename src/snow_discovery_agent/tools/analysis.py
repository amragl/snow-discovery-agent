"""MCP tool for analyzing ServiceNow Discovery scan results.

Provides the ``analyze_discovery_results`` function which supports
ANALYZE, ERRORS, TREND, and COVERAGE actions against the
``discovery_status`` and ``discovery_log`` tables.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoveryLog, DiscoveryStatus

logger = logging.getLogger(__name__)

STATUS_TABLE = "discovery_status"
LOG_TABLE = "discovery_log"

_VALID_ACTIONS = frozenset({"analyze", "errors", "trend", "coverage"})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

STATUS_FIELDS: list[str] = [
    "sys_id", "name", "state", "source", "dscl_status", "log",
    "started", "completed", "ci_count", "ip_address", "mid_server",
]

LOG_FIELDS: list[str] = [
    "sys_id", "status", "level", "message", "source", "created_on",
]

# Error categories for classification
_ERROR_CATEGORIES: dict[str, list[str]] = {
    "credential_failure": ["credential", "authentication", "login", "password", "access denied"],
    "network_timeout": ["timeout", "timed out", "unreachable", "connection refused"],
    "classification_failure": ["classification", "pattern", "classify", "unclassified"],
    "port_scan_failure": ["port scan", "port closed", "port unreachable"],
    "snmp_failure": ["snmp", "community string", "snmp timeout"],
    "ssh_failure": ["ssh", "key exchange", "host key"],
    "wmi_failure": ["wmi", "windows management", "dcom"],
}


def _validate_sys_id(sys_id: str | None, label: str) -> str:
    """Validate a sys_id is a well-formed 32-character hex string."""
    if sys_id is None or sys_id.strip() == "":
        raise ValueError(f"{label} is required for this action")
    sys_id = sys_id.strip()
    if not _SYS_ID_PATTERN.match(sys_id):
        raise ValueError(
            f"Invalid {label} format: '{sys_id}'. "
            "Expected a 32-character hexadecimal string."
        )
    return sys_id


def _categorize_error(message: str) -> str:
    """Categorize an error message into a known category.

    Args:
        message: The error message text.

    Returns:
        The category name, or 'other' if no category matches.
    """
    lower_msg = message.lower()
    for category, keywords in _ERROR_CATEGORIES.items():
        if any(kw in lower_msg for kw in keywords):
            return category
    return "other"


def analyze_discovery_results(
    action: str,
    scan_sys_id: str | None = None,
    schedule_sys_id: str | None = None,
    last_n_scans: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Analyze ServiceNow Discovery scan results and identify patterns.

    Supports four actions:

    - **analyze**: Analyze a specific scan's results (CIs, errors, duration).
    - **errors**: Categorize errors from a specific scan's logs.
    - **trend**: Analyze trends across multiple scans.
    - **coverage**: Compute IP coverage for a schedule's scans.

    Args:
        action: Operation to perform -- 'analyze', 'errors', 'trend', or 'coverage'.
        scan_sys_id: Scan sys_id (required for analyze, errors).
        schedule_sys_id: Schedule sys_id (for trend, coverage).
        last_n_scans: Number of recent scans to analyze (default 10, for trend).
        date_from: Start date filter (YYYY-MM-DD, for trend).
        date_to: End date filter (YYYY-MM-DD, for trend).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from ..server import get_client

    action = action.strip().lower()
    if action not in _VALID_ACTIONS:
        return {
            "success": False,
            "data": None,
            "message": f"Invalid action: '{action}'. Valid actions: {sorted(_VALID_ACTIONS)}",
            "action": action,
            "error": f"INVALID_ACTION: {action}",
        }

    try:
        client = get_client()
    except ServiceNowError as exc:
        logger.error("Failed to get ServiceNow client: %s", exc.message)
        return {
            "success": False,
            "data": None,
            "message": f"ServiceNow client not available: {exc.message}",
            "action": action,
            "error": exc.error_code,
        }

    try:
        if action == "analyze":
            return _action_analyze(client, scan_sys_id)
        elif action == "errors":
            return _action_errors(client, scan_sys_id)
        elif action == "trend":
            return _action_trend(
                client,
                schedule_sys_id=schedule_sys_id,
                last_n_scans=last_n_scans,
                date_from=date_from,
                date_to=date_to,
            )
        elif action == "coverage":
            return _action_coverage(client, schedule_sys_id)
    except ValueError as exc:
        return {
            "success": False,
            "data": None,
            "message": str(exc),
            "action": action,
            "error": "VALIDATION_ERROR",
        }
    except ServiceNowNotFoundError as exc:
        logger.warning("Record not found: %s", exc.message)
        return {
            "success": False,
            "data": None,
            "message": exc.message,
            "action": action,
            "error": exc.error_code,
        }
    except ServiceNowError as exc:
        logger.error("ServiceNow error during %s: %s", action, exc.message)
        return {
            "success": False,
            "data": None,
            "message": exc.message,
            "action": action,
            "error": exc.error_code,
        }

    return {
        "success": False,
        "data": None,
        "message": f"Unhandled action: {action}",
        "action": action,
        "error": "INTERNAL_ERROR",
    }


def _action_analyze(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Analyze a specific scan's results."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Analyzing discovery scan: %s", validated_id)

    # Get the status record
    record = client.get_table_record(STATUS_TABLE, validated_id, fields=STATUS_FIELDS)
    status = DiscoveryStatus.from_snow(record)

    # Get log entries
    log_records = client.query_table(
        LOG_TABLE,
        query=f"status={validated_id}",
        fields=LOG_FIELDS,
        limit=500,
    )

    logs = [DiscoveryLog.from_snow(lr) for lr in log_records]

    # Compute statistics
    error_count = sum(1 for lg in logs if lg.level.lower() == "error")
    warning_count = sum(1 for lg in logs if lg.level.lower() == "warning")
    info_count = sum(1 for lg in logs if lg.level.lower() == "info")

    duration_seconds: float | None = None
    if status.started and status.completed:
        delta = status.completed - status.started
        duration_seconds = delta.total_seconds()

    analysis: dict[str, Any] = {
        "scan_sys_id": validated_id,
        "name": status.name,
        "state": status.state,
        "ci_count": status.ci_count,
        "duration_seconds": duration_seconds,
        "log_summary": {
            "total": len(logs),
            "errors": error_count,
            "warnings": warning_count,
            "info": info_count,
        },
        "ip_address": status.ip_address,
        "mid_server": status.mid_server,
    }

    return {
        "success": True,
        "data": analysis,
        "message": f"Analyzed scan '{status.name}': {status.ci_count} CIs, {error_count} errors",
        "action": "analyze",
        "error": None,
    }


def _action_errors(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Categorize errors from a specific scan's logs."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Analyzing errors for discovery scan: %s", validated_id)

    # Get error and warning log entries
    log_records = client.query_table(
        LOG_TABLE,
        query=f"status={validated_id}^levelINError,Warning",
        fields=LOG_FIELDS,
        limit=500,
    )

    logs = [DiscoveryLog.from_snow(lr) for lr in log_records]

    # Categorize errors
    category_counter: Counter[str] = Counter()
    categorized_errors: list[dict[str, Any]] = []

    for lg in logs:
        category = _categorize_error(lg.message)
        category_counter[category] += 1
        categorized_errors.append({
            "message": lg.message[:200],
            "level": lg.level,
            "category": category,
            "source": lg.source,
        })

    # Top errors by category
    top_categories = [
        {"category": cat, "count": count}
        for cat, count in category_counter.most_common(10)
    ]

    return {
        "success": True,
        "data": {
            "scan_sys_id": validated_id,
            "total_errors": len(logs),
            "by_category": top_categories,
            "errors": categorized_errors[:50],  # Limit to first 50
        },
        "message": f"Found {len(logs)} error/warning entries in {len(category_counter)} categories",
        "action": "errors",
        "error": None,
    }


def _action_trend(
    client: Any,
    *,
    schedule_sys_id: str | None = None,
    last_n_scans: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Analyze trends across multiple scans."""
    logger.info(
        "Analyzing discovery trends (schedule=%s, last_n=%d, from=%s, to=%s)",
        schedule_sys_id, last_n_scans, date_from, date_to,
    )

    # Build query
    conditions: list[str] = []
    if schedule_sys_id is not None and schedule_sys_id.strip():
        _validate_sys_id(schedule_sys_id, "schedule_sys_id")
        conditions.append(f"source={schedule_sys_id.strip()}")
    if date_from is not None and date_from.strip():
        conditions.append(f"started>={date_from.strip()}")
    if date_to is not None and date_to.strip():
        conditions.append(f"started<={date_to.strip()}")

    query = "^".join(conditions) if conditions else None

    records = client.query_table(
        STATUS_TABLE,
        query=query,
        fields=STATUS_FIELDS,
        limit=last_n_scans,
        order_by="-sys_created_on",
    )

    scans = [DiscoveryStatus.from_snow(r) for r in records]

    if not scans:
        return {
            "success": True,
            "data": {"scans": [], "trend": "no_data"},
            "message": "No scans found for the specified criteria",
            "action": "trend",
            "error": None,
        }

    # Compute trend metrics
    total_cis = sum(s.ci_count for s in scans)
    completed_count = sum(1 for s in scans if s.state == "Completed")
    error_count = sum(1 for s in scans if s.state == "Error")
    success_rate = (completed_count / len(scans) * 100) if scans else 0.0

    durations: list[float] = []
    for s in scans:
        if s.started and s.completed:
            durations.append((s.completed - s.started).total_seconds())

    avg_duration = sum(durations) / len(durations) if durations else 0.0

    # Determine trend direction based on CI counts
    ci_counts = [s.ci_count for s in scans]
    if len(ci_counts) >= 2:
        first_half = ci_counts[len(ci_counts) // 2:]  # older scans
        second_half = ci_counts[:len(ci_counts) // 2]  # newer scans
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        if avg_second > avg_first * 1.1:
            trend_direction = "improving"
        elif avg_second < avg_first * 0.9:
            trend_direction = "degrading"
        else:
            trend_direction = "stable"
    else:
        trend_direction = "insufficient_data"

    trend_data: dict[str, Any] = {
        "scan_count": len(scans),
        "total_cis_discovered": total_cis,
        "completed": completed_count,
        "errors": error_count,
        "success_rate_percent": round(success_rate, 1),
        "avg_duration_seconds": round(avg_duration, 1),
        "trend_direction": trend_direction,
        "scans": [
            {
                "sys_id": s.sys_id,
                "name": s.name,
                "state": s.state,
                "ci_count": s.ci_count,
                "started": s.started.isoformat() if s.started else None,
            }
            for s in scans
        ],
    }

    return {
        "success": True,
        "data": trend_data,
        "message": (
            f"Trend analysis: {len(scans)} scans, "
            f"{success_rate:.0f}% success rate, trend={trend_direction}"
        ),
        "action": "trend",
        "error": None,
    }


def _action_coverage(client: Any, schedule_sys_id: str | None) -> dict[str, Any]:
    """Compute IP coverage for a schedule's scans."""
    validated_id = _validate_sys_id(schedule_sys_id, "schedule_sys_id")
    logger.info("Computing discovery coverage for schedule: %s", validated_id)

    # Get recent scans for this schedule
    scan_records = client.query_table(
        STATUS_TABLE,
        query=f"source={validated_id}^state=Completed",
        fields=STATUS_FIELDS,
        limit=50,
        order_by="-sys_created_on",
    )

    scans = [DiscoveryStatus.from_snow(r) for r in scan_records]

    # Collect unique discovered IPs
    discovered_ips: set[str] = set()
    for s in scans:
        if s.ip_address and s.ip_address.strip():
            discovered_ips.add(s.ip_address.strip())

    # Get configured ranges for this schedule (via discovery_range)
    range_records = client.query_table(
        "discovery_range",
        query="active=true",
        fields=["sys_id", "name", "type", "range_start", "range_end", "active"],
        limit=200,
    )

    coverage: dict[str, Any] = {
        "schedule_sys_id": validated_id,
        "total_scans_analyzed": len(scans),
        "unique_ips_discovered": len(discovered_ips),
        "configured_ranges": len(range_records),
        "discovered_ips": sorted(discovered_ips)[:100],  # Limit output
    }

    return {
        "success": True,
        "data": coverage,
        "message": (
            f"Coverage: {len(discovered_ips)} unique IPs from "
            f"{len(scans)} scans, {len(range_records)} configured ranges"
        ),
        "action": "coverage",
        "error": None,
    }
