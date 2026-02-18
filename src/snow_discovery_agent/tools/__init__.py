"""Discovery tools package for the Snow Discovery Agent.

Provides MCP tool functions organized by discovery domain. Each module
implements one or more ``@mcp.tool()``-registered functions that interact
with ServiceNow Discovery tables via the shared ``ServiceNowClient``.

Module layout:
    credentials.py     -- Discovery credential CRUD operations
    schedule.py        -- Schedule and trigger discovery scans
    status.py          -- Discovery scan status and results
    schedules_list.py  -- List and view discovery schedules
    ranges.py          -- IP range CRUD operations
    utils.py           -- Shared utility functions
    errors.py          -- Tool-specific error types
    analysis.py        -- Scan result analysis
    remediation.py     -- Failure diagnosis and remediation
    patterns.py        -- CI classification pattern management
    health.py          -- Discovery health metrics
    compare.py         -- Discovery run comparison
"""

from __future__ import annotations

from .analysis import analyze_discovery_results
from .compare import compare_discovery_runs
from .credentials import manage_discovery_credentials
from .health import get_discovery_health
from .patterns import get_discovery_patterns
from .ranges import manage_discovery_ranges
from .remediation import remediate_discovery_failures
from .schedule import schedule_discovery_scan
from .schedules_list import list_discovery_schedules
from .status import get_discovery_status

__all__ = [
    "analyze_discovery_results",
    "compare_discovery_runs",
    "get_discovery_health",
    "get_discovery_patterns",
    "get_discovery_status",
    "list_discovery_schedules",
    "manage_discovery_credentials",
    "manage_discovery_ranges",
    "remediate_discovery_failures",
    "schedule_discovery_scan",
]
