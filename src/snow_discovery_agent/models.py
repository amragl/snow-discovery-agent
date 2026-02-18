"""Pydantic v2 models for ServiceNow Discovery tables.

Defines data models for the core ServiceNow Discovery tables used by the
snow-discovery-agent MCP server.  Each model that maps to a ServiceNow table
provides a ``from_snow()`` classmethod that creates an instance from a raw
ServiceNow REST API response dict, handling field-name mapping and type
coercion (including ServiceNow's datetime format).

Custom models (``DiscoveryHealthSummary``, ``DiscoveryCompareResult``) are
used internally by analysis and comparison tools -- they do not map directly
to ServiceNow tables.

ServiceNow datetime format
--------------------------
ServiceNow returns datetimes as ``"YYYY-MM-DD HH:MM:SS"`` strings in UTC.
The helper ``parse_snow_datetime`` handles parsing these into Python
``datetime`` objects.  Empty strings and ``None`` values are coerced to
``None`` for optional datetime fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# ServiceNow datetime helpers
# ---------------------------------------------------------------------------

SNOW_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
"""The datetime format returned by the ServiceNow REST API."""


def parse_snow_datetime(value: str | None) -> datetime | None:
    """Parse a ServiceNow datetime string into a Python datetime.

    ServiceNow returns datetimes as ``"YYYY-MM-DD HH:MM:SS"`` in UTC.
    This function also accepts ISO 8601 format (``"YYYY-MM-DDTHH:MM:SS"``)
    for convenience.

    Args:
        value: A datetime string from ServiceNow, an empty string, or ``None``.

    Returns:
        A ``datetime`` object if the value is a non-empty string that can be
        parsed, otherwise ``None``.
    """
    if not value or not value.strip():
        return None

    value = value.strip()

    # Try ServiceNow's native format first
    try:
        return datetime.strptime(value, SNOW_DATETIME_FORMAT)
    except ValueError:
        pass

    # Fall back to ISO 8601 (with 'T' separator)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _coerce_bool(value: Any) -> bool:
    """Coerce a ServiceNow boolean-ish value to a Python bool.

    ServiceNow may return booleans as ``"true"``/``"false"`` strings,
    ``"1"``/``"0"`` strings, or actual bools.

    Args:
        value: The raw value from the ServiceNow API response.

    Returns:
        A Python ``bool``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    """Coerce a ServiceNow value to a Python int.

    ServiceNow often returns numeric fields as strings.

    Args:
        value: The raw value from the ServiceNow API response.
        default: Default to return when value is empty or unparseable.

    Returns:
        A Python ``int``.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


# ---------------------------------------------------------------------------
# Base model for ServiceNow table records
# ---------------------------------------------------------------------------


class SnowBaseModel(BaseModel):
    """Base model for all ServiceNow table-backed models.

    Provides common configuration and the ``from_snow()`` factory method
    pattern.  Subclasses override ``_field_map()`` to define the mapping
    from ServiceNow field names to Python attribute names when they differ.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        frozen=False,
    )

    sys_id: str = Field(
        default="",
        description="ServiceNow sys_id (32-character hex string).",
    )

    @classmethod
    def _field_map(cls) -> dict[str, str]:
        """Return a mapping of ServiceNow field names to model attribute names.

        Override in subclasses when ServiceNow field names differ from the
        Python attribute names.  Keys are ServiceNow field names; values are
        the corresponding Python attribute names on this model.

        Returns:
            A dict mapping ``{snow_field: python_attr}``.
        """
        return {}

    @classmethod
    def from_snow(cls, data: dict[str, Any]) -> Self:
        """Create an instance from a raw ServiceNow API response dict.

        Applies the field mapping from ``_field_map()`` so that ServiceNow
        field names are translated to the corresponding Python attribute
        names before Pydantic validation.

        Args:
            data: A single record dict from the ServiceNow ``result`` array.

        Returns:
            A validated model instance.
        """
        mapped: dict[str, Any] = {}
        field_map = cls._field_map()

        # Build a reverse lookup: python_attr -> snow_field for fields we
        # have explicit mappings for
        reverse_map = {v: k for k, v in field_map.items()}

        # Get all model field names
        model_fields = set(cls.model_fields.keys())

        for attr_name in model_fields:
            if attr_name in reverse_map:
                # This Python attr has a mapped ServiceNow field name
                snow_key = reverse_map[attr_name]
                if snow_key in data:
                    mapped[attr_name] = data[snow_key]
                elif attr_name in data:
                    # Fall back: maybe the data already uses the Python name
                    mapped[attr_name] = data[attr_name]
            elif attr_name in data:
                # No mapping needed; same name in both systems
                mapped[attr_name] = data[attr_name]

        return cls.model_validate(mapped)


