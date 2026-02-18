# ---------------------------------------------------------------------------
# snow-discovery-agent — MCP server container
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# Metadata
LABEL maintainer="amragl"
LABEL description="MCP server for ServiceNow Discovery operations"

# Security: run as non-root
RUN addgroup --system agent && adduser --system --ingroup agent agent

WORKDIR /app

# Install dependencies first (separate layer for caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Copy source
COPY src/ ./src/

# Switch to non-root user
USER agent

# Environment defaults (override at runtime)
ENV LOG_LEVEL=INFO
ENV SERVICENOW_TIMEOUT=30
ENV SERVICENOW_MAX_RETRIES=3

# MCP server runs on stdio by default
CMD ["python3", "-m", "snow_discovery_agent.server"]
