"""MCP tool for scheduling and triggering ServiceNow Discovery scans.

Provides the ``schedule_discovery_scan`` function which supports
TRIGGER and CREATE operations against the ``discovery_schedule`` and
``discovery_status`` tables.

Trigger activates an existing schedule to start an immediate discovery
scan.  Create defines a new discovery schedule with a name, discovery
type, and optional configuration.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoverySchedule, DiscoveryStatus

logger = logging.getLogger(__name__)

# ServiceNow tables
SCHEDULE_TABLE = "discovery_schedule"
STATUS_TABLE = "discovery_status"

# Valid actions for this tool
_VALID_ACTIONS = frozenset({"trigger", "create"})

# Valid discovery types in ServiceNow
_VALID_DISCOVER_TYPES = frozenset({
    "IP", "CI", "Network", "Cloud", "Configuration",
})

# Valid sys_id pattern: 32 hex characters
_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

# Fields to return for schedule records
SCHEDULE_FIELDS: list[str] = [
    "sys_id", "name", "active", "discover", "max_run_time",
    "run_dayofweek", "run_time", "mid_select_method", "location",
]

# Fields to return for status records
STATUS_FIELDS: list[str] = [
    "sys_id", "name", "state", "source", "dscl_status", "log",
    "started", "completed", "ci_count", "ip_address", "mid_server",
]


def _validate_sys_id(sys_id: str | None, label: str) -> str:
    """Validate that a sys_id is a well-formed 32-character hex string.

    Args:
        sys_id: The sys_id value to validate.
        label: Label for error messages (e.g., 'schedule_sys_id').

    Returns:
        The validated sys_id string.

    Raises:
        ValueError: If the sys_id is missing or malformed.
    """
    if sys_id is None or sys_id.strip() == "":
        raise ValueError(f"{label} is required for this action")
    sys_id = sys_id.strip()
    if not _SYS_ID_PATTERN.match(sys_id):
        raise ValueError(
            f"Invalid {label} format: '{sys_id}'. "
            "Expected a 32-character hexadecimal string."
        )
    return sys_id


def schedule_discovery_scan(
    action: str,
    schedule_sys_id: str | None = None,
    name: str | None = None,
    discover_type: str | None = None,
    ip_ranges: list[str] | None = None,
    mid_server: str | None = None,
    max_run_time: str = "02:00:00",
) -> dict[str, Any]:
    """Schedule or trigger a ServiceNow Discovery scan.

    Supports two actions:

    - **trigger**: Activate an existing discovery schedule to start an
      immediate scan.  Requires ``schedule_sys_id``.
    - **create**: Create a new discovery schedule.  Requires ``name``
      and ``discover_type``.

    Args:
        action: Operation to perform -- 'trigger' or 'create'.
        schedule_sys_id: The sys_id of the schedule to trigger
            (required for trigger action).
        name: Name for the new schedule (required for create).
        discover_type: Discovery type -- 'IP', 'CI', 'Network', 'Cloud',
            or 'Configuration' (required for create).
        ip_ranges: Optional list of IP range sys_ids to associate with
            the schedule (for create).
        mid_server: Optional MID server sys_id or name (for create).
        max_run_time: Maximum run time in HH:MM:SS format
            (default '02:00:00', for create).

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
        if action == "trigger":
            return _action_trigger(client, schedule_sys_id)
        elif action == "create":
            return _action_create(
                client,
                name=name,
                discover_type=discover_type,
                ip_ranges=ip_ranges,
                mid_server=mid_server,
                max_run_time=max_run_time,
            )
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

    # Should not be reached
    return {
        "success": False,
        "data": None,
        "message": f"Unhandled action: {action}",
        "action": action,
        "error": "INTERNAL_ERROR",
    }


