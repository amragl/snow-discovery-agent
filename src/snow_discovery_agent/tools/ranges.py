"""MCP tool for managing ServiceNow Discovery IP ranges.

Provides the ``manage_discovery_ranges`` function which supports LIST,
GET, CREATE, UPDATE, DELETE, and VALIDATE operations against the
``discovery_range`` table.  Includes IPv4/IPv6 validation and CIDR support.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoveryRange

logger = logging.getLogger(__name__)

TABLE_NAME = "discovery_range"

_VALID_ACTIONS = frozenset({"list", "get", "create", "update", "delete", "validate"})

_VALID_RANGE_TYPES = frozenset({"IP Range", "IP Network", "IP Address"})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

RANGE_FIELDS: list[str] = [
    "sys_id", "name", "type", "active", "range_start", "range_end", "include",
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


def _validate_ip_address(ip_str: str, label: str) -> str:
    """Validate an IPv4 or IPv6 address string.

    Args:
        ip_str: The IP address string.
        label: Label for error messages.

    Returns:
        The validated IP address string.

    Raises:
        ValueError: If the IP address is invalid.
    """
    ip_str = ip_str.strip()
    try:
        ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise ValueError(
            f"Invalid IP address for {label}: '{ip_str}'. {exc}"
        ) from exc
    return ip_str


def _validate_cidr(cidr_str: str, label: str) -> str:
    """Validate a CIDR network string.

    Args:
        cidr_str: The CIDR notation string (e.g., '10.0.0.0/24').
        label: Label for error messages.

    Returns:
        The validated CIDR string.

    Raises:
        ValueError: If the CIDR notation is invalid.
    """
    cidr_str = cidr_str.strip()
    try:
        ipaddress.ip_network(cidr_str, strict=False)
    except ValueError as exc:
        raise ValueError(
            f"Invalid CIDR network for {label}: '{cidr_str}'. {exc}"
        ) from exc
    return cidr_str


def _validate_ip_range(start: str, end: str) -> None:
    """Validate that range_end >= range_start for IP Range type.

    Args:
        start: The start IP address.
        end: The end IP address.

    Raises:
        ValueError: If end < start or addresses are of different families.
    """
    start_addr = ipaddress.ip_address(start)
    end_addr = ipaddress.ip_address(end)

    if type(start_addr) is not type(end_addr):
        raise ValueError(
            f"IP address family mismatch: start={start} ({type(start_addr).__name__}) "
            f"vs end={end} ({type(end_addr).__name__})"
        )

    # Compare as integers to avoid mypy union type complaints
    if int(end_addr) < int(start_addr):
        raise ValueError(
            f"Range end ({end}) must be >= range start ({start})"
        )


def manage_discovery_ranges(
    action: str,
    sys_id: str | None = None,
    name: str | None = None,
    range_type: str | None = None,
    range_start: str | None = None,
    range_end: str | None = None,
    active: bool | None = None,
    include: bool | None = None,
    filter_type: str | None = None,
    filter_active: bool | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Manage ServiceNow Discovery IP ranges (CRUD + validate).

    Supports six actions:

    - **list**: Query ranges with optional filters.
    - **get**: Retrieve a single range by sys_id.
    - **create**: Create a new range. Requires name, range_type, range_start.
    - **update**: Update an existing range by sys_id.
    - **delete**: Delete a range by sys_id.
    - **validate**: Validate IP range parameters without creating.

    Args:
        action: Operation to perform.
        sys_id: The sys_id of the range (required for get, update, delete).
        name: Range name (required for create).
        range_type: 'IP Range', 'IP Network', or 'IP Address' (required for create).
        range_start: Start IP, CIDR, or single IP (required for create).
        range_end: End IP address (required for IP Range type).
        active: Whether the range is active.
        include: Whether to include or exclude this range.
        filter_type: Filter list results by range type.
        filter_active: Filter list results by active status.
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

    # Validate action does not need a client
    if action == "validate":
        return _action_validate(
            range_type=range_type,
            range_start=range_start,
            range_end=range_end,
        )

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
                filter_type=filter_type,
                filter_active=filter_active,
                limit=limit,
            )
        elif action == "get":
            validated_id = _validate_sys_id(sys_id, "sys_id")
            return _action_get(client, validated_id)
        elif action == "create":
            return _action_create(
                client,
                name=name,
                range_type=range_type,
                range_start=range_start,
                range_end=range_end,
                active=active,
                include=include,
            )
        elif action == "update":
            validated_id = _validate_sys_id(sys_id, "sys_id")
            return _action_update(
                client,
                sys_id=validated_id,
                name=name,
                range_type=range_type,
                range_start=range_start,
                range_end=range_end,
                active=active,
                include=include,
            )
        elif action == "delete":
            validated_id = _validate_sys_id(sys_id, "sys_id")
            return _action_delete(client, validated_id)
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


def _action_validate(
    *,
    range_type: str | None = None,
    range_start: str | None = None,
    range_end: str | None = None,
) -> dict[str, Any]:
    """Validate IP range parameters without creating a record."""
    issues: list[str] = []
    validated: dict[str, Any] = {}

    if not range_type or not range_type.strip():
        issues.append("range_type is required")
    elif range_type.strip() not in _VALID_RANGE_TYPES:
        issues.append(
            f"Invalid range_type: '{range_type}'. "
            f"Valid types: {sorted(_VALID_RANGE_TYPES)}"
        )
    else:
        validated["range_type"] = range_type.strip()

    if not range_start or not range_start.strip():
        issues.append("range_start is required")
    else:
        rt = validated.get("range_type", "")
        try:
            if rt == "IP Network":
                _validate_cidr(range_start, "range_start")
            elif rt in ("IP Range", "IP Address"):
                _validate_ip_address(range_start, "range_start")
            validated["range_start"] = range_start.strip()
        except ValueError as exc:
            issues.append(str(exc))

    if validated.get("range_type") == "IP Range":
        if not range_end or not range_end.strip():
            issues.append("range_end is required for 'IP Range' type")
        else:
            try:
                _validate_ip_address(range_end, "range_end")
                if "range_start" in validated:
                    _validate_ip_range(validated["range_start"], range_end.strip())
                validated["range_end"] = range_end.strip()
            except ValueError as exc:
                issues.append(str(exc))

    if issues:
        return {
            "success": False,
            "data": {"issues": issues},
            "message": f"Validation failed: {len(issues)} issue(s)",
            "action": "validate",
            "error": "VALIDATION_ERROR",
        }

    return {
        "success": True,
        "data": {"validated": validated},
        "message": "Validation passed",
        "action": "validate",
        "error": None,
    }


def _build_list_query(
    filter_type: str | None = None,
    filter_active: bool | None = None,
) -> str | None:
    """Build a ServiceNow encoded query string from filter parameters."""
    conditions: list[str] = []

    if filter_type is not None and filter_type.strip():
        conditions.append(f"type={filter_type.strip()}")

    if filter_active is not None:
        conditions.append(f"active={'true' if filter_active else 'false'}")

    if not conditions:
        return None

    return "^".join(conditions)


def _action_list(
    client: Any,
    *,
    filter_type: str | None = None,
    filter_active: bool | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List discovery ranges with optional filters."""
    logger.info(
        "Listing discovery ranges (type=%s, active=%s, limit=%d)",
        filter_type, filter_active, limit,
    )

    query = _build_list_query(filter_type=filter_type, filter_active=filter_active)

    records = client.query_table(
        TABLE_NAME,
        query=query,
        fields=RANGE_FIELDS,
        limit=limit,
    )

    ranges = []
    for record in records:
        r = DiscoveryRange.from_snow(record)
        ranges.append(r.model_dump(mode="json"))

    logger.info("Listed %d discovery ranges", len(ranges))

    return {
        "success": True,
        "data": ranges,
        "message": f"Found {len(ranges)} range(s)",
        "action": "list",
        "error": None,
    }


