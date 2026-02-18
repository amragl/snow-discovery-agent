"""ServiceNow REST client for the Snow Discovery Agent.

Provides a reusable ``ServiceNowClient`` class that handles all HTTP
communication with a ServiceNow instance, including authentication,
session management, URL construction, query parameters, response parsing,
and comprehensive error handling.

This module is the foundation every MCP tool in the discovery agent uses
to interact with the ServiceNow Table API.

Usage::

    from snow_discovery_agent.client import ServiceNowClient

    client = ServiceNowClient(
        instance="https://dev12345.service-now.com",
        username="admin",
        password="secret",
    )
    records = client.get("sys_properties", params={"sysparm_limit": "1"})
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import (
    ServiceNowAPIError,
    ServiceNowAuthError,
    ServiceNowConnectionError,
    ServiceNowNotFoundError,
    ServiceNowPermissionError,
    ServiceNowRateLimitError,
)

logger = logging.getLogger(__name__)

# ServiceNow Table API base path
TABLE_API_PATH = "/api/now/table"

# Default settings
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5
DEFAULT_POOL_SIZE = 10

# HTTP status codes that warrant automatic retry at the urllib3 level
_RETRY_STATUS_CODES: frozenset[int] = frozenset({502, 503, 504})


def _create_session(
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    pool_connections: int = DEFAULT_POOL_SIZE,
    pool_maxsize: int = DEFAULT_POOL_SIZE,
) -> requests.Session:
    """Create a ``requests.Session`` with connection pooling and retry logic.

    Configures a urllib3 ``Retry`` strategy with exponential backoff and
    mounts it via an ``HTTPAdapter`` for both HTTPS and HTTP.

    The retry strategy handles:
    - Network-level errors (connect, read, status)
    - HTTP 502, 503, 504 responses (transient server errors)

    Note: 429 is intentionally not retried at the urllib3 level because
    the client handles Retry-After headers at the application level.

    Args:
        max_retries: Maximum number of retry attempts per request.
        backoff_factor: Multiplier for exponential backoff between retries.
        pool_connections: Number of connection pools to cache.
        pool_maxsize: Maximum number of connections per pool.

    Returns:
        A configured ``requests.Session`` with retry adapters mounted.
    """
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(_RETRY_STATUS_CODES),
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
    )

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def _raise_for_status(response: requests.Response) -> None:
    """Raise an appropriate ServiceNow exception based on HTTP status code.

    Inspects the response status code and raises the most specific exception
    class. Called after every ServiceNow API request.

    Args:
        response: The HTTP response from ServiceNow.

    Raises:
        ServiceNowAuthError: For 401 responses.
        ServiceNowPermissionError: For 403 responses.
        ServiceNowNotFoundError: For 404 responses.
        ServiceNowRateLimitError: For 429 responses.
        ServiceNowAPIError: For 5xx and other error responses.
    """
    if response.ok:
        return

    status = response.status_code

    # Extract error detail from the response body when possible
    try:
        body = response.json()
        error_field = body.get("error", {})
        if isinstance(error_field, dict):
            detail_msg = error_field.get("message", "")
        else:
            detail_msg = str(error_field)
    except (ValueError, AttributeError):
        detail_msg = response.text[:500] if response.text else ""

    base_msg = f"HTTP {status}"
    if detail_msg:
        base_msg = f"HTTP {status}: {detail_msg}"

    details: dict[str, Any] = {
        "url": response.url,
        "method": response.request.method if response.request else "UNKNOWN",
    }

    if status == 401:
        raise ServiceNowAuthError(
            message=base_msg,
            status_code=status,
            details=details,
        )
    elif status == 403:
        raise ServiceNowPermissionError(
            message=base_msg,
            status_code=status,
            details=details,
        )
    elif status == 404:
        raise ServiceNowNotFoundError(
            message=base_msg,
            status_code=status,
            details=details,
        )
    elif status == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            details["retry_after"] = retry_after
        raise ServiceNowRateLimitError(
            message=base_msg,
            status_code=status,
            details=details,
        )
    elif status >= 500:
        raise ServiceNowAPIError(
            message=base_msg,
            status_code=status,
            details=details,
        )
    else:
        # Other 4xx errors (400, 405, 409, etc.)
        raise ServiceNowAPIError(
            message=base_msg,
            status_code=status,
            details=details,
        )


def _handle_request_exception(exc: requests.exceptions.RequestException) -> None:
    """Convert a ``requests`` library exception into a ServiceNow exception.

    Maps timeout and connection errors to ``ServiceNowConnectionError``.
    This function always raises and never returns.

    Args:
        exc: The requests exception to convert.

    Raises:
        ServiceNowConnectionError: Always raised with details about the
            underlying transport error.
    """
    if isinstance(exc, requests.exceptions.Timeout):
        logger.error("Request timed out: %s", exc)
        raise ServiceNowConnectionError(
            message=f"Request timed out: {exc}",
            details={"original_error": str(exc)},
        ) from exc
    elif isinstance(exc, requests.exceptions.ConnectionError):
        logger.error("Connection failed: %s", exc)
        raise ServiceNowConnectionError(
            message=f"Connection failed: {exc}",
            details={"original_error": str(exc)},
        ) from exc
    else:
        logger.error("Request exception: %s", exc)
        raise ServiceNowConnectionError(
            message=f"Request failed: {exc}",
            details={"original_error": str(exc)},
        ) from exc


class ServiceNowClient:
    """Client for interacting with the ServiceNow REST Table API.

    Handles authentication, session management, URL construction, query
    parameter building, response parsing, and error handling. Uses
    ``requests.Session`` for connection pooling and automatic retry of
    transient server errors.

    All public methods raise ``ServiceNowError`` subclasses on failure.
    Callers (the tools layer) are responsible for catching these exceptions
    and converting them to structured error responses.

    Args:
        instance: ServiceNow instance URL (e.g., ``https://dev12345.service-now.com``).
        username: ServiceNow username for basic auth.
        password: ServiceNow password for basic auth.
        timeout: Request timeout in seconds. Can be an int for a single
            timeout or a tuple ``(connect_timeout, read_timeout)``.
            Defaults to 30 seconds.
        max_retries: Maximum number of retries for transient failures.
            Defaults to 3.
        backoff_factor: Multiplier for exponential backoff between retries.
            Defaults to 0.5.
        pool_size: Connection pool size per host. Defaults to 10.
        session: Pre-configured ``requests.Session`` to use. If provided,
            the ``max_retries``, ``pool_size``, and ``backoff_factor``
            parameters are ignored.

    Example::

        client = ServiceNowClient(
            instance="https://dev12345.service-now.com",
            username="admin",
            password="secret",
        )
        with client:
            records = client.get("discovery_status", params={"sysparm_limit": "5"})
    """

    def __init__(
        self,
        instance: str,
        username: str,
        password: str,
        timeout: int | tuple[int, int] = DEFAULT_TIMEOUT,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        pool_size: int = DEFAULT_POOL_SIZE,
        session: requests.Session | None = None,
    ) -> None:
        # Normalize instance URL: strip trailing slash
        self._instance = instance.rstrip("/")
        self._base_url = f"{self._instance}{TABLE_API_PATH}"
        self._auth = (username, password)
        self._headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Timeout can be a single int or a (connect, read) tuple
        if isinstance(timeout, tuple):
            self._timeout: int | tuple[int, int] = timeout
        else:
            self._timeout = timeout

        # Create or use provided session with connection pooling and retry
        if session is not None:
            self._session = session
        else:
            self._session = _create_session(
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                pool_connections=pool_size,
                pool_maxsize=pool_size,
            )

        logger.info(
            "ServiceNowClient initialized: instance=%s, timeout=%s, pool_size=%d, max_retries=%d",
            self._instance,
            self._timeout,
            pool_size,
            max_retries,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def instance(self) -> str:
        """Return the ServiceNow instance URL."""
        return self._instance

    @property
    def base_url(self) -> str:
        """Return the full Table API base URL."""
        return self._base_url

    @property
    def session(self) -> requests.Session:
        """Return the underlying ``requests.Session`` for inspection."""
        return self._session

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying session and release connection pool resources."""
        self._session.close()
        logger.debug("ServiceNowClient session closed")

    def __enter__(self) -> ServiceNowClient:
        """Support usage as a context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close the session on context manager exit."""
        self.close()

    # ------------------------------------------------------------------
    # URL construction
    # ------------------------------------------------------------------

    def _build_table_url(self, table: str, sys_id: str | None = None) -> str:
        """Build the full URL for a ServiceNow Table API endpoint.

        Args:
            table: The ServiceNow table name (e.g., ``discovery_status``).
            sys_id: Optional sys_id for a specific record.

        Returns:
            The full URL, e.g.
            ``https://instance/api/now/table/discovery_status/abc123``.
        """
        url = f"{self._base_url}/{table}"
        if sys_id:
            url = f"{url}/{sys_id}"
        return url

    def _build_api_url(self, path: str) -> str:
        """Build a full URL for an arbitrary ServiceNow API path.

        Use this for non-table endpoints (e.g., ``/api/now/stats/...``).

        Args:
            path: The API path starting with ``/`` (e.g., ``/api/now/stats/incident``).

        Returns:
            The full URL.
        """
        return f"{self._instance}{path}"

    # ------------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Execute an HTTP request with authentication and error handling.

        Sends the request via the internal ``requests.Session`` with basic
        auth, JSON headers, and the configured timeout. Logs the request
        and response at DEBUG level.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            url: Full request URL.
            params: Optional query string parameters.
            json_body: Optional JSON body for POST/PUT/PATCH requests.

        Returns:
            The raw ``requests.Response`` object.

        Raises:
            ServiceNowConnectionError: On network-level failures.
        """
        logger.debug("API request: %s %s", method.upper(), url)
        if params:
            logger.debug("Request params: %s", params)
        if json_body:
            logger.debug("Request body keys: %s", list(json_body.keys()))

        kwargs: dict[str, Any] = {
            "headers": self._headers,
            "auth": self._auth,
            "timeout": self._timeout,
        }
        if params is not None:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        try:
            response = self._session.request(method.upper(), url, **kwargs)
        except requests.exceptions.RequestException as exc:
            _handle_request_exception(exc)

        elapsed_ms = response.elapsed.total_seconds() * 1000
        logger.debug(
            "API response: %s %s -> %d (%.0fms)",
            method.upper(),
            url.rsplit("/", 1)[-1],
            response.status_code,
            elapsed_ms,
        )

        return response

    def _extract_result(self, response: requests.Response) -> Any:
        """Parse the response JSON and extract the ``result`` key.

        ServiceNow wraps all API responses in a ``{"result": ...}`` envelope.
        This method extracts the inner value.

        Args:
            response: A successful HTTP response from ServiceNow.

        Returns:
            The value of the ``result`` key from the response JSON. This is
            typically a list of dicts for collection endpoints or a single
            dict for record endpoints.

        Raises:
            ServiceNowAPIError: If the response body is not valid JSON.
        """
        try:
            body = response.json()
        except ValueError as exc:
            raise ServiceNowAPIError(
                message=f"Invalid JSON in response: {exc}",
                status_code=response.status_code,
                details={"response_text": response.text[:500]},
            ) from exc

        return body.get("result", body)

    # ------------------------------------------------------------------
    # Public HTTP methods
    # ------------------------------------------------------------------

    def get(
        self,
        table: str,
        sys_id: str | None = None,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a GET request to the ServiceNow Table API.

        For collection queries (no ``sys_id``), returns a list of record dicts.
        For single-record lookups (with ``sys_id``), returns a single dict.

        Common query parameters:
        - ``sysparm_query``: Encoded query string for filtering.
        - ``sysparm_fields``: Comma-separated field names to return.
        - ``sysparm_limit``: Maximum records to return (default varies).
        - ``sysparm_offset``: Number of records to skip (for pagination).

        Args:
            table: ServiceNow table name (e.g., ``discovery_status``).
            sys_id: Optional sys_id to retrieve a single record.
            params: Optional query parameters dict.

        Returns:
            The parsed ``result`` from the response: a list of dicts for
            collection queries or a single dict for record lookups.

        Raises:
            ServiceNowAuthError: If authentication fails (401).
            ServiceNowPermissionError: If access is denied (403).
            ServiceNowNotFoundError: If the resource is not found (404).
            ServiceNowRateLimitError: If rate limited (429).
            ServiceNowAPIError: For server errors (5xx) or other HTTP errors.
            ServiceNowConnectionError: On network failures.
        """
        url = self._build_table_url(table, sys_id)
        response = self._request("GET", url, params=params)
        _raise_for_status(response)
        return self._extract_result(response)

    def post(
        self,
        table: str,
        data: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a POST request to create a new record.

        Args:
            table: ServiceNow table name.
            data: Field values for the new record.
            params: Optional query parameters.

        Returns:
            The created record as a dict.

        Raises:
            ServiceNowError: On any API or network error.
        """
        url = self._build_table_url(table)
        response = self._request("POST", url, json_body=data, params=params)
        _raise_for_status(response)
        return self._extract_result(response)

    def put(
        self,
        table: str,
        sys_id: str,
        data: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a PUT request to replace a record entirely.

        Args:
            table: ServiceNow table name.
            sys_id: The sys_id of the record to replace.
            data: Complete field values for the record.
            params: Optional query parameters.

        Returns:
            The updated record as a dict.

        Raises:
            ServiceNowError: On any API or network error.
        """
        url = self._build_table_url(table, sys_id)
        response = self._request("PUT", url, json_body=data, params=params)
        _raise_for_status(response)
        return self._extract_result(response)

    def patch(
        self,
        table: str,
        sys_id: str,
        data: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a PATCH request to partially update a record.

        Args:
            table: ServiceNow table name.
            sys_id: The sys_id of the record to update.
            data: Field values to update (partial update).
            params: Optional query parameters.

        Returns:
            The updated record as a dict.

        Raises:
            ServiceNowError: On any API or network error.
        """
        url = self._build_table_url(table, sys_id)
        response = self._request("PATCH", url, json_body=data, params=params)
        _raise_for_status(response)
        return self._extract_result(response)

    def delete(
        self,
        table: str,
        sys_id: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """Send a DELETE request to remove a record.

        Args:
            table: ServiceNow table name.
            sys_id: The sys_id of the record to delete.
            params: Optional query parameters.

        Returns:
            ``True`` if the record was deleted successfully.

        Raises:
            ServiceNowError: On any API or network error.
        """
        url = self._build_table_url(table, sys_id)
        response = self._request("DELETE", url, params=params)
        _raise_for_status(response)
        return True

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get_table_record(
        self,
        table: str,
        sys_id: str,
        *,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retrieve a single record from a table by sys_id.

        A convenience wrapper around ``get()`` that builds the fields
        parameter and returns a typed dict.

        Args:
            table: ServiceNow table name.
            sys_id: The sys_id of the record to retrieve.
            fields: Optional list of field names to include in the response.

        Returns:
            The record as a dict.

        Raises:
            ServiceNowNotFoundError: If the record does not exist.
            ServiceNowError: On any other API or network error.
        """
        params: dict[str, Any] = {}
        if fields:
            params["sysparm_fields"] = ",".join(fields)

        result = self.get(table, sys_id=sys_id, params=params or None)
        if isinstance(result, dict):
            return result
        # If the API returns a list (shouldn't for sys_id lookup, but be safe)
        if isinstance(result, list) and len(result) > 0:
            first: dict[str, Any] = result[0]
            return first
        raise ServiceNowNotFoundError(
            message=f"Record not found: {table}/{sys_id}",
            details={"table": table, "sys_id": sys_id},
        )

    def query_table(
        self,
        table: str,
        *,
        query: str | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query a table with filters, field selection, and pagination.

        A convenience wrapper around ``get()`` that constructs query parameters
        from higher-level arguments.

        Args:
            table: ServiceNow table name.
            query: ServiceNow encoded query string (e.g., ``active=true``).
            fields: Optional list of field names to include in the response.
            limit: Maximum number of records to return. Defaults to 100.
            offset: Number of records to skip. Defaults to 0.
            order_by: Optional field to order results by. Prefix with ``-``
                for descending order (e.g., ``-sys_created_on``).

        Returns:
            A list of record dicts.

        Raises:
            ServiceNowError: On any API or network error.
        """
        params: dict[str, Any] = {
            "sysparm_limit": str(limit),
            "sysparm_offset": str(offset),
        }
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        if order_by:
            # Append ordering to query or set as standalone
            order_clause = f"ORDERBY{order_by}" if not order_by.startswith("-") else f"ORDERBYDESC{order_by[1:]}"
            if "sysparm_query" in params:
                params["sysparm_query"] = f"{params['sysparm_query']}^{order_clause}"
            else:
                params["sysparm_query"] = order_clause

        result = self.get(table, params=params)
        if isinstance(result, list):
            records: list[dict[str, Any]] = result
            return records
        return []

    def get_record_count(
        self,
        table: str,
        query: str | None = None,
    ) -> int:
        """Get the count of records matching a query using the stats API.

        Uses the ServiceNow aggregate API (``/api/now/stats/``) instead of
        the table API for efficient counting without retrieving record data.

        Args:
            table: ServiceNow table name.
            query: Optional encoded query string to filter records.

        Returns:
            The number of matching records.

        Raises:
            ServiceNowError: On any API or network error.
        """
        url = self._build_api_url(f"/api/now/stats/{table}")
        params: dict[str, str] = {"sysparm_count": "true"}
        if query:
            params["sysparm_query"] = query

        response = self._request("GET", url, params=params)
        _raise_for_status(response)

        try:
            body = response.json()
            stats = body.get("result", {}).get("stats", {})
            return int(stats.get("count", 0))
        except (ValueError, KeyError, TypeError) as exc:
            raise ServiceNowAPIError(
                message=f"Failed to parse count response: {exc}",
                details={"table": table, "query": query},
            ) from exc

    def test_connection(self) -> dict[str, Any]:
        """Test the connection and authentication to the ServiceNow instance.

        Makes a lightweight GET request to the ``sys_properties`` table with
        a limit of 1 to verify that the client can connect, authenticate,
        and receive a valid response.

        Returns:
            A dict with connection test results::

                {
                    "success": True,
                    "instance": "https://dev12345.service-now.com",
                    "status_code": 200,
                    "message": "Connection successful"
                }

        Raises:
            ServiceNowAuthError: If authentication fails.
            ServiceNowConnectionError: If the instance is unreachable.
            ServiceNowError: On any other error.
        """
        url = self._build_table_url("sys_properties")
        params: dict[str, str] = {"sysparm_limit": "1"}

        response = self._request("GET", url, params=params)
        _raise_for_status(response)

        return {
            "success": True,
            "instance": self._instance,
            "status_code": response.status_code,
            "message": "Connection successful",
        }
