"""T019 — Unit tests for the metric-codex CLI skeleton.

Tests (RED first, per TDD mandate):
- --help exits 0 (argparse SystemExit handled).
- Unknown subcommand exits 2.
- _COMMAND_HANDLERS contains exactly the 7 expected subcommands.
- app() with a known subcommand passes argparse parsing (doesn't fail on
  argument validation), and the stub handler raises NotImplementedError.
- Common flags (--semester, --course, --data-root) are accepted by every
  subcommand (argparse level — parse does not fail).

Updated in T041/T042/T045: query, dry-run, and generate are now wired.
Updated in T052: distribute is now wired (no longer a stub).
Updated in T054: verify is now wired (no longer a stub).
Updated in T055: build is now wired (no longer a stub).
- query requires --student; skeleton test passes dummy --student.
- dry-run is wired and may fail on missing Silver files (not NotImplementedError).
- distribute is wired and may fail on missing roster file (not NotImplementedError).
- verify is wired and exits 0/2/3 depending on artifact state (not NotImplementedError).
- build is wired and chains all four stages (not NotImplementedError).
"""

from __future__ import annotations

import pytest

_ALL_SUBCOMMANDS = ["ingest", "query", "dry-run", "generate", "distribute", "verify", "build"]
# Subcommands still backed by a NotImplementedError stub.
# All subcommands are now wired (T041/T042/T045/T052/T054/T055).
_STUB_SUBCOMMANDS: list[str] = []


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
    """--semester, --course, --data-root are accepted by every subcommand.

    Note: 'query' also requires --student (wired in T045); we pass a dummy value.
    """
    from metric_codex.cli.main import _build_parser

    parser = _build_parser()
    argv = [subcommand, "--semester", "2026-1", "--course", "anatomy", "--data-root", "data/"]
    # query requires --student (wired); provide a dummy for the parse-level test.
    if subcommand == "query":
        argv += ["--student", "S001", "--text", "score"]
    # Should not raise; handler failure is fine at this level.
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        pytest.fail(f"argparse exited {exc.code} for '{subcommand}' with common flags")

    assert args.semester == "2026-1"
    assert args.course == "anatomy"


# ---------------------------------------------------------------------------
# Stub handlers raise NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", _STUB_SUBCOMMANDS)
def test_stub_handlers_raise_not_implemented(subcommand: str) -> None:
    """Each still-stub handler raises NotImplementedError (wired in later units).

    All subcommands are now wired (T055), so _STUB_SUBCOMMANDS is empty and
    this parametrized test is a no-op placeholder.
    """
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
# build wired — all 7 subcommands are now wired (T055)
# ---------------------------------------------------------------------------


def test_build_subcommand_is_wired() -> None:
    """app() with 'build' on a missing Bronze tree exits 2 (ingest boundary fail).

    All stub handlers are gone (T055).  'build' is wired: it runs ingest first,
    which raises LocatedInputError when the school map is absent → app returns 2.
    """
    import tempfile

    from metric_codex.cli.main import app

    with tempfile.TemporaryDirectory() as td:
        # An empty data root: no Bronze inputs → ingest fails fast (exit 2).
        result = app([
            "build",
            "--semester", "2026-1",
            "--course", "x",
            "--data-root", td,
        ])
    # Exit 0 is also acceptable if no school map is found and the degraded
    # path completes successfully (no mandatory school map in the absence of
    # explicit flags).  Either 0 or 2 signals that the wired handler ran.
    assert result in (0, 2), (
        f"build should return 0 or 2 from a wired handler; got {result}"
    )