def _action_get(client: Any, sys_id: str) -> dict[str, Any]:
    """Retrieve a single discovery range by sys_id."""
    logger.info("Getting discovery range: %s", sys_id)

    record = client.get_table_record(TABLE_NAME, sys_id, fields=RANGE_FIELDS)
    r = DiscoveryRange.from_snow(record)

    return {
        "success": True,
        "data": r.model_dump(mode="json"),
        "message": f"Retrieved range '{r.name}' ({sys_id})",
        "action": "get",
        "error": None,
    }


def _action_create(
    client: Any,
    *,
    name: str | None = None,
    range_type: str | None = None,
    range_start: str | None = None,
    range_end: str | None = None,
    active: bool | None = None,
    include: bool | None = None,
) -> dict[str, Any]:
    """Create a new discovery range."""
    if not name or not name.strip():
        raise ValueError("'name' is required for create action")
    if not range_type or not range_type.strip():
        raise ValueError("'range_type' is required for create action")
    if range_type.strip() not in _VALID_RANGE_TYPES:
        raise ValueError(
            f"Invalid range_type: '{range_type}'. "
            f"Valid types: {sorted(_VALID_RANGE_TYPES)}"
        )
    if not range_start or not range_start.strip():
        raise ValueError("'range_start' is required for create action")

    rt = range_type.strip()

    # Validate IP addresses based on type
    if rt == "IP Network":
        _validate_cidr(range_start, "range_start")
    else:
        _validate_ip_address(range_start, "range_start")

    if rt == "IP Range":
        if not range_end or not range_end.strip():
            raise ValueError("'range_end' is required for 'IP Range' type")
        _validate_ip_address(range_end, "range_end")
        _validate_ip_range(range_start.strip(), range_end.strip())

    data: dict[str, Any] = {
        "name": name.strip(),
        "type": rt,
        "range_start": range_start.strip(),
    }

    if range_end is not None and range_end.strip():
        data["range_end"] = range_end.strip()
    if active is not None:
        data["active"] = str(active).lower()
    else:
        data["active"] = "true"
    if include is not None:
        data["include"] = str(include).lower()
    else:
        data["include"] = "true"

    logger.info(
        "Creating discovery range: name=%s, type=%s, start=%s",
        data["name"], data["type"], data["range_start"],
    )

    result = client.post(TABLE_NAME, data)
    r = DiscoveryRange.from_snow(result)

    logger.info(
        "Created discovery range: %s (name=%s)", r.sys_id, r.name,
    )

    return {
        "success": True,
        "data": r.model_dump(mode="json"),
        "message": f"Created range '{r.name}' ({r.sys_id})",
        "action": "create",
        "error": None,
    }