# ---------------------------------------------------------------------------
# DiscoveryStatus -- discovery_status table
# ---------------------------------------------------------------------------


class DiscoveryStatus(SnowBaseModel):
    """Represents a record from the ``discovery_status`` table.

    Tracks the state and results of a single ServiceNow Discovery scan,
    including when it started and completed, how many CIs it found, and
    which IP address and MID server were involved.

    ServiceNow states: ``Starting``, ``Active``, ``Completed``,
    ``Cancelled``, ``Error``.
    """

    name: str = Field(
        default="",
        description="Display name / identifier for the discovery scan.",
    )
    state: str = Field(
        default="",
        description="Current state (Starting, Active, Completed, Cancelled, Error).",
    )
    source: str = Field(
        default="",
        description="The discovery schedule or source that triggered this scan.",
    )
    dscl_status: str = Field(
        default="",
        description="Detailed classification status of the discovery run.",
    )
    log: str = Field(
        default="",
        description="Discovery log summary text.",
    )
    started: datetime | None = Field(
        default=None,
        description="Timestamp when the scan started.",
    )
    completed: datetime | None = Field(
        default=None,
        description="Timestamp when the scan completed.",
    )
    ci_count: int = Field(
        default=0,
        description="Number of configuration items discovered.",
    )
    ip_address: str = Field(
        default="",
        description="IP address targeted by this discovery scan.",
    )
    mid_server: str = Field(
        default="",
        description="MID Server used for this discovery scan (sys_id or display value).",
    )

    @field_validator("started", "completed", mode="before")
    @classmethod
    def _parse_datetime(cls, v: Any) -> datetime | None:
        """Parse ServiceNow datetime strings for started/completed fields."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return parse_snow_datetime(v)
        return None

    @field_validator("ci_count", mode="before")
    @classmethod
    def _coerce_ci_count(cls, v: Any) -> int:
        """Coerce ci_count from string to int."""
        return _coerce_int(v)

    @classmethod
    def _field_map(cls) -> dict[str, str]:
        """Map ServiceNow ``discovery_status`` fields to Python attributes."""
        return {
            "ip_address": "ip_address",
            "mid_server": "mid_server",
            "dscl_status": "dscl_status",
            "ci_count": "ci_count",
        }


# ---------------------------------------------------------------------------
# DiscoverySchedule -- discovery_schedule table
# ---------------------------------------------------------------------------


class DiscoverySchedule(SnowBaseModel):
    """Represents a record from the ``discovery_schedule`` table.

    Defines when and how ServiceNow Discovery scans are run, including
    the discovery type, scheduling cadence, MID server selection, and
    maximum run time.
    """

    name: str = Field(
        default="",
        description="Name of the discovery schedule.",
    )
    active: bool = Field(
        default=True,
        description="Whether this schedule is active.",
    )
    discover: str = Field(
        default="",
        description="Discovery type (e.g., 'IP', 'CI', 'Network').",
    )
    max_run_time: str = Field(
        default="02:00:00",
        description="Maximum scan run time in HH:MM:SS format.",
    )
    run_dayofweek: str = Field(
        default="",
        description="Days of the week when the schedule runs (e.g., 'Monday,Wednesday').",
    )
    run_time: str = Field(
        default="",
        description="Time of day when the schedule runs (HH:MM:SS format).",
    )
    mid_select_method: str = Field(
        default="",
        description="Method for selecting a MID server (e.g., 'Auto', 'Specific').",
    )
    location: str = Field(
        default="",
        description="Location associated with this schedule (sys_id or display value).",
    )

    @field_validator("active", mode="before")
    @classmethod
    def _coerce_active(cls, v: Any) -> bool:
        """Coerce active field from ServiceNow string to bool."""
        return _coerce_bool(v)


# ---------------------------------------------------------------------------
# DiscoveryCredential -- discovery_credential table
# ---------------------------------------------------------------------------


class DiscoveryCredential(SnowBaseModel):
    """Represents a record from the ``discovery_credential`` table.

    Contains metadata about a discovery credential. For security, this model
    intentionally excludes secret fields (passwords, private keys) -- only
    non-sensitive metadata is exposed.
    """

    name: str = Field(
        default="",
        description="Credential name.",
    )
    type: str = Field(
        default="",
        description="Credential type (e.g., 'SSH', 'SNMP', 'Windows', 'VMware').",
    )
    active: bool = Field(
        default=True,
        description="Whether this credential is active.",
    )
    tag: str = Field(
        default="",
        description="Credential tag for grouping and selection.",
    )
    order: int = Field(
        default=100,
        description="Evaluation order (lower numbers are tried first).",
    )
    affinity: str = Field(
        default="",
        description="Credential affinity setting.",
    )

    @field_validator("active", mode="before")
    @classmethod
    def _coerce_active(cls, v: Any) -> bool:
        """Coerce active field from ServiceNow string to bool."""
        return _coerce_bool(v)

    @field_validator("order", mode="before")
    @classmethod
    def _coerce_order(cls, v: Any) -> int:
        """Coerce order field from ServiceNow string to int."""
        return _coerce_int(v, default=100)


# ---------------------------------------------------------------------------
# DiscoveryRange -- discovery_range table
# ---------------------------------------------------------------------------


class DiscoveryRange(SnowBaseModel):
    """Represents a record from the ``discovery_range`` table.

    Defines an IP address range, network, or single IP used for discovery
    scanning.  The ``type`` field determines how ``range_start`` and
    ``range_end`` are interpreted.

    Types:
    - ``IP Range``: ``range_start`` and ``range_end`` define a contiguous range.
    - ``IP Network``: ``range_start`` holds a CIDR notation (e.g., ``10.0.0.0/24``).
    - ``IP Address``: ``range_start`` holds a single IP address.
    """

    name: str = Field(
        default="",
        description="Name of the discovery range.",
    )
    type: str = Field(
        default="",
        description="Range type ('IP Range', 'IP Network', 'IP Address').",
    )
    active: bool = Field(
        default=True,
        description="Whether this range is active.",
    )
    range_start: str = Field(
        default="",
        description="Start IP address, CIDR network, or single IP.",
    )
    range_end: str = Field(
        default="",
        description="End IP address (for IP Range type only).",
    )
    include: bool = Field(
        default=True,
        description="Whether to include (True) or exclude (False) this range.",
    )

    @field_validator("active", "include", mode="before")
    @classmethod
    def _coerce_bools(cls, v: Any) -> bool:
        """Coerce boolean fields from ServiceNow strings."""
        return _coerce_bool(v)


# ---------------------------------------------------------------------------
# DiscoveryPattern -- cmdb_ci_pattern table
# ---------------------------------------------------------------------------


class DiscoveryPattern(SnowBaseModel):
    """Represents a record from the ``cmdb_ci_pattern`` table.

    CI classification patterns define the rules ServiceNow uses to classify
    discovered devices into specific Configuration Item (CI) types in the CMDB.
    """

    name: str = Field(
        default="",
        description="Pattern name.",
    )
    active: bool = Field(
        default=True,
        description="Whether this pattern is active.",
    )
    ci_type: str = Field(
        default="",
        description="Target CI type (e.g., 'cmdb_ci_linux_server', 'cmdb_ci_win_server').",
    )
    criteria: str = Field(
        default="",
        description="Classification criteria / matching rules (JSON or encoded query).",
    )
    description: str = Field(
        default="",
        description="Human-readable description of what this pattern matches.",
    )

    @field_validator("active", mode="before")
    @classmethod
    def _coerce_active(cls, v: Any) -> bool:
        """Coerce active field from ServiceNow string to bool."""
        return _coerce_bool(v)


# ---------------------------------------------------------------------------
# DiscoveryLog -- discovery_log table
# ---------------------------------------------------------------------------


class DiscoveryLog(SnowBaseModel):
    """Represents a record from the ``discovery_log`` table.

    Contains log entries generated during a discovery scan, including
    informational messages, warnings, and errors.  Each entry links back
    to a ``discovery_status`` record via the ``status`` field.
    """

    status: str = Field(
        default="",
        description="Reference to the discovery_status record (sys_id).",
    )
    level: str = Field(
        default="",
        description="Log level (e.g., 'Info', 'Warning', 'Error').",
    )
    message: str = Field(
        default="",
        description="Log message text.",
    )
    source: str = Field(
        default="",
        description="Source component that generated the log entry.",
    )
    created_on: datetime | None = Field(
        default=None,
        description="Timestamp when the log entry was created.",
    )

    @field_validator("created_on", mode="before")
    @classmethod
    def _parse_created_on(cls, v: Any) -> datetime | None:
        """Parse ServiceNow datetime string for created_on."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return parse_snow_datetime(v)
        return None


