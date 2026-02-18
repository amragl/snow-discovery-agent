# Claude MCP Integration — snow-discovery-agent

How to register snow-discovery-agent as an MCP server in Claude Code and Claude Desktop.

---

## Claude Code

Add to your project-level `.claude/settings.json` or global `~/.claude/settings.json`:

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

Or using a `.env` file (recommended — keeps credentials out of settings.json):

```json
{
  "mcpServers": {
    "snow-discovery-agent": {
      "command": "bash",
      "args": ["-c", "source .env && python3 -m snow_discovery_agent.server"],
      "cwd": "/path/to/snow-discovery-agent"
    }
  }
}
```

---

## Claude Desktop

### macOS

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

### Windows

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "snow-discovery-agent": {
      "command": "python",
      "args": ["-m", "snow_discovery_agent.server"],
      "cwd": "C:\\path\\to\\snow-discovery-agent",
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

## Docker (Claude Desktop)

If you prefer to run the server in Docker, Claude Desktop supports subprocess MCP servers.
Use a wrapper script:

**`run-mcp-server.sh`** (in the project root):

```bash
#!/bin/bash
docker run --rm -i \
  -e SERVICENOW_INSTANCE="${SERVICENOW_INSTANCE}" \
  -e SERVICENOW_USERNAME="${SERVICENOW_USERNAME}" \
  -e SERVICENOW_PASSWORD="${SERVICENOW_PASSWORD}" \
  snow-discovery-agent:latest
```

Then in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "snow-discovery-agent": {
      "command": "bash",
      "args": ["/path/to/snow-discovery-agent/run-mcp-server.sh"],
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

## Verifying the Connection

After configuring, ask Claude:

> "List all discovery schedules in ServiceNow."

Claude will call the `list_discovery_schedules` MCP tool and display the results.

---

## Available Tools

Once registered, Claude has access to these tools:

| Tool | Example Prompt |
|------|----------------|
| `list_discovery_schedules` | "List all active discovery schedules" |
| `schedule_discovery_scan` | "Schedule a scan on the 10.0.0.0/8 range" |
| `get_discovery_status` | "What's the current discovery status?" |
| `analyze_discovery_results` | "Analyze errors from the last discovery run" |
| `get_discovery_health` | "Give me a health summary of all schedules" |
| `remediate_discovery_failures` | "Find and fix the most common discovery errors" |
| `compare_discovery_runs` | "What changed between the last two runs?" |
| `manage_discovery_ranges` | "Add 172.16.0.0/12 as a discovery range" |
| `get_discovery_patterns` | "List all active discovery patterns" |
| `manage_discovery_credentials` | "List SSH credentials (no passwords shown)" |
