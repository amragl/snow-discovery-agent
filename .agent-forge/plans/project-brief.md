# Project Brief: snow-discovery-agent

## Overview
An autonomous AI agent for ServiceNow Discovery operations, built as an MCP server. It manages network discovery schedules, monitors discovery health, detects and classifies Configuration Items (CIs), populates the CMDB with discovered data, and handles discovery credential management -- all through intelligent automation with risk-based decision-making.

## Objectives
1. Automate ServiceNow Discovery schedule management (create, configure, monitor, troubleshoot)
2. Provide real-time discovery health monitoring with proactive issue detection
3. Detect and classify CIs from discovery data with confidence scoring
4. Populate and reconcile CMDB records from discovery results
5. Manage discovery credentials securely with rotation and health tracking

## Target Users
- ITOM/Network teams managing ServiceNow Discovery at scale
- CMDB teams needing automated CI detection and population
- The ITOM Orchestrator (itom-orchestrator) for coordinated multi-agent operations
- AI assistants orchestrating discovery workflows via MCP protocol

## Tech Stack
- **Languages:** Python 3.11+
- **Frameworks:** FastMCP, Pydantic
- **Databases:** None (stateless -- uses ServiceNow as backend)
- **APIs/Services:** ServiceNow REST API (discovery_schedule, cmdb_ci, dscy_credentials), MCP Protocol
- **Infrastructure:** Claude Code CLI

## Requirements

### Must Have (P0)
1. Discovery schedule CRUD and monitoring MCP tools
2. Discovery health assessment with metrics collection
3. CI detection and classification engine
4. CMDB population with conflict resolution
5. Credential management with health checking

### Should Have (P1)
1. Risk-based decision engine for autonomous discovery operations
2. Discovery troubleshooting automation (log analysis, common fix suggestions)
3. Structured JSON logging with correlation IDs
4. Comprehensive unit and integration tests

### Nice to Have (P2)
1. Discovery scheduling optimization (time windows, overlap detection)
2. Multi-instance discovery coordination
3. Integration tests against real ServiceNow instance
4. Performance benchmarking for large-scale discovery

## Constraints
- Depends on ServiceNow instance with Discovery plugin activated
- Discovery credential access requires elevated ServiceNow permissions
- Must coordinate with servicenow-cmdb-mcp for CMDB writes
- Network scanning operations carry inherent risk -- must implement safety controls

## Existing Codebase
- **Starting from scratch:** Yes -- planning phase only
- **Existing repo:** https://github.com/amragl/snow-discovery-agent.git
- **Current state:** Planned. 0/25 tickets complete. All 5 phases at 0%.
- **Technical debt:** None (greenfield)

## Dependencies
- servicenow-cmdb-mcp (foundation MCP server -- execution order #1)
- ServiceNow instance with Discovery plugin and REST API access
- Python 3.11+ runtime

## Success Criteria
1. All discovery MCP tools operational and tested
2. Discovery health monitoring detects and reports issues proactively
3. CI classification achieves high accuracy against known CI types
4. CMDB population handles conflicts and deduplication correctly
5. Credential management secure with no plaintext exposure

## Notes
- Execution order #3 in the ServiceNow Suite -- depends on servicenow-cmdb-mcp
- Greenfield project -- roadmap has 5 phases from Foundation through Testing & Documentation
- Uses DISC-xxx ticket prefix in the backlog
- 25 tickets planned across 5 phases
