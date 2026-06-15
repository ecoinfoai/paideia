"""Shared pytest fixtures for retro_mester tests.

Provides tiny in-memory stubs and factory functions for:
- CombinedAnalysisRow-like dicts (immersio combined phase3 output shape)
- ItemStatistics-like dicts (item-level stats used by segment/gaps)
- retro_config dicts (pipeline config structure)

These are lightweight stubs so unit tests have something to import
without touching the filesystem or network.  Integration tests will
build on these factories with richer data.
"""

from __future__ import annotations

import pytest

from tests.fixtures.factories import (
    make_combined_row,
    make_item_statistics,
    make_retro_config,
)


@pytest.fixture()
def minimal_combined_row() -> dict:
    """Return a minimal CombinedAnalysisRow-like dict with defaults.

    Returns:
        Dict matching the expected CombinedAnalysisRow schema stub.
    """
    return make_combined_row()


@pytest.fixture()
def minimal_item_statistics() -> dict:
    """Return a minimal ItemStatistics-like dict with defaults.

    Returns:
        Dict matching the expected ItemStatistics schema stub.
    """
    return make_item_statistics()


@pytest.fixture()
def minimal_retro_config() -> dict:
    """Return a minimal retro_config dict with default settings.

    Returns:
        Dict matching the expected retro pipeline config structure.
    """
    return make_retro_config()
