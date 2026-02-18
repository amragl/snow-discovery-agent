"""MCP tool for listing and viewing ServiceNow Discovery schedule configurations.

Provides the ``list_discovery_schedules`` function which supports LIST,
GET, and SUMMARY operations against the ``discovery_schedule`` table.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoverySchedule

logger = logging.getLogger(__name__)

TABLE_NAME = "discovery_schedule"

_VALID_ACTIONS = frozenset({"list", "get", "summary"})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

SCHEDULE_FIELDS: list[str] = [
    "sys_id", "name", "active", "discover", "max_run_time",
    "run_dayofweek", "run_time", "mid_select_method", "location",
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


def list_discovery_schedules(
    action: str,
    schedule_sys_id: str | None = None,
    active: bool | None = None,
    discover_type: str | None = None,
    name_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List and view ServiceNow Discovery schedule configurations.

    Supports three actions:

    - **list**: Query all discovery schedules with optional filters.
    - **get**: Retrieve a single schedule by sys_id with full details.
    - **summary**: Return a summary view with counts and status.

    Args:
        action: Operation to perform -- 'list', 'get', or 'summary'.
        schedule_sys_id: The sys_id of the schedule (required for get).
        active: Filter by active status (for list).
        discover_type: Filter by discovery type (for list).
        name_filter: Filter by name pattern using LIKE (for list).
        limit: Maximum records to return for list (default 100).

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
        if action == "list":
            return _action_list(
                client,
                active=active,
                discover_type=discover_type,
                name_filter=name_filter,
                limit=limit,
            )
        elif action == "get":
            return _action_get(client, schedule_sys_id)
        elif action == "summary":
            return _action_summary(client)
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


def _build_list_query(
    active: bool | None = None,
    discover_type: str | None = None,
    name_filter: str | None = None,
) -> str | None:
    """Build a ServiceNow encoded query string from filter parameters."""
    conditions: list[str] = []

    if active is not None:
        conditions.append(f"active={'true' if active else 'false'}")

    if discover_type is not None and discover_type.strip():
        conditions.append(f"discover={discover_type.strip()}")

    if name_filter is not None and name_filter.strip():
        conditions.append(f"nameLIKE{name_filter.strip()}")

    if not conditions:
        return None

    return "^".join(conditions)


def _action_list(
    client: Any,
    *,
    active: bool | None = None,
    discover_type: str | None = None,
    name_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List discovery schedules with optional filters."""
    logger.info(
        "Listing discovery schedules (active=%s, type=%s, name=%s, limit=%d)",
        active, discover_type, name_filter, limit,
    )

    query = _build_list_query(
        active=active,
        discover_type=discover_type,
        name_filter=name_filter,
    )

    records = client.query_table(
        TABLE_NAME,
        query=query,
        fields=SCHEDULE_FIELDS,
        limit=limit,
    )

    schedules = []
    for record in records:
        schedule = DiscoverySchedule.from_snow(record)
        schedules.append(schedule.model_dump(mode="json"))

    logger.info("Listed %d discovery schedules", len(schedules))

    return {
        "success": True,
        "data": schedules,
        "message": f"Found {len(schedules)} schedule(s)",
        "action": "list",
        "error": None,
    }


def _action_get(client: Any, schedule_sys_id: str | None) -> dict[str, Any]:
    """Retrieve a single discovery schedule by sys_id."""
    validated_id = _validate_sys_id(schedule_sys_id, "schedule_sys_id")
    logger.info("Getting discovery schedule: %s", validated_id)

    record = client.get_table_record(TABLE_NAME, validated_id, fields=SCHEDULE_FIELDS)
    schedule = DiscoverySchedule.from_snow(record)

    logger.info(
        "Retrieved discovery schedule: %s (name=%s)",
        validated_id,
        schedule.name,
    )

    return {
        "success": True,
        "data": schedule.model_dump(mode="json"),
        "message": f"Retrieved schedule '{schedule.name}' ({validated_id})",
        "action": "get",
        "error": None,
    }


def _action_summary(client: Any) -> dict[str, Any]:
    """Return a summary view of all discovery schedules."""
    logger.info("Computing discovery schedule summary")

    # Get all schedules
    records = client.query_table(
        TABLE_NAME,
        fields=SCHEDULE_FIELDS,
        limit=500,
    )

    schedules = [DiscoverySchedule.from_snow(r) for r in records]
    total = len(schedules)
    active_count = sum(1 for s in schedules if s.active)
    inactive_count = total - active_count

    # Group by discovery type
    type_counts: dict[str, int] = {}
    for s in schedules:
        dtype = s.discover or "Unknown"
        type_counts[dtype] = type_counts.get(dtype, 0) + 1

    summary: dict[str, Any] = {
        "total_schedules": total,
        "active": active_count,
        "inactive": inactive_count,
        "by_type": type_counts,
    }

    logger.info(
        "Schedule summary: total=%d, active=%d, inactive=%d",
        total, active_count, inactive_count,
    )

    return {
        "success": True,
        "data": summary,
        "message": f"Summary: {total} schedule(s) ({active_count} active, {inactive_count} inactive)",
        "action": "summary",
        "error": None,
    }
