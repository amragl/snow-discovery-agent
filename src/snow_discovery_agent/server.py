"""FastMCP server for the Snow Discovery Agent.

Entry point for the MCP server that exposes ServiceNow Discovery tools
via the Model Context Protocol.  Initializes the FastMCP server instance,
loads configuration, creates a ``ServiceNowClient``, and registers tools
using ``@mcp.tool()`` decorators.

The server is designed for graceful degradation: it starts even when
ServiceNow configuration is missing, but tools that require a client
will return structured error responses indicating the configuration issue.

Usage::

    # Via entry point
    snow-discovery-agent

    # Via module
    python -m snow_discovery_agent.server
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from fastmcp import FastMCP

from .config import DiscoveryAgentConfig, get_config
from .exceptions import ServiceNowError

if TYPE_CHECKING:
    from .client import ServiceNowClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    "snow-discovery-agent",
    instructions=(
        "ServiceNow Discovery Agent -- an MCP server for managing and "
        "analyzing ServiceNow Discovery operations including scheduling "
        "scans, checking status, managing credentials, ranges, and patterns, "
        "and computing discovery health metrics."
    ),
)

# ---------------------------------------------------------------------------
# Server state -- populated during startup
# ---------------------------------------------------------------------------

_config: DiscoveryAgentConfig | None = None
_client: ServiceNowClient | None = None
_config_error: str | None = None


def _init_server() -> None:
    """Load configuration and create the ServiceNow client.

    Called once at server startup.  If configuration is missing or
    invalid, the error is captured and the server continues in degraded
    mode.  The ``get_server_info`` tool reports the configuration status
    so callers can understand why operations may fail.
    """
    global _config, _client, _config_error

    try:
        _config = get_config()
    except Exception as exc:
        _config_error = str(exc)
        logger.warning(
            "Configuration not available -- server running in degraded mode: %s",
            _config_error,
        )
        return

    # Configure logging level from the loaded config
    log_level = getattr(logging, _config.log_level, logging.INFO)
    logging.getLogger("snow_discovery_agent").setLevel(log_level)

    try:
        _client = _config.create_client()
        logger.info(
            "ServiceNow client created for instance: %s",
            _config.instance,
        )
    except Exception as exc:
        _config_error = f"Client creation failed: {exc}"
        logger.warning("Failed to create ServiceNow client: %s", exc)


def get_client() -> ServiceNowClient:
    """Return the server-wide ``ServiceNowClient``.

    Raises:
        ServiceNowError: If no client is available (configuration missing
            or client creation failed).
    """
    if _client is None:
        msg = _config_error or "ServiceNow client not initialized -- check configuration"
        raise ServiceNowError(
            message=msg,
            error_code="CLIENT_NOT_CONFIGURED",
        )
    return _client


def get_server_config() -> DiscoveryAgentConfig | None:
    """Return the server-wide ``DiscoveryAgentConfig``, or None if unavailable."""
    return _config


# ---------------------------------------------------------------------------
# Error handling helper
# ---------------------------------------------------------------------------


def handle_tool_error(exc: Exception) -> dict[str, Any]:
    """Convert an exception into a structured MCP tool error response.

    Catches ``ServiceNowError`` subclasses and formats them as a dict
    with ``error``, ``error_code``, and optional ``status_code`` and
    ``details`` keys.  For unexpected exceptions, returns a generic
    error response.

    Args:
        exc: The exception raised during tool execution.

    Returns:
        A structured error dict suitable for returning from an MCP tool.
    """
    if isinstance(exc, ServiceNowError):
        return exc.to_dict()

    logger.exception("Unexpected error in tool execution: %s", exc)
    return {
        "error": str(exc),
        "error_code": "UNEXPECTED_ERROR",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
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

    Provides five operations against the discovery_credential table:

    - **list**: Query credentials with optional filters (filter_type,
      filter_active, filter_tag).
    - **get**: Retrieve a single credential by sys_id.
    - **create**: Create a new credential. Requires name and credential_type.
    - **update**: Partially update an existing credential by sys_id.
    - **delete**: Delete a credential by sys_id.

    Security: Credential secrets (passwords, private keys) are never
    returned in responses. Only metadata fields are exposed: sys_id,
    name, type, active, tag, order, affinity.

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
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.credentials import manage_discovery_credentials as _impl

    return _impl(
        action=action,
        sys_id=sys_id,
        name=name,
        credential_type=credential_type,
        tag=tag,
        order=order,
        active=active,
        filter_type=filter_type,
        filter_active=filter_active,
        filter_tag=filter_tag,
        limit=limit,
    )


@mcp.tool()
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
      and ``discover_type`` (IP, CI, Network, Cloud, Configuration).

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
    from .tools.schedule import schedule_discovery_scan as _impl

    return _impl(
        action=action,
        schedule_sys_id=schedule_sys_id,
        name=name,
        discover_type=discover_type,
        ip_ranges=ip_ranges,
        mid_server=mid_server,
        max_run_time=max_run_time,
    )


@mcp.tool()
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
    - **list**: List recent scans with optional state/date filters.
    - **details**: Get detailed results including log entries.
    - **poll**: Check whether a scan has completed.

    Args:
        action: Operation -- 'get', 'list', 'details', or 'poll'.
        scan_sys_id: Scan sys_id (required for get, details, poll).
        state: Filter by state (Starting, Active, Completed, Cancelled, Error).
        limit: Maximum records for list (default 20).
        date_from: Filter scans started on or after (YYYY-MM-DD).
        date_to: Filter scans started on or before (YYYY-MM-DD).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.status import get_discovery_status as _impl

    return _impl(
        action=action,
        scan_sys_id=scan_sys_id,
        state=state,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )


@mcp.tool()
def list_discovery_schedules(
    action: str,
    schedule_sys_id: str | None = None,
    active: bool | None = None,
    discover_type: str | None = None,
    name_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List and view ServiceNow Discovery schedule configurations.

    Supports three actions:

    - **list**: Query schedules with optional filters.
    - **get**: Retrieve a single schedule by sys_id.
    - **summary**: Return counts and status overview.

    Args:
        action: Operation -- 'list', 'get', or 'summary'.
        schedule_sys_id: Schedule sys_id (required for get).
        active: Filter by active status (for list).
        discover_type: Filter by discovery type (for list).
        name_filter: Filter by name pattern (for list).
        limit: Maximum records for list (default 100).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.schedules_list import list_discovery_schedules as _impl

    return _impl(
        action=action,
        schedule_sys_id=schedule_sys_id,
        active=active,
        discover_type=discover_type,
        name_filter=name_filter,
        limit=limit,
    )


@mcp.tool()
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

    Supports six actions: list, get, create, update, delete, validate.
    Includes IPv4/IPv6 validation and CIDR support.

    Args:
        action: Operation to perform.
        sys_id: Range sys_id (required for get, update, delete).
        name: Range name (required for create).
        range_type: 'IP Range', 'IP Network', or 'IP Address'.
        range_start: Start IP, CIDR, or single IP.
        range_end: End IP (required for IP Range type).
        active: Whether the range is active.
        include: Whether to include or exclude this range.
        filter_type: Filter by range type (for list).
        filter_active: Filter by active status (for list).
        limit: Maximum records for list (default 100).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.ranges import manage_discovery_ranges as _impl

    return _impl(
        action=action,
        sys_id=sys_id,
        name=name,
        range_type=range_type,
        range_start=range_start,
        range_end=range_end,
        active=active,
        include=include,
        filter_type=filter_type,
        filter_active=filter_active,
        limit=limit,
    )


@mcp.tool()
def analyze_discovery_results(
    action: str,
    scan_sys_id: str | None = None,
    schedule_sys_id: str | None = None,
    last_n_scans: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Analyze ServiceNow Discovery scan results and identify patterns.

    Supports four actions:

    - **analyze**: Analyze a specific scan's results.
    - **errors**: Categorize errors from a scan's logs.
    - **trend**: Analyze trends across multiple scans.
    - **coverage**: Compute IP coverage for a schedule.

    Args:
        action: Operation -- 'analyze', 'errors', 'trend', or 'coverage'.
        scan_sys_id: Scan sys_id (required for analyze, errors).
        schedule_sys_id: Schedule sys_id (for trend, coverage).
        last_n_scans: Recent scans to analyze (default 10).
        date_from: Start date filter (YYYY-MM-DD).
        date_to: End date filter (YYYY-MM-DD).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.analysis import analyze_discovery_results as _impl

    return _impl(
        action=action,
        scan_sys_id=scan_sys_id,
        schedule_sys_id=schedule_sys_id,
        last_n_scans=last_n_scans,
        date_from=date_from,
        date_to=date_to,
    )


@mcp.tool()
def remediate_discovery_failures(
    action: str,
    scan_sys_id: str | None = None,
    remediation_type: str | None = None,
    target_items: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Diagnose and remediate common ServiceNow Discovery failures.

    Supports five actions: diagnose, credential_fix, network_fix,
    classification_fix, bulk_remediate.

    Safety: Never auto-modifies credentials without explicit confirmation.
    Always returns a dry-run plan first when confirm=False.

    Args:
        action: Operation to perform.
        scan_sys_id: Scan sys_id (required for all actions).
        remediation_type: Type of remediation (for bulk_remediate).
        target_items: List of IPs or CI sys_ids (for bulk_remediate).
        confirm: Execute changes (default False = dry-run only).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.remediation import remediate_discovery_failures as _impl

    return _impl(
        action=action,
        scan_sys_id=scan_sys_id,
        remediation_type=remediation_type,
        target_items=target_items,
        confirm=confirm,
    )


@mcp.tool()
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
    - **analyze**: Show patterns for a CI type, identify conflicts.
    - **coverage**: Show CI types with/without pattern coverage.

    Args:
        action: Operation -- 'list', 'get', 'analyze', or 'coverage'.
        pattern_sys_id: Pattern sys_id (required for get).
        ci_type: CI type (required for analyze, optional filter for list).
        active: Filter by active status (for list).
        name_filter: Filter by name pattern (for list).
        limit: Maximum records (default 100).

    Returns:
        A dict with success status, data, message, action, and error fields.
    """
    from .tools.patterns import get_discovery_patterns as _impl

    return _impl(
        action=action,
        pattern_sys_id=pattern_sys_id,
        ci_type=ci_type,
        active=active,
        name_filter=name_filter,
        limit=limit,
    )


