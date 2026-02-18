"""Shared utility functions for the Snow Discovery Agent tools package.

Provides common helpers used across all tool modules for formatting,
query building, pagination, validation, and text processing.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..models import SNOW_DATETIME_FORMAT

# Valid sys_id pattern: 32 hex characters
_SYS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def format_snow_datetime(value: str | None) -> str | None:
    """Convert a ServiceNow datetime string to ISO 8601 format.

    ServiceNow returns datetimes as ``"YYYY-MM-DD HH:MM:SS"`` in UTC.
    This function converts them to ``"YYYY-MM-DDTHH:MM:SSZ"`` (ISO 8601).

    Args:
        value: A datetime string from ServiceNow, or None.

    Returns:
        An ISO 8601 formatted datetime string, or None if the input is
        empty or unparseable.
    """
    if not value or not value.strip():
        return None

    value = value.strip()

    try:
        dt = datetime.strptime(value, SNOW_DATETIME_FORMAT)
        return dt.isoformat() + "Z"
    except ValueError:
        pass

    # Try ISO 8601 format (already correct, just normalize)
    try:
        dt = datetime.fromisoformat(value)
        return dt.isoformat() + "Z"
    except ValueError:
        return None


def build_query(filters: dict[str, Any]) -> str | None:
    """Build a ServiceNow encoded query string from a filter dictionary.

    Each key-value pair becomes a query condition joined by ``^`` (AND).
    None values are skipped.  Boolean values are converted to ``"true"``
    or ``"false"``.  String values are used directly.

    Args:
        filters: A dict of field_name -> value pairs. None values
            are ignored.

    Returns:
        An encoded query string, or None if no filters are active.

    Example::

        build_query({"active": True, "state": "Completed", "name": None})
        # Returns: "active=true^state=Completed"
    """
    conditions: list[str] = []

    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, bool):
            conditions.append(f"{key}={'true' if value else 'false'}")
        else:
            conditions.append(f"{key}={value}")

    if not conditions:
        return None

    return "^".join(conditions)


def paginate(
    client: Any,
    table: str,
    *,
    query: str | None = None,
    fields: list[str] | None = None,
    limit: int = 100,
    max_pages: int = 10,
    order_by: str | None = None,
) -> list[dict[str, Any]]:
    """Paginate through ServiceNow table results.

    Fetches records page by page using ``sysparm_offset`` until no more
    records are returned or ``max_pages`` is reached.

    Args:
        client: The ServiceNowClient instance.
        table: ServiceNow table name.
        query: Optional encoded query string.
        fields: Optional list of fields to return.
        limit: Records per page (default 100).
        max_pages: Maximum number of pages to fetch (default 10).
        order_by: Optional ordering field.

    Returns:
        A list of all fetched record dicts.
    """
    all_records: list[dict[str, Any]] = []

    for page in range(max_pages):
        offset = page * limit
        records = client.query_table(
            table,
            query=query,
            fields=fields,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )

        if not records:
            break

        all_records.extend(records)

        # If we got fewer records than the limit, we have all of them
        if len(records) < limit:
            break

    return all_records


def validate_sys_id(sys_id: str | None, label: str = "sys_id") -> str:
    """Validate that a sys_id is a well-formed 32-character hex string.

    Args:
        sys_id: The sys_id value to validate.
        label: Label for error messages.

    Returns:
        The validated sys_id string.

    Raises:
        ValueError: If the sys_id is missing or malformed.
    """
    if sys_id is None or sys_id.strip() == "":
        raise ValueError(f"{label} is required")
    sys_id = sys_id.strip()
    if not _SYS_ID_PATTERN.match(sys_id):
        raise ValueError(
            f"Invalid {label} format: '{sys_id}'. "
            "Expected a 32-character hexadecimal string."
        )
    return sys_id


def truncate_description(text: str | None, max_length: int = 200) -> str:
    """Safely truncate a long text field for display.

    If the text exceeds ``max_length``, it is truncated and ``"..."``
    is appended.

    Args:
        text: The text to truncate, or None.
        max_length: Maximum character length (default 200).

    Returns:
        The truncated text string, or empty string if input is None.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def make_response(
    *,
    success: bool,
    data: Any = None,
    message: str = "",
    action: str = "",
    error: str | None = None,
) -> dict[str, Any]:
    """Create a standardized tool response dict.

    All tools return responses in this format for consistency.

    Args:
        success: Whether the operation succeeded.
        data: The result data.
        message: Human-readable result description.
        action: The action that was performed.
        error: Error message if the operation failed.

    Returns:
        A dict with success, data, message, action, and error keys.
    """
    return {
        "success": success,
        "data": data,
        "message": message,
        "action": action,
        "error": error,
    }
