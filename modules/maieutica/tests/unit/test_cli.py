"""Unit tests for maieutica CLI skeleton — T012.

Tests verify:
- --help exits 0 and lists all subcommands.
- Missing required args (--semester, --course, --week) exit 2.
- Invalid --backend choice exits 2.
- Unknown subcommand exits non-zero.
- Each subcommand with valid common args stubs out and exits 3 (not yet implemented).
"""

from __future__ import annotations

import pytest
from maieutica.cli.main import app

# ---------------------------------------------------------------------------
# Common valid args shared across stub tests
# ---------------------------------------------------------------------------

_COMMON = [
    "--semester", "2026-1",
    "--course", "anatomy-physiology",
    "--week", "3",
]

# ---------------------------------------------------------------------------
# --help tests
# ---------------------------------------------------------------------------


def test_top_level_help_exits_0() -> None:
    """app(['--help']) should exit 0."""
    assert app(["--help"]) == 0


def test_build_subcommand_help_exits_0() -> None:
    """app(['build', '--help']) should exit 0."""
    assert app(["build", "--help"]) == 0


def test_help_text_lists_all_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    """Top-level help output must name all six subcommands."""
    app(["--help"])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    for sub in ("ingest", "plan", "dry-run", "generate", "verify", "build"):
        assert sub in output, f"subcommand '{sub}' missing from help output"


# ---------------------------------------------------------------------------
# Validation failure → exit 2
# ---------------------------------------------------------------------------


def test_missing_semester_exits_2() -> None:
    """Missing --semester should exit 2 (argparse validation failure)."""
    rc = app(["ingest", "--course", "anatomy-physiology", "--week", "3"])
    assert rc == 2


def test_missing_course_exits_2() -> None:
    """Missing --course should exit 2."""
    rc = app(["ingest", "--semester", "2026-1", "--week", "3"])
    assert rc == 2


def test_missing_week_exits_2() -> None:
    """Missing --week should exit 2."""
    rc = app(["ingest", "--semester", "2026-1", "--course", "anatomy-physiology"])
    assert rc == 2


def test_invalid_backend_exits_2() -> None:
    """--backend with invalid choice should exit 2."""
    rc = app(["generate"] + _COMMON + ["--backend", "bogus"])
    assert rc == 2


# ---------------------------------------------------------------------------
# Unknown subcommand → non-zero
# ---------------------------------------------------------------------------


def test_unknown_subcommand_exits_nonzero() -> None:
    """An unknown subcommand must exit non-zero."""
    rc = app(["nonexistent-cmd"] + _COMMON)
    assert rc != 0


# ---------------------------------------------------------------------------
# Stub handlers exit 3 (not yet implemented)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", ["ingest", "plan", "dry-run", "generate", "verify", "build"])
def test_stub_handler_exits_3(subcommand: str) -> None:
    """Each subcommand with valid common args should exit 3 (stub, not implemented)."""
    rc = app([subcommand] + _COMMON)
    assert rc == 3, (
        f"subcommand '{subcommand}': expected exit 3 (stub not implemented), got {rc}"
    )


# ---------------------------------------------------------------------------
# Default backend is 'subscription' (no error for omitting --backend)
# ---------------------------------------------------------------------------


def test_default_backend_accepted() -> None:
    """Omitting --backend should default to 'subscription' and not exit 2."""
    rc = app(["generate"] + _COMMON)
    # stub returns 3; the point is it is NOT 2 (invalid arg)
    assert rc != 2


def test_explicit_backend_api_accepted() -> None:
    """--backend api should be a valid choice."""
    rc = app(["generate"] + _COMMON + ["--backend", "api"])
    assert rc != 2


def test_explicit_backend_subscription_accepted() -> None:
    """--backend subscription should be a valid choice."""
    rc = app(["generate"] + _COMMON + ["--backend", "subscription"])
    assert rc != 2
