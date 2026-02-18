"""MCP tool for comparing ServiceNow Discovery scan results.

Provides the ``compare_discovery_runs`` function which supports COMPARE
(two specific scans) and SEQUENTIAL (last N scans for a schedule)
operations against the ``discovery_status`` and ``discovery_log`` tables.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import (
    DiscoveryCompareResult,
    DiscoveryStatus,
    ErrorDelta,
)

logger = logging.getLogger(__name__)

STATUS_TABLE = "discovery_status"
LOG_TABLE = "discovery_log"

_VALID_ACTIONS = frozenset({"compare", "sequential"})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

STATUS_FIELDS: list[str] = [
    "sys_id", "name", "state", "source", "dscl_status", "log",
    "started", "completed", "ci_count", "ip_address", "mid_server",
]

LOG_FIELDS: list[str] = [
    "sys_id", "status", "level", "message", "source", "created_on",
]


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


def compare_discovery_runs(
    action: str,
    scan_a_sys_id: str | None = None,
    scan_b_sys_id: str | None = None,
    schedule_sys_id: str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Compare the results of ServiceNow Discovery scans.

    Supports two actions:

    - **compare**: Detailed comparison of two specific scans.
    - **sequential**: Compare the last N scans for a schedule to show
      progression over time.

    Args:
        action: Operation to perform -- 'compare' or 'sequential'.
        scan_a_sys_id: First (baseline) scan sys_id (required for compare).
        scan_b_sys_id: Second (comparison) scan sys_id (required for compare).
        schedule_sys_id: Schedule sys_id (required for sequential).
        last_n: Number of recent scans to compare (default 5, for sequential).

    Returns:
        A dict with success status, data (DiscoveryCompareResult), message,
        action, and error fields.
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
        if action == "compare":
            return _action_compare(client, scan_a_sys_id, scan_b_sys_id)
        elif action == "sequential":
            return _action_sequential(client, schedule_sys_id, last_n)
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


def _get_scan_with_errors(
    client: Any, scan_sys_id: str,
) -> tuple[DiscoveryStatus, Counter[str]]:
    """Retrieve a scan and count its errors by message."""
    record = client.get_table_record(STATUS_TABLE, scan_sys_id, fields=STATUS_FIELDS)
    status = DiscoveryStatus.from_snow(record)

    log_records = client.query_table(
        LOG_TABLE,
        query=f"status={scan_sys_id}^level=Error",
        fields=LOG_FIELDS,
        limit=300,
    )

    error_counter: Counter[str] = Counter()
    for lr in log_records:
        msg = lr.get("message", "Unknown")
        key = msg[:100] if len(msg) > 100 else msg
        error_counter[key] += 1

    return status, error_counter


def _compute_duration(status: DiscoveryStatus) -> float:
    """Compute scan duration in seconds, or 0.0 if not available."""
    if status.started and status.completed:
        return (status.completed - status.started).total_seconds()
    return 0.0


def _action_compare(
    client: Any,
    scan_a_sys_id: str | None,
    scan_b_sys_id: str | None,
) -> dict[str, Any]:
    """Compare two specific discovery scans."""
    validated_a = _validate_sys_id(scan_a_sys_id, "scan_a_sys_id")
    validated_b = _validate_sys_id(scan_b_sys_id, "scan_b_sys_id")

    logger.info("Comparing scans: %s vs %s", validated_a, validated_b)

    status_a, errors_a = _get_scan_with_errors(client, validated_a)
    status_b, errors_b = _get_scan_with_errors(client, validated_b)

    duration_a = _compute_duration(status_a)
    duration_b = _compute_duration(status_b)

    # Compute error deltas
    all_error_msgs = set(errors_a.keys()) | set(errors_b.keys())
    errors_new: list[ErrorDelta] = []
    errors_resolved: list[ErrorDelta] = []
    errors_persistent: list[ErrorDelta] = []

    for msg in all_error_msgs:
        count_a = errors_a.get(msg, 0)
        count_b = errors_b.get(msg, 0)

        delta = ErrorDelta(
            message=msg,
            count_a=count_a,
            count_b=count_b,
        )

        if count_a == 0 and count_b > 0:
            delta.status = "new"
            errors_new.append(delta)
        elif count_a > 0 and count_b == 0:
            delta.status = "resolved"
            errors_resolved.append(delta)
        else:
            delta.status = "persistent"
            errors_persistent.append(delta)

    total_errors_a = sum(errors_a.values())
    total_errors_b = sum(errors_b.values())

    compare_result = DiscoveryCompareResult(
        scan_a_sys_id=validated_a,
        scan_b_sys_id=validated_b,
        scan_a_state=status_a.state,
        scan_b_state=status_b.state,
        delta_ci_count=status_b.ci_count - status_a.ci_count,
        delta_error_count=total_errors_b - total_errors_a,
        delta_duration_seconds=round(duration_b - duration_a, 1),
        errors_new=errors_new,
        errors_resolved=errors_resolved,
        errors_persistent=errors_persistent,
        compared_at=datetime.now(UTC),
    )

    return {
        "success": True,
        "data": compare_result.model_dump(mode="json"),
        "message": (
            f"Compared scan A ({status_a.state}, {status_a.ci_count} CIs) "
            f"vs B ({status_b.state}, {status_b.ci_count} CIs): "
            f"delta_ci={compare_result.delta_ci_count}, "
            f"delta_errors={compare_result.delta_error_count}"
        ),
        "action": "compare",
        "error": None,
    }


def _action_sequential(
    client: Any,
    schedule_sys_id: str | None,
    last_n: int,
) -> dict[str, Any]:
    """Compare last N scans for a schedule to show progression."""
    validated_id = _validate_sys_id(schedule_sys_id, "schedule_sys_id")

    logger.info(
        "Sequential comparison for schedule %s (last %d scans)",
        validated_id, last_n,
    )

    # Get recent scans for this schedule
    scan_records = client.query_table(
        STATUS_TABLE,
        query=f"source={validated_id}",
        fields=STATUS_FIELDS,
        limit=last_n,
        order_by="-sys_created_on",
    )

    scans = [DiscoveryStatus.from_snow(r) for r in scan_records]

    if len(scans) < 2:
        return {
            "success": True,
            "data": {
                "schedule_sys_id": validated_id,
                "scans_found": len(scans),
                "comparisons": [],
            },
            "message": (
                f"Need at least 2 scans to compare; found {len(scans)} "
                f"for schedule {validated_id}"
            ),
            "action": "sequential",
            "error": None,
        }

    # Compare consecutive pairs (newest to oldest)
    comparisons: list[dict[str, Any]] = []
    for i in range(len(scans) - 1):
        newer = scans[i]
        older = scans[i + 1]

        dur_newer = _compute_duration(newer)
        dur_older = _compute_duration(older)

        comparison: dict[str, Any] = {
            "scan_newer": {
                "sys_id": newer.sys_id,
                "name": newer.name,
                "state": newer.state,
                "ci_count": newer.ci_count,
                "started": newer.started.isoformat() if newer.started else None,
            },
            "scan_older": {
                "sys_id": older.sys_id,
                "name": older.name,
                "state": older.state,
                "ci_count": older.ci_count,
                "started": older.started.isoformat() if older.started else None,
            },
            "delta_ci_count": newer.ci_count - older.ci_count,
            "delta_duration_seconds": round(dur_newer - dur_older, 1),
        }
        comparisons.append(comparison)

    # Compute overall trend
    ci_counts = [s.ci_count for s in scans]
    if ci_counts[0] > ci_counts[-1]:
        trend = "improving"
    elif ci_counts[0] < ci_counts[-1]:
        trend = "degrading"
    else:
        trend = "stable"

    result: dict[str, Any] = {
        "schedule_sys_id": validated_id,
        "scans_analyzed": len(scans),
        "trend": trend,
        "comparisons": comparisons,
    }

    return {
        "success": True,
        "data": result,
        "message": (
            f"Sequential comparison: {len(scans)} scans, "
            f"{len(comparisons)} comparisons, trend={trend}"
        ),
        "action": "sequential",
        "error": None,
    }
