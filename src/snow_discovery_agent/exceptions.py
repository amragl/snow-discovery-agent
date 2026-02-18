"""Custom exception hierarchy for Snow Discovery Agent.

Provides structured error handling that maps to ServiceNow HTTP status codes
and common failure modes. Exceptions are raised by ServiceNowClient and caught
at the tools layer boundary to return structured error dicts to MCP callers.

Exception Hierarchy:
    ServiceNowError (base)
    +-- ServiceNowAuthError (401)
    +-- ServiceNowPermissionError (403)
    +-- ServiceNowNotFoundError (404)
    +-- ServiceNowRateLimitError (429)
    +-- ServiceNowAPIError (5xx and other HTTP errors)
    +-- ServiceNowConnectionError (timeouts, network issues)
"""

from __future__ import annotations

from typing import Any


class ServiceNowError(Exception):
    """Base exception for all ServiceNow client errors.

    All custom exceptions in this module inherit from this class, allowing
    callers to catch any ServiceNow-related error with a single except clause.

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code string.
        status_code: HTTP status code from ServiceNow, if applicable.
        details: Additional context about the error (optional).
    """

    def __init__(
        self,
        message: str = "ServiceNow error",
        error_code: str = "SERVICENOW_ERROR",
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert the exception to a structured error dict.

        Returns a dict compatible with the MCP tool response format,
        including the error message, error_code, and optionally
        status_code and details.
        """
        result: dict[str, Any] = {
            "error": self.message,
            "error_code": self.error_code,
        }
        if self.status_code is not None:
            result["status_code"] = self.status_code
        if self.details:
            result["details"] = self.details
        return result


class ServiceNowAuthError(ServiceNowError):
    """Raised when ServiceNow returns 401 Unauthorized.

    Indicates invalid credentials or an expired session token. The client
    was unable to authenticate with the provided username/password.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        status_code: int = 401,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status_code,
            details=details,
        )


class ServiceNowPermissionError(ServiceNowError):
    """Raised when ServiceNow returns 403 Forbidden.

    Indicates the authenticated user lacks the required roles or permissions
    for the requested operation (e.g., missing discovery_admin role).
    """

    def __init__(
        self,
        message: str = "Permission denied",
        status_code: int = 403,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="PERMISSION_ERROR",
            status_code=status_code,
            details=details,
        )


class ServiceNowNotFoundError(ServiceNowError):
    """Raised when ServiceNow returns 404 Not Found.

    Indicates the requested resource (record, table, or API endpoint)
    does not exist in the ServiceNow instance.
    """

    def __init__(
        self,
        message: str = "Resource not found",
        status_code: int = 404,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=status_code,
            details=details,
        )


class ServiceNowRateLimitError(ServiceNowError):
    """Raised when ServiceNow returns 429 Too Many Requests.

    Indicates the API rate limit has been exceeded. The ``details`` dict
    may include a ``retry_after`` key with the server-suggested wait time.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        status_code: int = 429,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            status_code=status_code,
            details=details,
        )


class ServiceNowAPIError(ServiceNowError):
    """Raised for ServiceNow server errors (5xx) and other unexpected HTTP errors.

    Covers 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable,
    and any other non-client HTTP error response not handled by a more specific
    exception class.
    """

    def __init__(
        self,
        message: str = "ServiceNow API error",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SERVICENOW_API_ERROR",
            status_code=status_code,
            details=details,
        )


class ServiceNowConnectionError(ServiceNowError):
    """Raised for network-level failures: timeouts, DNS resolution, refused connections.

    Maps to ``requests.exceptions.ConnectionError``,
    ``requests.exceptions.Timeout``, and similar transport-layer errors
    where no HTTP response was received.
    """

    def __init__(
        self,
        message: str = "Connection failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONNECTION_ERROR",
            status_code=None,
            details=details,
        )
