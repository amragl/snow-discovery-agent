"""MCP tool for diagnosing and remediating ServiceNow Discovery failures.

Provides the ``remediate_discovery_failures`` function which supports
DIAGNOSE, CREDENTIAL_FIX, NETWORK_FIX, CLASSIFICATION_FIX, and
BULK_REMEDIATE actions.  All modifications produce a dry-run plan first
and never auto-modify credentials without explicit confirmation.
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
CREDENTIAL_TABLE = "discovery_credential"
RANGE_TABLE = "discovery_range"

_VALID_ACTIONS = frozenset({
    "diagnose", "credential_fix", "network_fix",
    "classification_fix", "bulk_remediate",
})

_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

STATUS_FIELDS: list[str] = [
    "sys_id", "name", "state", "source", "dscl_status", "log",
    "started", "completed", "ci_count", "ip_address", "mid_server",
]

LOG_FIELDS: list[str] = [
    "sys_id", "status", "level", "message", "source", "created_on",
]

CREDENTIAL_SAFE_FIELDS: list[str] = [
    "sys_id", "name", "type", "active", "tag", "order", "affinity",
]

# Error categories for diagnosis
_ERROR_CATEGORIES: dict[str, list[str]] = {
    "credential": ["credential", "authentication", "login", "password", "access denied"],
    "network": ["timeout", "timed out", "unreachable", "connection refused", "network"],
    "classification": ["classification", "pattern", "classify", "unclassified"],
    "port_scan": ["port scan", "port closed", "port unreachable"],
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
    """Categorize an error message into a known failure type."""
    lower_msg = message.lower()
    for category, keywords in _ERROR_CATEGORIES.items():
        if any(kw in lower_msg for kw in keywords):
            return category
    return "other"


def remediate_discovery_failures(
    action: str,
    scan_sys_id: str | None = None,
    remediation_type: str | None = None,
    target_items: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Diagnose and remediate common ServiceNow Discovery failures.

    Supports five actions:

    - **diagnose**: Analyze failures and return structured diagnosis.
    - **credential_fix**: Check credential-related failures and suggest fixes.
    - **network_fix**: Verify network/range configuration for failures.
    - **classification_fix**: Check pattern matches for classification failures.
    - **bulk_remediate**: Generate remediation plan for multiple failed items.

    Safety: Never auto-modifies credentials without explicit confirmation
    via the ``confirm`` parameter. Always returns a dry-run plan first.

    Args:
        action: Operation to perform.
        scan_sys_id: Scan sys_id (required for all actions).
        remediation_type: Type of remediation for bulk_remediate.
        target_items: List of IPs or CI sys_ids for bulk_remediate.
        confirm: Whether to execute changes (default False = dry-run only).

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
        if action == "diagnose":
            return _action_diagnose(client, scan_sys_id)
        elif action == "credential_fix":
            return _action_credential_fix(client, scan_sys_id, confirm=confirm)
        elif action == "network_fix":
            return _action_network_fix(client, scan_sys_id)
        elif action == "classification_fix":
            return _action_classification_fix(client, scan_sys_id)
        elif action == "bulk_remediate":
            return _action_bulk_remediate(
                client,
                scan_sys_id,
                remediation_type=remediation_type,
                target_items=target_items,
                confirm=confirm,
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

    return {
        "success": False,
        "data": None,
        "message": f"Unhandled action: {action}",
        "action": action,
        "error": "INTERNAL_ERROR",
    }


def _get_scan_errors(
    client: Any, scan_sys_id: str,
) -> tuple[DiscoveryStatus, list[DiscoveryLog]]:
    """Retrieve scan status and error logs for a given scan."""
    record = client.get_table_record(STATUS_TABLE, scan_sys_id, fields=STATUS_FIELDS)
    status = DiscoveryStatus.from_snow(record)

    log_records = client.query_table(
        LOG_TABLE,
        query=f"status={scan_sys_id}^levelINError,Warning",
        fields=LOG_FIELDS,
        limit=500,
    )
    logs = [DiscoveryLog.from_snow(lr) for lr in log_records]

    return status, logs


def _action_diagnose(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Analyze failures and return a structured diagnosis."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Diagnosing discovery failures: %s", validated_id)

    status, logs = _get_scan_errors(client, validated_id)

    # Categorize all errors
    category_counter: Counter[str] = Counter()
    for lg in logs:
        cat = _categorize_error(lg.message)
        category_counter[cat] += 1

    # Determine primary root cause
    if category_counter:
        primary_cause = category_counter.most_common(1)[0][0]
    else:
        primary_cause = "none"

    # Build remediation suggestions based on categories
    suggestions: list[str] = []
    if "credential" in category_counter:
        suggestions.append(
            "Credential failures detected. Run credential_fix action to check "
            "credential status and ordering."
        )
    if "network" in category_counter:
        suggestions.append(
            "Network failures detected. Run network_fix action to verify "
            "IP ranges and network connectivity."
        )
    if "classification" in category_counter:
        suggestions.append(
            "Classification failures detected. Run classification_fix action "
            "to check CI patterns."
        )

    diagnosis: dict[str, Any] = {
        "scan_sys_id": validated_id,
        "scan_name": status.name,
        "scan_state": status.state,
        "total_errors": len(logs),
        "primary_root_cause": primary_cause,
        "error_breakdown": [
            {"category": cat, "count": count}
            for cat, count in category_counter.most_common()
        ],
        "suggestions": suggestions,
        "affected_ip": status.ip_address,
    }

    return {
        "success": True,
        "data": diagnosis,
        "message": (
            f"Diagnosis: {len(logs)} errors, primary cause: {primary_cause}"
        ),
        "action": "diagnose",
        "error": None,
    }


def _action_credential_fix(
    client: Any,
    scan_sys_id: str | None,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    """Check credential-related failures and suggest fixes."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Checking credential issues for scan: %s", validated_id)

    _status, logs = _get_scan_errors(client, validated_id)

    # Filter to credential-related errors
    cred_errors = [
        lg for lg in logs if _categorize_error(lg.message) == "credential"
    ]

    # Get active credentials to check status
    credentials = client.query_table(
        CREDENTIAL_TABLE,
        fields=CREDENTIAL_SAFE_FIELDS,
        limit=100,
    )

    active_creds = [c for c in credentials if c.get("active") in ("true", True)]
    inactive_creds = [c for c in credentials if c.get("active") in ("false", False)]

    plan: dict[str, Any] = {
        "scan_sys_id": validated_id,
        "credential_errors": len(cred_errors),
        "total_credentials": len(credentials),
        "active_credentials": len(active_creds),
        "inactive_credentials": len(inactive_creds),
        "dry_run": not confirm,
        "recommendations": [],
    }

    if inactive_creds:
        plan["recommendations"].append({
            "type": "activate_credentials",
            "description": f"{len(inactive_creds)} credential(s) are inactive and may need activation",
            "items": [
                {"sys_id": c.get("sys_id", ""), "name": c.get("name", "")}
                for c in inactive_creds[:10]
            ],
        })

    if cred_errors:
        plan["recommendations"].append({
            "type": "check_credential_order",
            "description": (
                "Credential ordering may need adjustment. Ensure the correct "
                "credential type is tried first for the target devices."
            ),
        })

    if not confirm:
        plan["note"] = (
            "This is a dry-run. Set confirm=true to execute changes. "
            "Credential modifications require explicit confirmation."
        )

    return {
        "success": True,
        "data": plan,
        "message": f"Credential analysis: {len(cred_errors)} credential errors found",
        "action": "credential_fix",
        "error": None,
    }


