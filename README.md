# snow-discovery-agent

An MCP (Model Context Protocol) server that automates ServiceNow Discovery operations —
scheduling scans, analyzing results, remediating failures, and managing discovery
patterns and credentials — using natural language via Claude Code or Claude Desktop.

Part of the **[ServiceNow Suite](https://github.com/amragl/servicenow-suite)** — a
full ITOM ServiceNow automation stack.

---

## What It Does

Given a natural language request, snow-discovery-agent:

1. **Schedules discovery scans** — trigger immediate or recurring network scans
2. **Analyzes results** — surface CI counts, errors, and coverage from discovery logs
3. **Remediates failures** — identify recurring error patterns and apply fixes
4. **Compares discovery runs** — diff two runs to see what changed in your CMDB
5. **Manages IP ranges** — add, list, update, and delete discovery IP ranges
6. **Manages credentials** — CRUD for discovery credentials (no secrets in output)
7. **Monitors health** — summarize discovery health across all active schedules
8. **Lists and inspects patterns** — view and manage discovery patterns

---

## Architecture

```
User (via Claude Code or Claude Desktop)
    │
    ▼
MCP Protocol (stdio / HTTP)
    │
    ▼
FastMCP Server (snow_discovery_agent.server)
    │
    ├── tools/analysis.py          analyze_discovery_results
    ├── tools/compare.py           compare_discovery_runs
    ├── tools/credentials.py       manage_discovery_credentials
    ├── tools/health.py            get_discovery_health
    ├── tools/patterns.py          get_discovery_patterns
    ├── tools/ranges.py            manage_discovery_ranges
    ├── tools/remediation.py       remediate_discovery_failures
    ├── tools/schedule.py          schedule_discovery_scan
    ├── tools/schedules_list.py    list_discovery_schedules
    └── tools/status.py            get_discovery_status
         │
         ▼
    ServiceNowClient (client.py)
         │
         ▼
    ServiceNow REST API
    (Table API + Discovery API)
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `analyze_discovery_results` | Analyze discovery logs — CI counts, error rates, coverage |
| `compare_discovery_runs` | Diff two discovery runs to see CMDB deltas |
| `manage_discovery_credentials` | CRUD for discovery credentials (no secrets exposed) |
| `get_discovery_health` | Health summary across all active schedules |
| `get_discovery_patterns` | List and inspect active discovery patterns |
| `manage_discovery_ranges` | Add, list, update, delete IP discovery ranges |
| `remediate_discovery_failures` | Identify error patterns and apply remediation steps |
| `schedule_discovery_scan` | Trigger or schedule a discovery scan |
| `list_discovery_schedules` | List all configured discovery schedules |
| `get_discovery_status` | Current status of discovery operations |

---

## Setup

### Prerequisites

- Python 3.11 or later
- A ServiceNow developer instance (free at [developer.servicenow.com](https://developer.servicenow.com))
- Claude Code or Claude Desktop with MCP support

### 1. Install

```bash
git clone https://github.com/amragl/snow-discovery-agent.git
cd snow-discovery-agent
pip install -e ".[dev]"
```

Or with pip directly:

```bash
pip install snow-discovery-agent
```

### 2. Configure

Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required — your ServiceNow instance
SERVICENOW_INSTANCE=https://devXXXXXX.service-now.com
SERVICENOW_USERNAME=admin
SERVICENOW_PASSWORD=your-password-here

# Optional
SERVICENOW_TIMEOUT=30
SERVICENOW_MAX_RETRIES=3
LOG_LEVEL=INFO
```

### 3. Register with Claude Code

Add to your Claude Code configuration (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "snow-discovery-agent": {
      "command": "python3",
      "args": ["-m", "snow_discovery_agent.server"],
      "cwd": "/path/to/snow-discovery-agent",
      "env": {
        "SERVICENOW_INSTANCE": "https://devXXXXXX.service-now.com",
        "SERVICENOW_USERNAME": "admin",
        "SERVICENOW_PASSWORD": "your-password"
      }
    }
  }
}
```

### 4. Register with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "snow-discovery-agent": {
      "command": "python3",
      "args": ["-m", "snow_discovery_agent.server"],
      "cwd": "/path/to/snow-discovery-agent",
      "env": {
        "SERVICENOW_INSTANCE": "https://devXXXXXX.service-now.com",
        "SERVICENOW_USERNAME": "admin",
        "SERVICENOW_PASSWORD": "your-password"
      }
    }
  }
}
```

---

## Usage Examples

### Schedule a Discovery Scan