# ---------------------------------------------------------------------------
# DiscoveryHealthSummary -- custom analytics model
# ---------------------------------------------------------------------------


class DiscoveryHealthSummary(BaseModel):
    """Aggregated health metrics for ServiceNow Discovery.

    This is a custom model used by the ``get_discovery_health`` tool.  It
    does not map to a ServiceNow table -- instead it is computed from
    data aggregated across ``discovery_status``, ``discovery_schedule``,
    ``discovery_credential``, and ``discovery_range`` tables.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    total_scans: int = Field(
        default=0,
        description="Total number of discovery scans in the analysis period.",
    )
    successful: int = Field(
        default=0,
        description="Number of scans that completed successfully.",
    )
    failed: int = Field(
        default=0,
        description="Number of scans that ended with errors.",
    )
    cancelled: int = Field(
        default=0,
        description="Number of scans that were cancelled.",
    )
    error_rate: float = Field(
        default=0.0,
        description="Percentage of scans that failed (0.0 to 100.0).",
    )
    avg_duration_seconds: float = Field(
        default=0.0,
        description="Average scan duration in seconds.",
    )
    total_cis_discovered: int = Field(
        default=0,
        description="Total CIs discovered across all scans in the period.",
    )
    top_errors: list[ErrorCount] = Field(
        default_factory=list,
        description="Most frequently occurring errors, sorted by count descending.",
    )
    health_score: int = Field(
        default=100,
        description="Overall health score (0-100): healthy > 80, warning 50-80, critical < 50.",
    )
    period: str = Field(
        default="week",
        description="Analysis period ('day', 'week', 'month').",
    )
    computed_at: datetime | None = Field(
        default=None,
        description="Timestamp when this summary was computed.",
    )

    @field_validator("error_rate")
    @classmethod
    def _clamp_error_rate(cls, v: float) -> float:
        """Ensure error_rate is between 0.0 and 100.0."""
        return max(0.0, min(100.0, v))

    @field_validator("health_score")
    @classmethod
    def _clamp_health_score(cls, v: int) -> int:
        """Ensure health_score is between 0 and 100."""
        return max(0, min(100, v))


class ErrorCount(BaseModel):
    """A single error type with its occurrence count.

    Used in ``DiscoveryHealthSummary.top_errors`` to report the most
    common error messages observed during discovery scans.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    message: str = Field(
        description="The error message or error category.",
    )
    count: int = Field(
        description="Number of times this error occurred.",
    )
    level: str = Field(
        default="Error",
        description="Log level of the error (e.g., 'Error', 'Warning').",
    )


