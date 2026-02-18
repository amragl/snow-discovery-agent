"""Snow Discovery Agent -- MCP server for ServiceNow Discovery operations.

Automates ServiceNow Discovery operations including scheduling scans,
analyzing results, remediating failures, and managing discovery patterns
and credentials via the Model Context Protocol (MCP).
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "amragl"

from .client import ServiceNowClient
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

__all__ = [
    "CIDelta",
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
    "parse_snow_datetime",
]
