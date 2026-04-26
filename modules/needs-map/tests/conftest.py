"""Shared pytest fixtures for needs-map module tests.

Determinism guard: matplotlib MPLCONFIGDIR is pinned to a fixture-local temp dir so
that font cache differences between OS environments do not bleed into PDF byte-equal
checks (developer R4 mitigation, FR-022).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_matplotlib_cache(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Pin MPLCONFIGDIR so font/render cache is deterministic across runs."""
    cache_dir = tmp_path_factory.mktemp("mplconfig")
    os.environ["MPLCONFIGDIR"] = str(cache_dir)


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    """Filesystem path to the bundled tests/fixtures/ tree."""
    return Path(__file__).parent / "fixtures"
