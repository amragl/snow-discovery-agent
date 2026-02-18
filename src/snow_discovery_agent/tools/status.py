"""MCP tool for checking ServiceNow Discovery scan status and results.

Provides the ``get_discovery_status`` function which supports GET, LIST,
DETAILS, and POLL operations against the ``discovery_status`` table.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoveryStatus

logger = logging.getLogger(__name__)

TABLE_NAME = "discovery_status"

_VALID_ACTIONS = frozenset({"get", "list", "details", "poll"})

_VALID_STATES = frozenset({
    "Starting", "Active", "Completed", "Cancelled", "Error",
})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

STATUS_FIELDS: list[str] = [
    "sys_id", "name", "state", "source", "dscl_status", "log",
    "started", "completed", "ci_count", "ip_address", "mid_server",
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


def _build_list_query(
    state: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str | None:
    """Build a ServiceNow encoded query string from filter parameters."""
    conditions: list[str] = []

    if state is not None and state.strip():
        conditions.append(f"state={state.strip()}")

    if date_from is not None and date_from.strip():
        conditions.append(f"started>={date_from.strip()}")

    if date_to is not None and date_to.strip():
        conditions.append(f"started<={date_to.strip()}")

    if not conditions:
        return None

    return "^".join(conditions)


def get_discovery_status(
    action: str,
    scan_sys_id: str | None = None,
    state: str | None = None,
    limit: int = 20,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Check the status and results of ServiceNow Discovery scans.

    Supports four actions:

    - **get**: Retrieve the status of a specific scan by sys_id.
    - **list**: List recent discovery scans with optional filters.
    - **details**: Get detailed results for a specific scan.
    - **poll**: Check whether a scan has completed.

    Args:
        action: Operation to perform -- 'get', 'list', 'details', or 'poll'.
        scan_sys_id: The sys_id of the scan (required for get, details, poll).
        state: Filter by scan state for list action
            (Starting, Active, Completed, Cancelled, Error).
        limit: Maximum records to return for list (default 20).
        date_from: Filter scans started on or after this date (YYYY-MM-DD).
        date_to: Filter scans started on or before this date (YYYY-MM-DD).

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
        if action == "get":
            return _action_get(client, scan_sys_id)
        elif action == "list":
            return _action_list(
                client,
                state=state,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
            )
        elif action == "details":
            return _action_details(client, scan_sys_id)
        elif action == "poll":
            return _action_poll(client, scan_sys_id)
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


def _action_get(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Retrieve the status of a specific discovery scan."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Getting discovery status: %s", validated_id)

    record = client.get_table_record(TABLE_NAME, validated_id, fields=STATUS_FIELDS)
    status = DiscoveryStatus.from_snow(record)

    logger.info(
        "Retrieved discovery status: %s (state=%s)",
        validated_id,
        status.state,
    )

    return {
        "success": True,
        "data": status.model_dump(mode="json"),
        "message": f"Retrieved scan status '{status.name}' (state={status.state})",
        "action": "get",
        "error": None,
    }


def _action_list(
    client: Any,
    *,
    state: str | None = None,
    limit: int = 20,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """List recent discovery scans with optional filters."""
    if state is not None and state.strip() and state.strip() not in _VALID_STATES:
        raise ValueError(
            f"Invalid state filter: '{state}'. "
            f"Valid states: {sorted(_VALID_STATES)}"
        )

    logger.info(
        "Listing discovery scans (state=%s, limit=%d, from=%s, to=%s)",
        state, limit, date_from, date_to,
    )

    query = _build_list_query(state=state, date_from=date_from, date_to=date_to)

    records = client.query_table(
        TABLE_NAME,
        query=query,
        fields=STATUS_FIELDS,
        limit=limit,
        order_by="-sys_created_on",
    )

    scans = []
    for record in records:
        status = DiscoveryStatus.from_snow(record)
        scans.append(status.model_dump(mode="json"))

    logger.info("Listed %d discovery scans", len(scans))

    return {
        "success": True,
        "data": scans,
        "message": f"Found {len(scans)} scan(s)",
        "action": "list",
        "error": None,
    }


def _action_details(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Get detailed results for a specific scan, including logs."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Getting discovery scan details: %s", validated_id)

    # Get the status record
    record = client.get_table_record(TABLE_NAME, validated_id, fields=STATUS_FIELDS)
    status = DiscoveryStatus.from_snow(record)

    # Get associated log entries from discovery_log
    log_records = client.query_table(
        "discovery_log",
        query=f"status={validated_id}",
        fields=["sys_id", "level", "message", "source", "created_on"],
        limit=100,
        order_by="-created_on",
    )

    # Compute duration if both started and completed are available
    duration_seconds: float | None = None
    if status.started and status.completed:
        delta = status.completed - status.started
        duration_seconds = delta.total_seconds()

    details: dict[str, Any] = {
        "status": status.model_dump(mode="json"),
        "log_entries": log_records,
        "log_entry_count": len(log_records),
        "duration_seconds": duration_seconds,
    }

    return {
        "success": True,
        "data": details,
        "message": f"Retrieved details for scan '{status.name}' ({len(log_records)} log entries)",
        "action": "details",
        "error": None,
    }


def _action_poll(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Poll a scan to check if it has completed."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Polling discovery scan: %s", validated_id)

    record = client.get_table_record(TABLE_NAME, validated_id, fields=STATUS_FIELDS)
    status = DiscoveryStatus.from_snow(record)

    is_complete = status.state in ("Completed", "Cancelled", "Error")

    return {
        "success": True,
        "data": {
            "sys_id": status.sys_id,
            "state": status.state,
            "is_complete": is_complete,
            "ci_count": status.ci_count,
            "started": status.started.isoformat() if status.started else None,
            "completed": status.completed.isoformat() if status.completed else None,
        },
        "message": f"Scan '{status.name}' state: {status.state} (complete={is_complete})",
        "action": "poll",
        "error": None,
    }