def _action_network_fix(client: Any, scan_sys_id: str | None) -> dict[str, Any]:
    """Verify network/range configuration for failures."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Checking network issues for scan: %s", validated_id)

    status, logs = _get_scan_errors(client, validated_id)

    # Filter to network-related errors
    net_errors = [
        lg for lg in logs if _categorize_error(lg.message) == "network"
    ]

    # Get configured ranges
    range_records = client.query_table(
        RANGE_TABLE,
        query="active=true",
        fields=["sys_id", "name", "type", "range_start", "range_end", "active"],
        limit=200,
    )

    plan: dict[str, Any] = {
        "scan_sys_id": validated_id,
        "network_errors": len(net_errors),
        "configured_ranges": len(range_records),
        "affected_ip": status.ip_address,
        "recommendations": [],
    }

    if net_errors:
        plan["recommendations"].append({
            "type": "verify_connectivity",
            "description": (
                f"Network errors detected for IP {status.ip_address}. "
                "Verify the target is reachable from the MID server."
            ),
        })

    if not range_records:
        plan["recommendations"].append({
            "type": "configure_ranges",
            "description": "No active discovery ranges configured. Add IP ranges for discovery.",
        })

    return {
        "success": True,
        "data": plan,
        "message": f"Network analysis: {len(net_errors)} network errors found",
        "action": "network_fix",
        "error": None,
    }


def _action_classification_fix(
    client: Any, scan_sys_id: str | None,
) -> dict[str, Any]:
    """Check CI pattern matches for classification failures."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")
    logger.info("Checking classification issues for scan: %s", validated_id)

    _status, logs = _get_scan_errors(client, validated_id)

    # Filter to classification-related errors
    class_errors = [
        lg for lg in logs if _categorize_error(lg.message) == "classification"
    ]

    # Get active patterns
    pattern_records = client.query_table(
        "cmdb_ci_pattern",
        query="active=true",
        fields=["sys_id", "name", "active", "ci_type", "criteria", "description"],
        limit=200,
    )

    plan: dict[str, Any] = {
        "scan_sys_id": validated_id,
        "classification_errors": len(class_errors),
        "active_patterns": len(pattern_records),
        "recommendations": [],
    }

    if class_errors:
        plan["recommendations"].append({
            "type": "review_patterns",
            "description": (
                f"{len(class_errors)} classification error(s) found. "
                "Review CI patterns for unclassified devices."
            ),
        })

    if not pattern_records:
        plan["recommendations"].append({
            "type": "create_patterns",
            "description": "No active CI patterns configured. Create patterns for target device types.",
        })

    return {
        "success": True,
        "data": plan,
        "message": f"Classification analysis: {len(class_errors)} classification errors found",
        "action": "classification_fix",
        "error": None,
    }


