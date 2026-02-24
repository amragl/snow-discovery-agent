# SNOW Discovery Agent - ServiceNow Discovery Operations

## Overview
Discovery scheduling, result analysis, failure remediation, IP range/credential/pattern management for ServiceNow Discovery via REST API.

## Core Principles (NON-NEGOTIABLE)
1. **ZERO MOCKS** — Every API call, data point, and integration must be real. No mock data, no hardcoded values, no stub implementations. If the ServiceNow instance isn’t available, STOP and report the blocker.
2. **FAIL-STOP** — If any agent or tool encounters an error, the pipeline halts. No silent failures. No workarounds. Fix the issue, then resume.
3. **CREDENTIAL SAFETY** — Never log, expose, or return credential secrets. Handle credential references by sys_id only.

## Architecture
```
FastMCP Server (server.py)
  |
  +-- schedule_discovery        (create/manage discovery schedules)
  +-- analyze_discovery         (analyze discovery results + failures)
  +-- remediate_discovery       (fix failed discoveries)
  +-- compare_discoveries       (compare discovery runs)
  +-- manage_ranges             (IP range management)
  +-- manage_credentials        (credential lifecycle)
  +-- check_health              (discovery infrastructure health)
  +-- manage_patterns           (CMDB CI patterns)
  +-- get_status                (discovery run status)
  +-- list_schedules            (list all schedules)
  |
  +-- ServiceNowClient (client.py) -> ServiceNow REST API
```

## MCP Tools (10 tools)
| Tool | Purpose |
|------|---------|
| `schedule_discovery` | Create and manage discovery schedules |
| `analyze_discovery` | Analyze discovery results and failures |
| `remediate_discovery` | Fix failed discovery issues |
| `compare_discoveries` | Compare two discovery runs |
| `manage_ranges` | IP range CRUD operations |
| `manage_credentials` | Credential lifecycle management |
| `check_health` | Discovery infrastructure health check |
| `manage_patterns` | CMDB CI pattern management |
| `get_status` | Get discovery run status |
| `list_schedules` | List all discovery schedules |

## ServiceNow Tables
| Table | Purpose |
|-------|---------|
| `discovery_status` | Discovery run status |
| `discovery_log` | Discovery logs |
| `discovery_schedule` | Discovery schedules |
| `discovery_credential` | Discovery credentials |
| `discovery_range` | IP ranges |
| `cmdb_ci_pattern` | CI patterns |
| `sys_properties` | System properties |

## Configuration
- **Env prefix:** `SNOW_*`
- **Key variables:** `SNOW_INSTANCE`, `SNOW_USERNAME`, `SNOW_PASSWORD`

## Key Files
- `src/snow_discovery_agent/server.py` — MCP server entry point
- `src/snow_discovery_agent/tools/` — Tool modules
- `src/snow_discovery_agent/client.py` — ServiceNow REST API client

## Git Workflow
- All agent work happens on feature branches
- PRs for human review before merging
- Never push directly to main