```
Schedule an immediate discovery scan on the 10.0.0.0/8 range.
```

### Analyze Results

```
Analyze the last 24 hours of discovery results and show me error counts by type.
```

### Remediate Failures

```
Find the most common discovery errors and suggest remediation steps.
```

### Compare Runs

```
Compare the last two discovery runs and show me what changed in the CMDB.
```

### Manage IP Ranges

```
List all discovery IP ranges in the 192.168.0.0/16 subnet.
```

### Check Health

```
Give me a health summary of all active discovery schedules.
```

---

## Docker

### Build and Run

```bash
docker build -t snow-discovery-agent .
docker run -e SERVICENOW_INSTANCE=https://devXXXXXX.service-now.com \
           -e SERVICENOW_USERNAME=admin \
           -e SERVICENOW_PASSWORD=secret \
           snow-discovery-agent
```

### Docker Compose

```bash
# Copy and edit the environment file
cp .env.example .env

# Start the service
docker-compose up -d
```

---

## Development

### Running Tests

```bash
# Unit tests (no ServiceNow connection required)
pytest tests/ --ignore=tests/integration -v

# With coverage report
pytest tests/ --ignore=tests/integration --cov=snow_discovery_agent --cov-report=term-missing

# Integration tests (requires live ServiceNow instance)
SERVICENOW_INSTANCE=https://dev123.service-now.com \
SERVICENOW_USERNAME=admin \
SERVICENOW_PASSWORD=secret \
pytest tests/integration/ -m integration -v
```

### Linting

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

### Type Checking

```bash
mypy src/
```

### Code Formatting

```bash
ruff format src/ tests/
```

---

## Project Structure

```
snow-discovery-agent/
├── src/
│   └── snow_discovery_agent/
│       ├── __init__.py          # Package init + public API
│       ├── client.py            # ServiceNow REST client
│       ├── config.py            # Configuration (pydantic-settings)
│       ├── exceptions.py        # Structured exception hierarchy
│       ├── models.py            # Pydantic v2 data models
│       ├── server.py            # FastMCP server + tool registration
│       └── tools/
│           ├── analysis.py      # analyze_discovery_results
│           ├── compare.py       # compare_discovery_runs
│           ├── credentials.py   # manage_discovery_credentials
│           ├── health.py        # get_discovery_health
│           ├── patterns.py      # get_discovery_patterns
│           ├── ranges.py        # manage_discovery_ranges
│           ├── remediation.py   # remediate_discovery_failures
│           ├── schedule.py      # schedule_discovery_scan
│           ├── schedules_list.py # list_discovery_schedules
│           ├── status.py        # get_discovery_status
│           └── utils.py         # Shared helpers
├── tests/
│   ├── conftest.py              # Shared fixtures
│   ├── test_client.py           # Client unit tests
│   ├── test_config.py           # Config unit tests
│   ├── test_models.py           # Model unit tests
│   ├── test_server.py           # Server unit tests
│   ├── test_exceptions.py       # Exception hierarchy tests
│   ├── test_tools_*.py          # Per-tool unit tests (577+ tests)
│   └── integration/
│       └── test_integration.py  # Live ServiceNow integration tests
├── .env.example                 # Environment variable template
├── Dockerfile                   # Container image
├── docker-compose.yml           # Compose for local development
├── pyproject.toml               # Project config, deps, ruff, mypy
└── README.md
```

---

## Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SERVICENOW_INSTANCE` | Yes | — | Base URL: `https://devXXXXXX.service-now.com` |
| `SERVICENOW_USERNAME` | Yes | — | Admin username |
| `SERVICENOW_PASSWORD` | Yes | — | Admin password |
| `SERVICENOW_TIMEOUT` | No | 30 | Request timeout in seconds |
| `SERVICENOW_MAX_RETRIES` | No | 3 | Retries on transient errors |
| `SERVICENOW_RETRY_BACKOFF` | No | 1.0 | Initial retry backoff (seconds) |
| `LOG_LEVEL` | No | INFO | Python logging level |

---

## Error Handling

All tools return structured dicts. On error:

```python
{
    "error": "Human-readable message",
    "error_code": "SN_CONNECTION_ERROR",  # or SN_AUTH_ERROR, SN_NOT_FOUND, etc.
}
```

Transient errors (`SN_CONNECTION_ERROR`, `SN_TIMEOUT_ERROR`) are automatically retried.
Permanent errors (`SN_AUTH_ERROR`, `SN_NOT_FOUND`) are returned immediately.

---

## License

MIT License — see LICENSE file.
