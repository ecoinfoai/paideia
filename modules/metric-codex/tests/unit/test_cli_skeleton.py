"""T019 — Unit tests for the metric-codex CLI skeleton.

Tests (RED first, per TDD mandate):
- --help exits 0 (argparse SystemExit handled).
- Unknown subcommand exits 2.
- _COMMAND_HANDLERS contains exactly the 7 expected subcommands.
- app() with a known subcommand passes argparse parsing (doesn't fail on
  argument validation).
- Common flags (--semester, --course, --data-root) are accepted by every
  subcommand (argparse level — parse does not fail).

Updated in T041/T042/T045: query, dry-run, and generate are now wired.
Updated in T052: distribute is now wired (no longer a stub).
Updated in T054: verify is now wired (no longer a stub).
Updated in T055: build is now wired (no longer a stub).
Updated in T069: removed the no-op stub-handler test — every subcommand is
wired, so no handler raises NotImplementedError and the dead app() handler
was dropped in T065 (SC-010: suite has 0 skips).
- query requires --student; skeleton test passes dummy --student.
- dry-run is wired and may fail on missing Silver files.
- distribute is wired and may fail on missing roster file.
- verify is wired and exits 0/2/3 depending on artifact state.
- build is wired and chains all four stages.
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
    """app() with 'build' on a valid key but empty Bronze tree exits 0 or 2.

    Updated in T024: the prior test used --course "x" (invalid slug) which now
    exits 2 at the new eager-validation gate (T029 fix).  We use a valid slug
    ("anatomy") so the test exercises the ingest handler, not the slug gate.

    'build' is wired: it runs ingest first. With a valid key but empty Bronze
    tree, ingest degrades (no school map) and continues — it may exit 0 or 2
    depending on whether any Silver is found.  Either signals the handler ran.
    """
    import tempfile

    from metric_codex.cli.main import app

    with tempfile.TemporaryDirectory() as td:
        result = app([
            "build",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--data-root", td,
        ])
    # Both 0 (graceful no-Bronze degrade) and 2 (ingest boundary fail) confirm
    # the handler ran.  3 (pipeline step failure from verify) is also acceptable
    # when generate/distribute succeed on an empty store but verify flags issues.
    assert result in (0, 2, 3), (
        f"build should return 0/2/3 from a wired handler; got {result}"
    )


# ---------------------------------------------------------------------------
# T024 — eager --semester / --course validation gate (US4 / D8)
# ---------------------------------------------------------------------------


class TestEagerSlugSemesterValidation:
    """app() must validate --semester and --course BEFORE any filesystem access.

    T029 GREEN: validated in app() between parse_args and handler dispatch.
    All 7 subcommands share this gate via the common args block.
    """

    def test_invalid_course_slug_exits_two(self, tmp_path: object) -> None:
        """A path-traversal --course string exits 2 with a located message.

        RED: before T029 fix, the bad value is interpolated into a path and
        a stat() call may occur before any validation.
        """
        import tempfile

        from metric_codex.cli.main import app

        with tempfile.TemporaryDirectory() as td:
            result = app([
                "ingest",
                "--semester", "2026-1",
                "--course", "../../tmp/evil",
                "--data-root", td,
            ])
        assert result == 2, (
            f"invalid --course '../../tmp/evil' must exit 2; got {result}"
        )

    def test_invalid_course_slug_no_data_dir_written(self) -> None:
        """Bad --course must not create any file under data_root before exit.

        This is the side-effect-before-validation audit finding (D8).
        """
        import tempfile

        from metric_codex.cli.main import app

        with tempfile.TemporaryDirectory() as td:
            import pathlib

            data_root = pathlib.Path(td) / "data"
            data_root.mkdir()
            app([
                "ingest",
                "--semester", "2026-1",
                "--course", "../../tmp/evil",
                "--data-root", str(data_root),
            ])
            # No file/dir may have been created inside data_root.
            created = list(data_root.rglob("*"))
            assert not created, (
                f"data_root must be untouched on invalid --course; found {created}"
            )

    def test_invalid_semester_exits_two(self) -> None:
        """A non-SemesterCode --semester string exits 2."""
        import tempfile

        from metric_codex.cli.main import app

        with tempfile.TemporaryDirectory() as td:
            result = app([
                "ingest",
                "--semester", "badyear",
                "--course", "anatomy",
                "--data-root", td,
            ])
        assert result == 2, (
            f"invalid --semester 'badyear' must exit 2; got {result}"
        )

    def test_invalid_semester_no_data_dir_written(self) -> None:
        """Bad --semester must not create any file under data_root."""
        import tempfile

        from metric_codex.cli.main import app

        with tempfile.TemporaryDirectory() as td:
            import pathlib

            data_root = pathlib.Path(td) / "data"
            data_root.mkdir()
            app([
                "ingest",
                "--semester", "2026/1",
                "--course", "anatomy",
                "--data-root", str(data_root),
            ])
            created = list(data_root.rglob("*"))
            assert not created, (
                f"data_root must be untouched on invalid --semester; found {created}"
            )

    def test_valid_course_and_semester_pass_gate(self) -> None:
        """A conforming --semester / --course must not be rejected by the gate."""
        import tempfile

        from metric_codex.cli.main import app

        with tempfile.TemporaryDirectory() as td:
            # With no Bronze inputs at all the ingest handler degrades (exit 0)
            # or fails on missing paideia Silver (also 0 or 2) — either is fine.
            # The point is that exit code 2 is NOT caused by the slug/semester gate.
            result = app([
                "ingest",
                "--semester", "2026-1",
                "--course", "anatomy",
                "--data-root", td,
            ])
        # 0 (no Bronze degrade) or 3 (pipeline failure from verify) are valid;
        # we just assert the gate did not reject a good value.
        assert result in (0, 3)  # gate must not reject a valid slug

    def test_single_char_course_slug_exits_two(self) -> None:
        """A 1-char course slug ('x') does not satisfy CourseSlug pattern → exit 2.

        This is the slug previously used by test_build_subcommand_is_wired; after
        T029 the gate now rejects it explicitly at exit 2.
        """
        import tempfile

        from metric_codex.cli.main import app

        with tempfile.TemporaryDirectory() as td:
            result = app([
                "ingest",
                "--semester", "2026-1",
                "--course", "x",
                "--data-root", td,
            ])
        assert result == 2, (
            f"1-char slug 'x' must exit 2 after T029 gate; got {result}"
        )
