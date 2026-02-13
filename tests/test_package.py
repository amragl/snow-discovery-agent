"""Tests for the snow_discovery_agent package structure and metadata."""

from __future__ import annotations


def test_package_is_importable() -> None:
    """Verify the package can be imported."""
    import snow_discovery_agent

    assert snow_discovery_agent is not None


def test_version_is_set() -> None:
    """Verify __version__ is defined and follows semver."""
    from snow_discovery_agent import __version__

    assert __version__ == "0.1.0"
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_author_is_set() -> None:
    """Verify __author__ is defined."""
    from snow_discovery_agent import __author__

    assert __author__ == "amragl"
