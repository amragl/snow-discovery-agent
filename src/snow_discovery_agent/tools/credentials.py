"""MCP tool for managing ServiceNow Discovery credentials.

Provides the ``manage_discovery_credentials`` function which supports
LIST, GET, CREATE, UPDATE, and DELETE operations against the
``discovery_credential`` table.

Security
--------
Credential secrets (passwords, private keys, community strings, etc.) are
**never** returned in responses. Only metadata fields are exposed:
``sys_id``, ``name``, ``type``, ``active``, ``tag``, ``order``, ``affinity``.

All operations are logged at INFO level for audit trail purposes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..exceptions import ServiceNowError, ServiceNowNotFoundError
from ..models import DiscoveryCredential

logger = logging.getLogger(__name__)

# ServiceNow table for discovery credentials
TABLE_NAME = "discovery_credential"

# Fields that are safe to return -- deliberately excludes secret fields
# such as password, ssh_private_key, community_string, etc.
SAFE_FIELDS: list[str] = [
    "sys_id",
    "name",
    "type",
    "active",
    "tag",
    "order",
    "affinity",
]

# Fields that may contain secrets and must never be returned or logged.
# This list is intentionally broad to catch any secret-like field names
# that ServiceNow might include in its response.
SECRET_FIELD_PATTERNS: list[str] = [
    "password",
    "secret",
    "private_key",
    "ssh_private",
    "community",
    "passphrase",
    "token",
    "credential",
    "auth_key",
    "key_file",
    "pem",
    "cert_body",
]

# Valid sys_id pattern: 32 hex characters
_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

# Valid actions
_VALID_ACTIONS = frozenset({"list", "get", "create", "update", "delete"})


def _is_secret_field(field_name: str) -> bool:
    """Check whether a field name matches a known secret pattern.

    Args:
        field_name: The ServiceNow field name to check.

    Returns:
        True if the field name matches a secret pattern.
    """
    lower = field_name.lower()
    return any(pattern in lower for pattern in SECRET_FIELD_PATTERNS)


def _strip_secrets(record: dict[str, Any]) -> dict[str, Any]:
    """Remove any secret fields from a ServiceNow record dict.

    Returns a new dict containing only safe, non-secret fields. Fields
    not in ``SAFE_FIELDS`` are included only if they do not match a
    secret pattern -- this ensures that any additional metadata fields
    ServiceNow might return are still available while secrets are always
    stripped.

    Args:
        record: A raw record dict from the ServiceNow API.

    Returns:
        A sanitized copy of the record with secrets removed.
    """
    safe: dict[str, Any] = {}
    for key, value in record.items():
        if key in SAFE_FIELDS or not _is_secret_field(key):
            safe[key] = value
    return safe


def _validate_sys_id(sys_id: str | None, action: str) -> str | None:
    """Validate that a sys_id is a well-formed 32-character hex string.

    Args:
        sys_id: The sys_id value to validate.
        action: The action name (for error message context).

    Returns:
        The validated sys_id, or None if no error and sys_id is optional.

    Raises:
        ValueError: If the sys_id is missing when required or malformed.
    """
    if sys_id is None or sys_id.strip() == "":
        raise ValueError(
            f"sys_id is required for '{action}' action"
        )
    sys_id = sys_id.strip()
    if not _SYS_ID_PATTERN.match(sys_id):
        raise ValueError(
            f"Invalid sys_id format: '{sys_id}'. "
            "Expected a 32-character hexadecimal string."
        )
    return sys_id


def _build_list_query(
    credential_type: str | None = None,
    active: bool | None = None,
    tag: str | None = None,
) -> str | None:
    """Build a ServiceNow encoded query string from filter parameters.

    Args:
        credential_type: Filter by credential type (e.g., 'SSH', 'SNMP').
        active: Filter by active status.
        tag: Filter by credential tag.

    Returns:
        An encoded query string, or None if no filters are specified.
    """
    conditions: list[str] = []

    if credential_type is not None and credential_type.strip():
        conditions.append(f"type={credential_type.strip()}")

    if active is not None:
        conditions.append(f"active={'true' if active else 'false'}")

    if tag is not None and tag.strip():
        conditions.append(f"tag={tag.strip()}")

    if not conditions:
        return None

    return "^".join(conditions)


def manage_discovery_credentials(
    action: str,
    sys_id: str | None = None,
    name: str | None = None,
    credential_type: str | None = None,
    tag: str | None = None,
    order: int | None = None,
    active: bool | None = None,
    filter_type: str | None = None,
    filter_active: bool | None = None,
    filter_tag: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Manage ServiceNow Discovery credentials (CRUD operations).

    Provides five operations against the ``discovery_credential`` table:

    - **list**: Query credentials with optional filters.
    - **get**: Retrieve a single credential by sys_id.
    - **create**: Create a new credential record.
    - **update**: Partially update an existing credential.
    - **delete**: Delete a credential by sys_id.

    Security: Credential secrets (passwords, private keys) are never
    returned in responses. Only metadata fields are exposed.

    Args:
        action: Operation to perform -- 'list', 'get', 'create', 'update',
            or 'delete'.
        sys_id: The sys_id of the credential (required for get, update,
            delete).
        name: Credential name (required for create, optional for update).
        credential_type: Credential type, e.g. 'SSH', 'SNMP', 'Windows',
            'VMware' (required for create, optional for update).
        tag: Credential tag for grouping (optional).
        order: Evaluation order -- lower numbers are tried first (optional).
        active: Whether the credential is active (optional, defaults to
            True for create).
        filter_type: Filter list results by credential type.
        filter_active: Filter list results by active status.
        filter_tag: Filter list results by tag.
        limit: Maximum number of records to return for list (default 100).

    Returns:
        A dict with keys:
        - ``success`` (bool): Whether the operation succeeded.
        - ``data``: The result data (dict, list of dicts, or None).
        - ``message`` (str): Human-readable result description.
        - ``action`` (str): The action that was performed.
        - ``error`` (str | None): Error message if the operation failed.
    """
    # Import here to avoid circular imports at module load time
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
                filter_type=filter_type,
                filter_active=filter_active,
                filter_tag=filter_tag,
                limit=limit,
            )
        elif action == "get":
            validated_id = _validate_sys_id(sys_id, action)
            assert validated_id is not None  # _validate_sys_id raises on None
            return _action_get(client, validated_id)
        elif action == "create":
            return _action_create(
                client,
                name=name,
                credential_type=credential_type,
                tag=tag,
                order=order,
                active=active,
            )
        elif action == "update":
            validated_id = _validate_sys_id(sys_id, action)
            assert validated_id is not None
            return _action_update(
                client,
                sys_id=validated_id,
                name=name,
                credential_type=credential_type,
                tag=tag,
                order=order,
                active=active,
            )
        elif action == "delete":
            validated_id = _validate_sys_id(sys_id, action)
            assert validated_id is not None
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

    # Should not be reached, but satisfy type checker
    return {
        "success": False,
        "data": None,
        "message": f"Unhandled action: {action}",
        "action": action,
        "error": "INTERNAL_ERROR",
    }