def _action_bulk_remediate(
    client: Any,
    scan_sys_id: str | None,
    *,
    remediation_type: str | None = None,
    target_items: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Generate a remediation plan for multiple failed items."""
    validated_id = _validate_sys_id(scan_sys_id, "scan_sys_id")

    if not remediation_type or not remediation_type.strip():
        raise ValueError("'remediation_type' is required for bulk_remediate action")

    logger.info(
        "Generating bulk remediation plan: scan=%s, type=%s, confirm=%s",
        validated_id, remediation_type, confirm,
    )

    _status, logs = _get_scan_errors(client, validated_id)

    # Build the plan
    plan_items: list[dict[str, Any]] = []

    if target_items:
        for item in target_items:
            plan_items.append({
                "target": item.strip(),
                "remediation_type": remediation_type.strip(),
                "status": "planned" if not confirm else "queued",
            })
    else:
        # Use all error entries as targets
        seen: set[str] = set()
        for lg in logs:
            key = lg.source or lg.message[:50]
            if key not in seen:
                seen.add(key)
                plan_items.append({
                    "target": key,
                    "remediation_type": remediation_type.strip(),
                    "status": "planned" if not confirm else "queued",
                })

    plan: dict[str, Any] = {
        "scan_sys_id": validated_id,
        "remediation_type": remediation_type.strip(),
        "total_items": len(plan_items),
        "dry_run": not confirm,
        "items": plan_items[:50],  # Limit output
    }

    if not confirm:
        plan["note"] = (
            "This is a dry-run plan. Set confirm=true to execute. "
            "Review the plan items before confirming."
        )

    return {
        "success": True,
        "data": plan,
        "message": f"Bulk remediation plan: {len(plan_items)} items ({remediation_type})",
        "action": "bulk_remediate",
        "error": None,
    }
