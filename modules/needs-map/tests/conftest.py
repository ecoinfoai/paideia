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


@pytest.fixture
def assert_owner_only():
    """Return a callable that asserts a path has owner-only permissions.

    Skips when running as root because root bypasses chmod protections,
    making the mode check meaningless.
    """

    def _assert(path: Path) -> None:
        if os.geteuid() == 0:
            pytest.skip("root bypasses chmod 0o600 protection")
        mode = path.stat().st_mode & 0o777
        assert mode & 0o077 == 0, f"expected owner-only, got {oct(mode)}"

    return _assert