@mcp.tool()
def get_discovery_health(
    period: str = "week",
    include_recommendations: bool = True,
) -> dict[str, Any]:
    """Compute overall ServiceNow Discovery health metrics.

    Aggregates data from discovery_status, discovery_schedule,
    discovery_credential, and discovery_range tables to produce a
    composite health score (0-100).

    Health ratings: Healthy (>80), Warning (50-80), Critical (<50).

    Args:
        period: Analysis period -- 'day', 'week', or 'month' (default 'week').
        include_recommendations: Include actionable recommendations (default True).

    Returns:
        A dict with success status, data (health summary + sub-metrics),
        message, action, and error fields.
    """
    from .tools.health import get_discovery_health as _impl

    return _impl(
        period=period,
        include_recommendations=include_recommendations,
    )


@mcp.tool()
def compare_discovery_runs(
    action: str,
    scan_a_sys_id: str | None = None,
    scan_b_sys_id: str | None = None,
    schedule_sys_id: str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Compare the results of ServiceNow Discovery scans.

    Supports two actions:

    - **compare**: Detailed comparison of two specific scans (requires
      scan_a_sys_id and scan_b_sys_id).
    - **sequential**: Compare last N scans for a schedule to show
      progression over time.

    Args:
        action: Operation -- 'compare' or 'sequential'.
        scan_a_sys_id: First (baseline) scan sys_id.
        scan_b_sys_id: Second (comparison) scan sys_id.
        schedule_sys_id: Schedule sys_id (for sequential).
        last_n: Recent scans to compare (default 5).

    Returns:
        A dict with success status, data (DiscoveryCompareResult),
        message, action, and error fields.
    """
    from .tools.compare import compare_discovery_runs as _impl

    return _impl(
        action=action,
        scan_a_sys_id=scan_a_sys_id,
        scan_b_sys_id=scan_b_sys_id,
        schedule_sys_id=schedule_sys_id,
        last_n=last_n,
    )


@mcp.tool()
def get_server_info() -> dict[str, Any]:
    """Return server metadata and configuration status.

    Provides information about the running server instance including
    the server name, version, configured ServiceNow instance hostname
    (sanitized -- no credentials), and whether the configuration is
    loaded and the client is ready.

    Returns:
        A dict with server name, version, instance hostname,
        configuration status, and client readiness.
    """
    from . import __version__

    info: dict[str, Any] = {
        "server_name": "snow-discovery-agent",
        "version": __version__,
        "status": "running",
    }

    if _config is not None:
        # Sanitize: extract hostname only, never expose credentials or full URL
        parsed = urlparse(_config.instance)
        info["instance_hostname"] = parsed.hostname or "unknown"
        info["config_loaded"] = True
        info["log_level"] = _config.log_level
        info["timeout"] = _config.timeout
        info["max_results"] = _config.max_results
    else:
        info["instance_hostname"] = None
        info["config_loaded"] = False
        info["config_error"] = _config_error

    info["client_ready"] = _client is not None

    return info


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Snow Discovery Agent MCP server.

    Initializes configuration, creates the ServiceNow client (with
    graceful degradation if config is missing), and starts the FastMCP
    server for stdio transport.
    """
    # Set up root logging for the package
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    logger.info("Starting snow-discovery-agent MCP server")

    _init_server()

    if _config is not None:
        logger.info(
            "Server initialized: instance=%s, log_level=%s",
            _config.instance,
            _config.log_level,
        )
    else:
        logger.warning("Server started in degraded mode -- no ServiceNow configuration")

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
