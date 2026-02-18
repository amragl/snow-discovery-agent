"""Discovery tools package for the Snow Discovery Agent.

Provides MCP tool functions organized by discovery domain. Each module
implements one or more ``@mcp.tool()``-registered functions that interact
with ServiceNow Discovery tables via the shared ``ServiceNowClient``.

Module layout:
    credentials.py  -- Discovery credential CRUD operations
"""

from __future__ import annotations

from .credentials import manage_discovery_credentials

__all__ = [
    "manage_discovery_credentials",
]
