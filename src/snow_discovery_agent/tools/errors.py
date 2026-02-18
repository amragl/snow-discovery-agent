"""Tool-specific error types for the Snow Discovery Agent tools package.

Provides a lightweight exception hierarchy for tool-level errors that are
distinct from the ServiceNow transport errors in ``exceptions.py``.  These
errors represent parameter validation failures, missing records, and
permission issues at the tool layer.
"""

from __future__ import annotations

from typing import Any


class ToolError(Exception):
    """Base exception for tool-level errors.

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code string.
        details: Additional context about the error (optional).
    """

    def __init__(
        self,
        message: str = "Tool error",
        error_code: str = "TOOL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert the exception to a structured error dict.

        Returns:
            A dict with error, error_code, and details keys.
        """
        result: dict[str, Any] = {
            "error": self.message,
            "error_code": self.error_code,
        }
        if self.details:
            result["details"] = self.details
        return result


class InvalidParameterError(ToolError):
    """Raised when a tool parameter fails validation.

    Covers missing required parameters, invalid formats (e.g., malformed
    sys_id), out-of-range values, and type mismatches.
    """

    def __init__(
        self,
        message: str = "Invalid parameter",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="INVALID_PARAMETER",
            details=details,
        )


class RecordNotFoundError(ToolError):
    """Raised when a requested record does not exist.

    Used at the tool layer when a query returns no results or a specific
    sys_id lookup finds no matching record.
    """

    def __init__(
        self,
        message: str = "Record not found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="RECORD_NOT_FOUND",
            details=details,
        )


class ToolPermissionError(ToolError):
    """Raised when the operation requires permissions the user lacks.

    Distinct from ``ServiceNowPermissionError`` (which is an HTTP 403);
    this represents tool-level permission checks such as attempting to
    modify credentials without the confirmation flag.
    """

    def __init__(
        self,
        message: str = "Permission denied",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="TOOL_PERMISSION_DENIED",
            details=details,
        )