# ---------------------------------------------------------------------------
# Update DiscoveryHealthSummary to use ErrorCount (forward reference resolved)
# ---------------------------------------------------------------------------
# Pydantic v2 handles forward references via model_rebuild().
DiscoveryHealthSummary.model_rebuild()


# ---------------------------------------------------------------------------
# DiscoveryCompareResult -- custom comparison model
# ---------------------------------------------------------------------------


class CIDelta(BaseModel):
    """A single CI that changed between two discovery scans.

    Used in ``DiscoveryCompareResult`` to represent CIs that were added,
    removed, or changed between two compared scans.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    sys_id: str = Field(
        description="sys_id of the configuration item.",
    )
    name: str = Field(
        default="",
        description="Display name of the CI.",
    )
    ci_type: str = Field(
        default="",
        description="CI class name (e.g., 'cmdb_ci_linux_server').",
    )
    change_type: str = Field(
        default="",
        description="Type of change: 'added', 'removed', or 'changed'.",
    )
    details: str = Field(
        default="",
        description="Additional details about the change.",
    )


class ErrorDelta(BaseModel):
    """An error difference between two discovery scans.

    Used in ``DiscoveryCompareResult`` to represent errors that are new,
    resolved, or persistent between two compared scans.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    message: str = Field(
        description="Error message text.",
    )
    status: str = Field(
        default="",
        description="Delta status: 'new', 'resolved', or 'persistent'.",
    )
    count_a: int = Field(
        default=0,
        description="Occurrence count in scan A.",
    )
    count_b: int = Field(
        default=0,
        description="Occurrence count in scan B.",
    )