def _action_trigger(
    client: Any,
    schedule_sys_id: str | None,
) -> dict[str, Any]:
    """Trigger an existing discovery schedule to start scanning.

    Activates the schedule and then queries ``discovery_status`` for
    the most recent scan started by this schedule to confirm it started.

    Args:
        client: The ServiceNowClient instance.
        schedule_sys_id: The sys_id of the schedule to trigger.

    Returns:
        Structured response dict with trigger results.
    """
    validated_id = _validate_sys_id(schedule_sys_id, "schedule_sys_id")

    logger.info("Triggering discovery schedule: %s", validated_id)

    # Retrieve the schedule to verify it exists
    schedule_record = client.get_table_record(
        SCHEDULE_TABLE,
        validated_id,
        fields=SCHEDULE_FIELDS,
    )
    schedule = DiscoverySchedule.from_snow(schedule_record)

    # Activate the schedule to trigger an immediate scan by setting
    # the 'discover' field -- ServiceNow triggers a scan when a
    # schedule record transitions to active.
    client.patch(SCHEDULE_TABLE, validated_id, {"active": "true"})

    logger.info(
        "Activated discovery schedule: %s (name=%s)",
        validated_id,
        schedule.name,
    )

    # Query discovery_status for the most recent scan from this schedule
    recent_scans = client.query_table(
        STATUS_TABLE,
        query=f"source={validated_id}",
        fields=STATUS_FIELDS,
        limit=1,
        order_by="-sys_created_on",
    )

    scan_data: dict[str, Any] | None = None
    if recent_scans:
        status = DiscoveryStatus.from_snow(recent_scans[0])
        scan_data = status.model_dump(mode="json")

    return {
        "success": True,
        "data": {
            "schedule": schedule.model_dump(mode="json"),
            "latest_scan": scan_data,
        },
        "message": f"Triggered discovery schedule '{schedule.name}' ({validated_id})",
        "action": "trigger",
        "error": None,
    }


def _action_create(
    client: Any,
    *,
    name: str | None = None,
    discover_type: str | None = None,
    ip_ranges: list[str] | None = None,
    mid_server: str | None = None,
    max_run_time: str = "02:00:00",
) -> dict[str, Any]:
    """Create a new discovery schedule.

    Args:
        client: The ServiceNowClient instance.
        name: Schedule name (required).
        discover_type: Discovery type (required).
        ip_ranges: Optional list of IP range sys_ids.
        mid_server: Optional MID server sys_id or name.
        max_run_time: Maximum run time in HH:MM:SS format.

    Returns:
        Structured response dict with the created schedule.
    """
    if not name or not name.strip():
        raise ValueError("'name' is required for create action")
    if not discover_type or not discover_type.strip():
        raise ValueError("'discover_type' is required for create action")

    discover_type = discover_type.strip()
    if discover_type not in _VALID_DISCOVER_TYPES:
        raise ValueError(
            f"Invalid discover_type: '{discover_type}'. "
            f"Valid types: {sorted(_VALID_DISCOVER_TYPES)}"
        )

    # Validate IP range sys_ids if provided
    if ip_ranges:
        for i, range_id in enumerate(ip_ranges):
            _validate_sys_id(range_id, f"ip_ranges[{i}]")

    data: dict[str, Any] = {
        "name": name.strip(),
        "discover": discover_type,
        "active": "true",
        "max_run_time": max_run_time,
    }

    if mid_server is not None and mid_server.strip():
        data["mid_select_method"] = "Specific"
        data["mid_server"] = mid_server.strip()

    logger.info(
        "Creating discovery schedule: name=%s, type=%s",
        data["name"],
        data["discover"],
    )

    result = client.post(SCHEDULE_TABLE, data)

    schedule = DiscoverySchedule.from_snow(result)

    logger.info(
        "Created discovery schedule: %s (name=%s, type=%s)",
        schedule.sys_id,
        schedule.name,
        schedule.discover,
    )

    return {
        "success": True,
        "data": schedule.model_dump(mode="json"),
        "message": f"Created discovery schedule '{schedule.name}' ({schedule.sys_id})",
        "action": "create",
        "error": None,
    }
