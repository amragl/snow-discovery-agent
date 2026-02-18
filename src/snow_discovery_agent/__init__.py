"""Snow Discovery Agent -- MCP server for ServiceNow Discovery operations.

Automates ServiceNow Discovery operations including scheduling scans,
analyzing results, remediating failures, and managing discovery patterns
and credentials via the Model Context Protocol (MCP).
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "amragl"

from .client import ServiceNowClient
from .config import DiscoveryAgentConfig, get_config
from .exceptions import (
    ServiceNowAPIError,
    ServiceNowAuthError,
    ServiceNowConnectionError,
    ServiceNowError,
    ServiceNowNotFoundError,
    ServiceNowPermissionError,
    ServiceNowRateLimitError,
)
from .models import (
    CIDelta,
    DiscoveryCompareResult,
    DiscoveryCredential,
    DiscoveryHealthSummary,
    DiscoveryLog,
    DiscoveryPattern,
    DiscoveryRange,
    DiscoverySchedule,
    DiscoveryStatus,
    ErrorCount,
    ErrorDelta,
    SnowBaseModel,
    parse_snow_datetime,
)
from .server import get_client, get_server_config, handle_tool_error, mcp
from .tools.analysis import analyze_discovery_results
from .tools.compare import compare_discovery_runs
from .tools.credentials import manage_discovery_credentials
from .tools.health import get_discovery_health
from .tools.patterns import get_discovery_patterns
from .tools.ranges import manage_discovery_ranges
from .tools.remediation import remediate_discovery_failures
from .tools.schedule import schedule_discovery_scan
from .tools.schedules_list import list_discovery_schedules
from .tools.status import get_discovery_status

__all__ = [
    "CIDelta",
    "DiscoveryAgentConfig",
    "DiscoveryCompareResult",
    "DiscoveryCredential",
    "DiscoveryHealthSummary",
    "DiscoveryLog",
    "DiscoveryPattern",
    "DiscoveryRange",
    "DiscoverySchedule",
    "DiscoveryStatus",
    "ErrorCount",
    "ErrorDelta",
    "ServiceNowAPIError",
    "ServiceNowAuthError",
    "ServiceNowClient",
    "ServiceNowConnectionError",
    "ServiceNowError",
    "ServiceNowNotFoundError",
    "ServiceNowPermissionError",
    "ServiceNowRateLimitError",
    "SnowBaseModel",
    "analyze_discovery_results",
    "compare_discovery_runs",
    "get_client",
    "get_config",
    "get_discovery_health",
    "get_discovery_patterns",
    "get_discovery_status",
    "get_server_config",
    "handle_tool_error",
    "list_discovery_schedules",
    "manage_discovery_credentials",
    "manage_discovery_ranges",
    "mcp",
    "parse_snow_datetime",
    "remediate_discovery_failures",
    "schedule_discovery_scan",
]