class DiscoveryCompareResult(BaseModel):
    """Comparison results between two ServiceNow Discovery scans.

    This is a custom model used by the ``compare_discovery_runs`` tool.
    It does not map to a ServiceNow table.  Populated by comparing
    ``discovery_status`` and ``discovery_log`` data from two different
    scan runs.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    scan_a_sys_id: str = Field(
        description="sys_id of the first (baseline) scan.",
    )
    scan_b_sys_id: str = Field(
        description="sys_id of the second (comparison) scan.",
    )
    scan_a_state: str = Field(
        default="",
        description="State of scan A (e.g., 'Completed').",
    )
    scan_b_state: str = Field(
        default="",
        description="State of scan B (e.g., 'Completed').",
    )
    delta_ci_count: int = Field(
        default=0,
        description="Change in total CI count (scan B - scan A).",
    )
    delta_error_count: int = Field(
        default=0,
        description="Change in total error count (scan B - scan A).",
    )
    delta_duration_seconds: float = Field(
        default=0.0,
        description="Change in scan duration in seconds (scan B - scan A).",
    )
    cis_added: list[CIDelta] = Field(
        default_factory=list,
        description="CIs found in scan B but not in scan A.",
    )
    cis_removed: list[CIDelta] = Field(
        default_factory=list,
        description="CIs found in scan A but not in scan B.",
    )
    cis_changed: list[CIDelta] = Field(
        default_factory=list,
        description="CIs found in both scans but with changed attributes.",
    )
    errors_new: list[ErrorDelta] = Field(
        default_factory=list,
        description="Errors present in scan B but not in scan A.",
    )
    errors_resolved: list[ErrorDelta] = Field(
        default_factory=list,
        description="Errors present in scan A but resolved in scan B.",
    )
    errors_persistent: list[ErrorDelta] = Field(
        default_factory=list,
        description="Errors present in both scans.",
    )
    compared_at: datetime | None = Field(
        default=None,
        description="Timestamp when this comparison was computed.",
    )
