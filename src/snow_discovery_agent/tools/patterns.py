"""MCP tool for managing ServiceNow Discovery CI classification patterns.

Provides the ``get_discovery_patterns`` function which supports LIST,
GET, ANALYZE, and COVERAGE operations against the ``cmdb_ci_pattern``
table.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoveryPattern

logger = logging.getLogger(__name__)

TABLE_NAME = "cmdb_ci_pattern"

_VALID_ACTIONS = frozenset({"list", "get", "analyze", "coverage"})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

PATTERN_FIELDS: list[str] = [
    "sys_id", "name", "active", "ci_type", "criteria", "description",
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


def get_discovery_patterns(
    action: str,
    pattern_sys_id: str | None = None,
    ci_type: str | None = None,
    active: bool | None = None,
    name_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List and manage ServiceNow CI classification patterns.

    Supports four actions:

    - **list**: Query patterns with optional filters.
    - **get**: Retrieve a single pattern by sys_id.
    - **analyze**: Show patterns for a given CI type, identify conflicts.
    - **coverage**: Show CI types with and without pattern coverage.

    Args:
        action: Operation to perform -- 'list', 'get', 'analyze', or 'coverage'.
        pattern_sys_id: Pattern sys_id (required for get).
        ci_type: CI type to analyze (required for analyze, optional filter for list).
        active: Filter by active status (for list).
        name_filter: Filter by name pattern using LIKE (for list).
        limit: Maximum records to return (default 100).

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
                ci_type=ci_type,
                active=active,
                name_filter=name_filter,
                limit=limit,
            )
        elif action == "get":
            return _action_get(client, pattern_sys_id)
        elif action == "analyze":
            return _action_analyze(client, ci_type)
        elif action == "coverage":
            return _action_coverage(client)
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
    ci_type: str | None = None,
    active: bool | None = None,
    name_filter: str | None = None,
) -> str | None:
    """Build a ServiceNow encoded query string from filter parameters."""
    conditions: list[str] = []

    if ci_type is not None and ci_type.strip():
        conditions.append(f"ci_type={ci_type.strip()}")

    if active is not None:
        conditions.append(f"active={'true' if active else 'false'}")

    if name_filter is not None and name_filter.strip():
        conditions.append(f"nameLIKE{name_filter.strip()}")

    if not conditions:
        return None

    return "^".join(conditions)


def _action_list(
    client: Any,
    *,
    ci_type: str | None = None,
    active: bool | None = None,
    name_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List CI classification patterns with optional filters."""
    logger.info(
        "Listing discovery patterns (ci_type=%s, active=%s, name=%s, limit=%d)",
        ci_type, active, name_filter, limit,
    )

    query = _build_list_query(ci_type=ci_type, active=active, name_filter=name_filter)

    records = client.query_table(
        TABLE_NAME,
        query=query,
        fields=PATTERN_FIELDS,
        limit=limit,
    )

    patterns = []
    for record in records:
        p = DiscoveryPattern.from_snow(record)
        patterns.append(p.model_dump(mode="json"))

    logger.info("Listed %d discovery patterns", len(patterns))

    return {
        "success": True,
        "data": patterns,
        "message": f"Found {len(patterns)} pattern(s)",
        "action": "list",
        "error": None,
    }


def _action_get(client: Any, pattern_sys_id: str | None) -> dict[str, Any]:
    """Retrieve a single CI classification pattern by sys_id."""
    validated_id = _validate_sys_id(pattern_sys_id, "pattern_sys_id")
    logger.info("Getting discovery pattern: %s", validated_id)

    record = client.get_table_record(TABLE_NAME, validated_id, fields=PATTERN_FIELDS)
    p = DiscoveryPattern.from_snow(record)

    return {
        "success": True,
        "data": p.model_dump(mode="json"),
        "message": f"Retrieved pattern '{p.name}' ({validated_id})",
        "action": "get",
        "error": None,
    }


def _action_analyze(client: Any, ci_type: str | None) -> dict[str, Any]:
    """Analyze patterns for a given CI type; identify conflicts."""
    if not ci_type or not ci_type.strip():
        raise ValueError("'ci_type' is required for analyze action")

    ci_type = ci_type.strip()
    logger.info("Analyzing patterns for CI type: %s", ci_type)

    records = client.query_table(
        TABLE_NAME,
        query=f"ci_type={ci_type}",
        fields=PATTERN_FIELDS,
        limit=100,
    )

    patterns = [DiscoveryPattern.from_snow(r) for r in records]

    # Check for potential conflicts (multiple active patterns for same type)
    active_patterns = [p for p in patterns if p.active]
    conflicts: list[dict[str, str]] = []

    if len(active_patterns) > 1:
        for i, p1 in enumerate(active_patterns):
            for p2 in active_patterns[i + 1:]:
                conflicts.append({
                    "pattern_a": p1.name,
                    "pattern_b": p2.name,
                    "reason": f"Both active patterns target CI type '{ci_type}'",
                })

    analysis: dict[str, Any] = {
        "ci_type": ci_type,
        "total_patterns": len(patterns),
        "active_patterns": len(active_patterns),
        "inactive_patterns": len(patterns) - len(active_patterns),
        "conflicts": conflicts,
        "patterns": [p.model_dump(mode="json") for p in patterns],
    }

    return {
        "success": True,
        "data": analysis,
        "message": (
            f"Analysis for '{ci_type}': {len(patterns)} pattern(s), "
            f"{len(conflicts)} conflict(s)"
        ),
        "action": "analyze",
        "error": None,
    }


def _action_coverage(client: Any) -> dict[str, Any]:
    """Show CI types with and without pattern coverage."""
    logger.info("Computing pattern coverage report")

    records = client.query_table(
        TABLE_NAME,
        fields=PATTERN_FIELDS,
        limit=500,
    )

    patterns = [DiscoveryPattern.from_snow(r) for r in records]

    # Group patterns by CI type
    type_coverage: dict[str, dict[str, Any]] = {}
    for p in patterns:
        ct = p.ci_type or "Unknown"
        if ct not in type_coverage:
            type_coverage[ct] = {"total": 0, "active": 0, "inactive": 0}
        type_coverage[ct]["total"] += 1
        if p.active:
            type_coverage[ct]["active"] += 1
        else:
            type_coverage[ct]["inactive"] += 1

    # Build coverage report
    covered_types = [
        ct for ct, info in type_coverage.items() if info["active"] > 0
    ]
    uncovered_types = [
        ct for ct, info in type_coverage.items() if info["active"] == 0
    ]

    coverage: dict[str, Any] = {
        "total_patterns": len(patterns),
        "total_ci_types": len(type_coverage),
        "covered_types": len(covered_types),
        "uncovered_types": len(uncovered_types),
        "by_type": type_coverage,
        "types_without_active_patterns": uncovered_types,
    }

    return {
        "success": True,
        "data": coverage,
        "message": (
            f"Coverage: {len(covered_types)}/{len(type_coverage)} CI types "
            f"have active patterns"
        ),
        "action": "coverage",
        "error": None,
    }
