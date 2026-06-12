"""Unit tests for maieutica CLI skeleton — T012.

Tests verify:
- --help exits 0 and lists all subcommands.
- Missing required args (--semester, --course, --week) exit 2.
- Invalid --backend choice exits 2.
- Unknown subcommand exits non-zero.
- Each subcommand with valid common args but a missing Bronze input exits 2
  (input/config validation fault — no partial output).
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
# Missing Bronze input → exit 2 (input/config validation fault)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand", ["ingest", "plan", "dry-run", "generate", "verify", "build"]
)
def test_missing_input_exits_2(
    subcommand: str, tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subcommand with valid args but no Bronze generation_spec exits 2."""
    # Run from an empty tmp cwd so the Bronze convention path resolves to a
    # nonexistent directory → load_generation_spec raises FileNotFoundError → 2.
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    rc = app([subcommand] + _COMMON)
    assert rc == 2, (
        f"subcommand '{subcommand}': expected exit 2 (missing input), got {rc}"
    )


# ---------------------------------------------------------------------------
# Default backend is 'subscription' (no error for omitting --backend)
# ---------------------------------------------------------------------------


def test_default_backend_is_subscription() -> None:
    """Omitting --backend should parse with the 'subscription' default."""
    from maieutica.cli.main import _build_parser

    args = _build_parser().parse_args(["generate"] + _COMMON)
    assert args.backend == "subscription"


def test_explicit_backend_api_parsed() -> None:
    """--backend api should be a valid, parseable choice."""
    from maieutica.cli.main import _build_parser

    args = _build_parser().parse_args(["generate"] + _COMMON + ["--backend", "api"])
    assert args.backend == "api"


def test_explicit_backend_subscription_parsed() -> None:
    """--backend subscription should be a valid, parseable choice."""
    from maieutica.cli.main import _build_parser

    args = _build_parser().parse_args(
        ["generate"] + _COMMON + ["--backend", "subscription"]
    )
    assert args.backend == "subscription"


# ---------------------------------------------------------------------------
# Exit code 4 — LLM backend unreachable (api mode)
# ---------------------------------------------------------------------------


def test_backend_unreachable_exits_4(monkeypatch: pytest.MonkeyPatch) -> None:
    """A handler raising BackendUnreachableError must map to exit 4."""
    from maieutica.cli import main as cli_main

    def _raise(_args: object) -> int:
        raise cli_main.BackendUnreachableError("api endpoint unreachable")

    monkeypatch.setitem(cli_main._COMMAND_HANDLERS, "generate", _raise)
    assert cli_main.app(["generate"] + _COMMON) == 4