def _action_list(
    client: Any,
    *,
    filter_type: str | None = None,
    filter_active: bool | None = None,
    filter_tag: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List discovery credentials with optional filters.

    Queries the ``discovery_credential`` table and returns sanitized
    credential metadata. Secrets are stripped from all records.

    Args:
        client: The ServiceNowClient instance.
        filter_type: Optional type filter (e.g., 'SSH').
        filter_active: Optional active status filter.
        filter_tag: Optional tag filter.
        limit: Maximum records to return.

    Returns:
        Structured response dict with list of credential records.
    """
    logger.info(
        "Listing discovery credentials (type=%s, active=%s, tag=%s, limit=%d)",
        filter_type,
        filter_active,
        filter_tag,
        limit,
    )

    query = _build_list_query(
        credential_type=filter_type,
        active=filter_active,
        tag=filter_tag,
    )

    records = client.query_table(
        TABLE_NAME,
        query=query,
        fields=SAFE_FIELDS,
        limit=limit,
    )

    # Strip secrets from every record (defense in depth -- even though
    # we request only SAFE_FIELDS, ServiceNow may return extra fields)
    sanitized = [_strip_secrets(r) for r in records]

    # Convert to DiscoveryCredential models for validation, then back to dicts
    credentials = []
    for record in sanitized:
        cred = DiscoveryCredential.from_snow(record)
        credentials.append(cred.model_dump())

    logger.info("Listed %d discovery credentials", len(credentials))

    return {
        "success": True,
        "data": credentials,
        "message": f"Found {len(credentials)} credential(s)",
        "action": "list",
        "error": None,
    }


def _action_get(client: Any, sys_id: str) -> dict[str, Any]:
    """Retrieve a single discovery credential by sys_id.

    Args:
        client: The ServiceNowClient instance.
        sys_id: The sys_id of the credential to retrieve.

    Returns:
        Structured response dict with the credential record.
    """
    logger.info("Getting discovery credential: %s", sys_id)

    record = client.get_table_record(
        TABLE_NAME,
        sys_id,
        fields=SAFE_FIELDS,
    )

    sanitized = _strip_secrets(record)
    credential = DiscoveryCredential.from_snow(sanitized)

    logger.info("Retrieved discovery credential: %s (name=%s)", sys_id, credential.name)

    return {
        "success": True,
        "data": credential.model_dump(),
        "message": f"Retrieved credential '{credential.name}' ({sys_id})",
        "action": "get",
        "error": None,
    }


def _action_create(
    client: Any,
    *,
    name: str | None = None,
    credential_type: str | None = None,
    tag: str | None = None,
    order: int | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    """Create a new discovery credential.

    Args:
        client: The ServiceNowClient instance.
        name: Credential name (required).
        credential_type: Credential type (required).
        tag: Optional credential tag.
        order: Optional evaluation order.
        active: Optional active status (defaults to True).

    Returns:
        Structured response dict with the created credential record.
    """
    if not name or not name.strip():
        raise ValueError("'name' is required for create action")
    if not credential_type or not credential_type.strip():
        raise ValueError("'credential_type' is required for create action")

    data: dict[str, Any] = {
        "name": name.strip(),
        "type": credential_type.strip(),
    }

    if tag is not None:
        data["tag"] = tag.strip()
    if order is not None:
        data["order"] = str(order)
    if active is not None:
        data["active"] = str(active).lower()
    else:
        data["active"] = "true"

    logger.info(
        "Creating discovery credential: name=%s, type=%s",
        data["name"],
        data["type"],
    )

    result = client.post(TABLE_NAME, data)

    sanitized = _strip_secrets(result)
    credential = DiscoveryCredential.from_snow(sanitized)

    logger.info(
        "Created discovery credential: %s (name=%s, type=%s)",
        credential.sys_id,
        credential.name,
        credential.type,
    )

    return {
        "success": True,
        "data": credential.model_dump(),
        "message": f"Created credential '{credential.name}' ({credential.sys_id})",
        "action": "create",
        "error": None,
    }


def _action_update(
    client: Any,
    *,
    sys_id: str,
    name: str | None = None,
    credential_type: str | None = None,
    tag: str | None = None,
    order: int | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    """Update an existing discovery credential.

    Supports partial updates -- only fields with non-None values are
    sent to ServiceNow.

    Args:
        client: The ServiceNowClient instance.
        sys_id: The sys_id of the credential to update.
        name: Updated credential name.
        credential_type: Updated credential type.
        tag: Updated tag.
        order: Updated evaluation order.
        active: Updated active status.

    Returns:
        Structured response dict with the updated credential record.
    """
    data: dict[str, Any] = {}

    if name is not None:
        data["name"] = name.strip()
    if credential_type is not None:
        data["type"] = credential_type.strip()
    if tag is not None:
        data["tag"] = tag.strip()
    if order is not None:
        data["order"] = str(order)
    if active is not None:
        data["active"] = str(active).lower()

    if not data:
        raise ValueError(
            "At least one field must be provided for update "
            "(name, credential_type, tag, order, active)"
        )

    logger.info(
        "Updating discovery credential %s: fields=%s",
        sys_id,
        list(data.keys()),
    )

    result = client.patch(TABLE_NAME, sys_id, data)

    sanitized = _strip_secrets(result)
    credential = DiscoveryCredential.from_snow(sanitized)

    logger.info(
        "Updated discovery credential: %s (name=%s)",
        credential.sys_id,
        credential.name,
    )

    return {
        "success": True,
        "data": credential.model_dump(),
        "message": f"Updated credential '{credential.name}' ({sys_id})",
        "action": "update",
        "error": None,
    }


def _action_delete(client: Any, sys_id: str) -> dict[str, Any]:
    """Delete a discovery credential by sys_id.

    Args:
        client: The ServiceNowClient instance.
        sys_id: The sys_id of the credential to delete.

    Returns:
        Structured response dict confirming deletion.
    """
    logger.info("Deleting discovery credential: %s", sys_id)

    client.delete(TABLE_NAME, sys_id)

    logger.info("Deleted discovery credential: %s", sys_id)

    return {
        "success": True,
        "data": {"sys_id": sys_id},
        "message": f"Deleted credential ({sys_id})",
        "action": "delete",
        "error": None,
    }
