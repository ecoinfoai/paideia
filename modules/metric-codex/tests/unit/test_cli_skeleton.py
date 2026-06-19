"""T019 — Unit tests for the metric-codex CLI skeleton.

Tests (RED first, per TDD mandate):
- --help exits 0 (argparse SystemExit handled).
- Unknown subcommand exits 2.
- _COMMAND_HANDLERS contains exactly the 7 expected subcommands.
- app() with a known subcommand passes argparse parsing (doesn't fail on
  argument validation), and the stub handler raises NotImplementedError.
- Common flags (--semester, --course, --data-root) are accepted by every
  subcommand (argparse level — parse does not fail).
"""

from __future__ import annotations

import pytest

_ALL_SUBCOMMANDS = ["ingest", "query", "dry-run", "generate", "distribute", "verify", "build"]


# ---------------------------------------------------------------------------
# --help exits 0
# ---------------------------------------------------------------------------


def test_help_exits_zero() -> None:
    """app(['--help']) must exit 0 (argparse raises SystemExit(0))."""
    from metric_codex.cli.main import app

    result = app(["--help"])
    assert result == 0


# ---------------------------------------------------------------------------
# Unknown subcommand exits 2
# ---------------------------------------------------------------------------


def test_unknown_subcommand_exits_two() -> None:
    """Unrecognised subcommand → exit code 2."""
    from metric_codex.cli.main import app

    result = app(["nonexistent-command", "--semester", "2026-1", "--course", "anatomy"])
    assert result == 2


# ---------------------------------------------------------------------------
# _COMMAND_HANDLERS contains all 7 subcommands
# ---------------------------------------------------------------------------


def test_command_handlers_contains_all_subcommands() -> None:
    """_COMMAND_HANDLERS dispatch map contains exactly the 7 required subcommands."""
    from metric_codex.cli.main import _COMMAND_HANDLERS

    for cmd in _ALL_SUBCOMMANDS:
        assert cmd in _COMMAND_HANDLERS, f"Missing subcommand in _COMMAND_HANDLERS: {cmd!r}"


def test_command_handlers_no_extra_keys() -> None:
    """_COMMAND_HANDLERS contains no unexpected extra subcommands."""
    from metric_codex.cli.main import _COMMAND_HANDLERS

    extra = set(_COMMAND_HANDLERS.keys()) - set(_ALL_SUBCOMMANDS)
    assert not extra, f"Unexpected keys in _COMMAND_HANDLERS: {extra}"


# ---------------------------------------------------------------------------
# Common flags accepted on all subcommands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", _ALL_SUBCOMMANDS)
def test_common_flags_parse_without_error(subcommand: str) -> None:
    """--semester, --course, --data-root are accepted by every subcommand."""
    from metric_codex.cli.main import _build_parser

    parser = _build_parser()
    # Should not raise; NotImplementedError from the handler is fine.
    try:
        args = parser.parse_args(
            [subcommand, "--semester", "2026-1", "--course", "anatomy", "--data-root", "data/"]
        )
    except SystemExit as exc:
        pytest.fail(f"argparse exited {exc.code} for '{subcommand}' with common flags")

    assert args.semester == "2026-1"
    assert args.course == "anatomy"


# ---------------------------------------------------------------------------
# Stub handlers raise NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", _ALL_SUBCOMMANDS)
def test_stub_handlers_raise_not_implemented(subcommand: str) -> None:
    """Each stub handler raises NotImplementedError (wired in later units)."""
    from metric_codex.cli.main import _COMMAND_HANDLERS, _build_parser

    parser = _build_parser()
    args = parser.parse_args([subcommand, "--semester", "2026-1", "--course", "anatomy"])
    handler = _COMMAND_HANDLERS[subcommand]
    with pytest.raises(NotImplementedError):
        handler(args)


# ---------------------------------------------------------------------------
# Subcommand --help exits 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", _ALL_SUBCOMMANDS)
def test_subcommand_help_exits_zero(subcommand: str) -> None:
    """Each subcommand --help exits 0."""
    from metric_codex.cli.main import app

    result = app([subcommand, "--help"])
    assert result == 0


# ---------------------------------------------------------------------------
# Stub handler via app() returns 3 (does not raise NotImplementedError)
# ---------------------------------------------------------------------------


def test_app_stub_handler_returns_three() -> None:
    """app() catches a stub handler's NotImplementedError and returns exit 3.

    Wiring units will replace each stub handler with real logic and adjust
    this expectation as they go.
    """
    from metric_codex.cli.main import app

    result = app(["ingest", "--semester", "2026-1", "--course", "x"])
    assert result == 3
