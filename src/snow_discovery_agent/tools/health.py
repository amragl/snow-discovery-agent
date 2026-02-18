"""MCP tool for computing overall ServiceNow Discovery health metrics.

Provides the ``get_discovery_health`` function which aggregates data from
``discovery_status``, ``discovery_schedule``, ``discovery_credential``,
``discovery_range``, and ``discovery_log`` to compute a health score (0-100)
with sub-metrics for scan, schedule, credential, and range health.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from ..exceptions import ServiceNowError
from ..models import (
    DiscoveryHealthSummary,
    DiscoveryStatus,
    ErrorCount,
)

logger = logging.getLogger(__name__)

STATUS_TABLE = "discovery_status"
SCHEDULE_TABLE = "discovery_schedule"
CREDENTIAL_TABLE = "discovery_credential"
RANGE_TABLE = "discovery_range"
LOG_TABLE = "discovery_log"

_VALID_PERIODS = frozenset({"day", "week", "month"})

_PERIOD_DAYS: dict[str, int] = {
    "day": 1,
    "week": 7,
    "month": 30,
}


def get_discovery_health(
    period: str = "week",
    include_recommendations: bool = True,
) -> dict[str, Any]:
    """Compute overall ServiceNow Discovery health metrics.

    Aggregates data from multiple Discovery tables to compute a composite
    health score (0-100) with sub-metrics for scan health, schedule health,
    credential health, and range health.

    Health score ratings:
    - **Healthy** (>80): Discovery is operating well.
    - **Warning** (50-80): Some issues need attention.
    - **Critical** (<50): Significant problems require immediate action.

    Args:
        period: Analysis period -- 'day', 'week', or 'month' (default 'week').
        include_recommendations: Include actionable recommendations (default True).

    Returns:
        A dict with success status, data (DiscoveryHealthSummary), message,
        action, and error fields.
    """
    from ..server import get_client

    period = period.strip().lower()
    if period not in _VALID_PERIODS:
        return {
            "success": False,
            "data": None,
            "message": f"Invalid period: '{period}'. Valid periods: {sorted(_VALID_PERIODS)}",
            "action": "health",
            "error": "VALIDATION_ERROR",
        }

    try:
        client = get_client()
    except ServiceNowError as exc:
        logger.error("Failed to get ServiceNow client: %s", exc.message)
        return {
            "success": False,
            "data": None,
            "message": f"ServiceNow client not available: {exc.message}",
            "action": "health",
            "error": exc.error_code,
        }

    try:
        return _compute_health(client, period=period, include_recommendations=include_recommendations)
    except ServiceNowError as exc:
        logger.error("ServiceNow error during health check: %s", exc.message)
        return {
            "success": False,
            "data": None,
            "message": exc.message,
            "action": "health",
            "error": exc.error_code,
        }


def _compute_health(
    client: Any,
    *,
    period: str,
    include_recommendations: bool,
) -> dict[str, Any]:
    """Compute all health metrics and assemble the response."""
    logger.info("Computing discovery health for period: %s", period)

    now = datetime.now(UTC)
    days = _PERIOD_DAYS[period]
    since = now - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    # ---- Scan health ----
    scan_records = client.query_table(
        STATUS_TABLE,
        query=f"started>={since_str}",
        fields=[
            "sys_id", "name", "state", "started", "completed",
            "ci_count", "ip_address",
        ],
        limit=500,
    )

    scans = [DiscoveryStatus.from_snow(r) for r in scan_records]
    total_scans = len(scans)
    completed = sum(1 for s in scans if s.state == "Completed")
    failed = sum(1 for s in scans if s.state == "Error")
    cancelled = sum(1 for s in scans if s.state == "Cancelled")
    total_cis = sum(s.ci_count for s in scans)

    error_rate = (failed / total_scans * 100) if total_scans > 0 else 0.0

    durations: list[float] = []
    for s in scans:
        if s.started and s.completed:
            durations.append((s.completed - s.started).total_seconds())
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    # Scan health score component (0-100): penalize for error rate
    scan_score = max(0, 100 - int(error_rate * 2))

    # ---- Schedule health ----
    schedule_records = client.query_table(
        SCHEDULE_TABLE,
        fields=["sys_id", "name", "active", "discover"],
        limit=500,
    )
    total_schedules = len(schedule_records)
    active_schedules = sum(
        1 for s in schedule_records
        if s.get("active") in ("true", True)
    )
    inactive_schedules = total_schedules - active_schedules

    # Schedule score: penalize if many inactive or no schedules
    if total_schedules == 0:
        schedule_score = 50
    else:
        active_ratio = active_schedules / total_schedules
        schedule_score = int(active_ratio * 100)

    # ---- Credential health ----
    cred_records = client.query_table(
        CREDENTIAL_TABLE,
        fields=["sys_id", "name", "active", "type"],
        limit=500,
    )
    total_creds = len(cred_records)
    active_creds = sum(
        1 for c in cred_records
        if c.get("active") in ("true", True)
    )
    inactive_creds = total_creds - active_creds

    if total_creds == 0:
        cred_score = 50
    else:
        cred_active_ratio = active_creds / total_creds
        cred_score = int(cred_active_ratio * 100)

    # ---- Range health ----
    range_records = client.query_table(
        RANGE_TABLE,
        fields=["sys_id", "name", "active", "type"],
        limit=500,
    )
    total_ranges = len(range_records)
    active_ranges = sum(
        1 for r in range_records
        if r.get("active") in ("true", True)
    )

    if total_ranges == 0:
        range_score = 50
    else:
        range_active_ratio = active_ranges / total_ranges
        range_score = int(range_active_ratio * 100)

    # ---- Top errors ----
    top_errors: list[ErrorCount] = []
    if failed > 0:
        error_log_records = client.query_table(
            LOG_TABLE,
            query=f"created_on>={since_str}^level=Error",
            fields=["sys_id", "message", "level"],
            limit=200,
        )

        error_counter: Counter[str] = Counter()
        for lr in error_log_records:
            msg = lr.get("message", "Unknown error")
            # Truncate for grouping
            key = msg[:100] if len(msg) > 100 else msg
            error_counter[key] += 1

        top_errors = [
            ErrorCount(message=msg, count=count, level="Error")
            for msg, count in error_counter.most_common(10)
        ]

    # ---- Overall health score (weighted average) ----
    health_score = int(
        scan_score * 0.4
        + schedule_score * 0.2
        + cred_score * 0.2
        + range_score * 0.2
    )
    health_score = max(0, min(100, health_score))

    # ---- Build summary ----
    summary = DiscoveryHealthSummary(
        total_scans=total_scans,
        successful=completed,
        failed=failed,
        cancelled=cancelled,
        error_rate=round(error_rate, 1),
        avg_duration_seconds=round(avg_duration, 1),
        total_cis_discovered=total_cis,
        top_errors=top_errors,
        health_score=health_score,
        period=period,
        computed_at=now,
    )

    # ---- Sub-metrics ----
    sub_metrics: dict[str, Any] = {
        "scan_health": {
            "score": scan_score,
            "total_scans": total_scans,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "error_rate_percent": round(error_rate, 1),
            "avg_duration_seconds": round(avg_duration, 1),
        },
        "schedule_health": {
            "score": schedule_score,
            "total": total_schedules,
            "active": active_schedules,
            "inactive": inactive_schedules,
        },
        "credential_health": {
            "score": cred_score,
            "total": total_creds,
            "active": active_creds,
            "inactive": inactive_creds,
        },
        "range_health": {
            "score": range_score,
            "total": total_ranges,
            "active": active_ranges,
            "inactive": total_ranges - active_ranges,
        },
    }

    # ---- Recommendations ----
    recommendations: list[str] = []
    if include_recommendations:
        if error_rate > 20:
            recommendations.append(
                f"High error rate ({error_rate:.0f}%). Review failed scans "
                f"and use the 'remediate_discovery_failures' tool to diagnose issues."
            )
        if inactive_schedules > active_schedules and total_schedules > 0:
            recommendations.append(
                f"{inactive_schedules} inactive schedule(s) detected. "
                "Review and activate needed schedules."
            )
        if inactive_creds > 0:
            recommendations.append(
                f"{inactive_creds} inactive credential(s). "
                "Verify they are no longer needed or re-activate."
            )
        if total_ranges == 0:
            recommendations.append(
                "No discovery ranges configured. Add IP ranges to enable discovery."
            )
        if total_scans == 0:
            recommendations.append(
                f"No scans in the last {period}. Check schedule configuration."
            )
        if health_score >= 80:
            recommendations.append("Discovery health is good. Continue monitoring.")

    # Determine status label
    if health_score >= 80:
        status_label = "healthy"
    elif health_score >= 50:
        status_label = "warning"
    else:
        status_label = "critical"

    result_data: dict[str, Any] = {
        "summary": summary.model_dump(mode="json"),
        "sub_metrics": sub_metrics,
        "status": status_label,
        "recommendations": recommendations,
    }

    return {
        "success": True,
        "data": result_data,
        "message": f"Discovery health: {health_score}/100 ({status_label}) for {period}",
        "action": "health",
        "error": None,
    }
