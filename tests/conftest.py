"""Shared pytest fixtures for snow-discovery-agent tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests do not leak environment variables.

    Removes ServiceNow-related environment variables so that unit tests
    never accidentally connect to a real instance unless they explicitly
    set the variables they need.
    """
    for key in list(os.environ):
        if key.startswith(("SNOW_", "SERVICENOW_")):
            monkeypatch.delenv(key, raising=False)


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: requires a live ServiceNow instance")
    config.addinivalue_line("markers", "slow: long-running test")