def _action_update(
    client: Any,
    *,
    sys_id: str,
    name: str | None = None,
    range_type: str | None = None,
    range_start: str | None = None,
    range_end: str | None = None,
    active: bool | None = None,
    include: bool | None = None,
) -> dict[str, Any]:
    """Update an existing discovery range."""
    data: dict[str, Any] = {}

    if name is not None:
        data["name"] = name.strip()
    if range_type is not None:
        if range_type.strip() not in _VALID_RANGE_TYPES:
            raise ValueError(
                f"Invalid range_type: '{range_type}'. "
                f"Valid types: {sorted(_VALID_RANGE_TYPES)}"
            )
        data["type"] = range_type.strip()
    if range_start is not None:
        # Validate based on type if available
        rt = data.get("type", "")
        if rt == "IP Network":
            _validate_cidr(range_start, "range_start")
        elif rt:
            _validate_ip_address(range_start, "range_start")
        data["range_start"] = range_start.strip()
    if range_end is not None:
        if range_end.strip():
            _validate_ip_address(range_end, "range_end")
        data["range_end"] = range_end.strip()
    if active is not None:
        data["active"] = str(active).lower()
    if include is not None:
        data["include"] = str(include).lower()

    if not data:
        raise ValueError("At least one field must be provided for update")

    logger.info("Updating discovery range %s: fields=%s", sys_id, list(data.keys()))

    result = client.patch(TABLE_NAME, sys_id, data)
    r = DiscoveryRange.from_snow(result)

    logger.info("Updated discovery range: %s (name=%s)", r.sys_id, r.name)

    return {
        "success": True,
        "data": r.model_dump(mode="json"),
        "message": f"Updated range '{r.name}' ({sys_id})",
        "action": "update",
        "error": None,
    }


def _action_delete(client: Any, sys_id: str) -> dict[str, Any]:
    """Delete a discovery range by sys_id."""
    logger.info("Deleting discovery range: %s", sys_id)

    client.delete(TABLE_NAME, sys_id)

    logger.info("Deleted discovery range: %s", sys_id)

    return {
        "success": True,
        "data": {"sys_id": sys_id},
        "message": f"Deleted range ({sys_id})",
        "action": "delete",
        "error": None,
    }
