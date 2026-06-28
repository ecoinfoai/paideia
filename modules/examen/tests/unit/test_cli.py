"""Unit tests for examen.cli.main — T016.

TDD: failing tests written BEFORE implementation.

Covers:
- --help works for all 6 subcommands.
- Missing --semester / --course / --blueprint returns exit code 2.
- Bad blueprint.yaml (invalid content) returns exit code 2.
- CLI entry point (app) is importable and callable.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke(argv: list[str]) -> int:
    """Invoke the examen CLI app with the given argv, returning the exit code."""
    from examen.cli.main import app

    return app(argv)


def _write_valid_blueprint(tmp_path: Path, name: str = "blueprint.yaml") -> Path:
    content = textwrap.dedent("""\
        semester: "2026-1"
        course_slug: "anatomy"
        exam_name: "2026-1학기 기말고사"
        total_items: 48
        chapters:
          - "8장. 호흡계통"
          - "9장. 근육계통"
        difficulty_targets:
          easy: 0.45
          medium: 0.35
          hard: 0.20
        source_mix:
          formative: 12
          quiz: 15
          textbook: 21
        answer_key_balance: true
    """)
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _write_invalid_blueprint(tmp_path: Path, name: str = "bad_blueprint.yaml") -> Path:
    """Write a blueprint.yaml with total_items out of range (triggers exit 2)."""
    content = textwrap.dedent("""\
        semester: "2026-1"
        course_slug: "anatomy"
        exam_name: "2026-1학기 기말고사"
        total_items: 5
        chapters:
          - "8장"
        difficulty_targets:
          easy: 0.45
          medium: 0.35
          hard: 0.20
        source_mix:
          formative: 2
          quiz: 2
          textbook: 1
        answer_key_balance: true
    """)
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Import / help tests
# ---------------------------------------------------------------------------


class TestCLIImport:
    def test_app_is_importable(self) -> None:
        """examen.cli.main.app must be importable."""
        from examen.cli.main import app  # noqa: F401


class TestHelpWorks:
    """--help must work (exit 0) for the main command and all 6 subcommands."""

    def test_top_level_help(self) -> None:
        """examen --help exits 0 (app returns 0, not raises)."""
        code = _invoke(["--help"])
        assert code == 0

    @pytest.mark.parametrize("sub", ["ingest", "plan", "dry-run", "generate", "verify", "build"])
    def test_subcommand_help(self, sub: str) -> None:
        """examen <sub> --help returns 0 for every subcommand."""
        code = _invoke([sub, "--help"])
        assert code == 0


# ---------------------------------------------------------------------------
# Missing required options → exit 2
# ---------------------------------------------------------------------------

_ALL_SUBCOMMANDS = ["ingest", "plan", "dry-run", "generate", "verify", "build"]


class TestMissingRequiredOptions:
    @pytest.mark.parametrize("sub", _ALL_SUBCOMMANDS)
    def test_missing_semester_returns_exit2(self, sub: str) -> None:
        """Missing --semester on every subcommand should exit 2."""
        code = _invoke([sub, "--course", "anatomy"])
        assert code == 2

    @pytest.mark.parametrize("sub", _ALL_SUBCOMMANDS)
    def test_missing_course_returns_exit2(self, sub: str) -> None:
        """Missing --course on every subcommand should exit 2."""
        code = _invoke([sub, "--semester", "2026-1"])
        assert code == 2


# ---------------------------------------------------------------------------
# Bad blueprint → exit 2
# ---------------------------------------------------------------------------


class TestBlueprintValidation:
    def test_explicit_invalid_blueprint_returns_exit2(self, tmp_path: Path) -> None:
        """Explicit --blueprint pointing to an invalid YAML returns exit 2."""
        bad_bp = _write_invalid_blueprint(tmp_path)
        code = _invoke(
            [
                "ingest",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--blueprint",
                str(bad_bp),
            ]
        )
        assert code == 2

    def test_explicit_missing_blueprint_returns_exit2(self, tmp_path: Path) -> None:
        """Explicit --blueprint pointing to a non-existent file returns exit 2."""
        missing = tmp_path / "no_such_blueprint.yaml"
        code = _invoke(
            [
                "ingest",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--blueprint",
                str(missing),
            ]
        )
        assert code == 2

    def test_valid_blueprint_does_not_return_exit2(self, tmp_path: Path) -> None:
        """With a valid blueprint, ingest should not exit 2 for validation reasons.

        It may exit non-zero for other reasons (bronze data missing, etc.) but
        NOT for blueprint validation failure.
        """
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke(
            [
                "ingest",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--blueprint",
                str(valid_bp),
            ]
        )
        # Should NOT be exit 2 (validation error); may be 0 or 3 depending
        # on whether bronze data exists, but blueprint itself is valid.
        assert code != 2


# ---------------------------------------------------------------------------
# Backend option — only accepted values
# ---------------------------------------------------------------------------


class TestBackendOption:
    def test_generate_accepts_subscription_backend(self, tmp_path: Path) -> None:
        """--backend subscription is accepted (even if generate is a stub)."""
        valid_bp = _write_valid_blueprint(tmp_path)
        # We pass a valid blueprint; the command may fail for other reasons
        # but should NOT exit 2 for unknown backend value.
        code = _invoke(
            [
                "generate",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--backend",
                "subscription",
                "--blueprint",
                str(valid_bp),
            ]
        )
        # Exit 2 = validation failure; we only check it's not a config error.
        assert code != 2

    def test_generate_accepts_api_backend(self, tmp_path: Path) -> None:
        """--backend api is accepted (even if generate is a stub)."""
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke(
            [
                "generate",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--backend",
                "api",
                "--blueprint",
                str(valid_bp),
            ]
        )
        assert code != 2


# ---------------------------------------------------------------------------
# no-emphasis flag
# ---------------------------------------------------------------------------


class TestNoEmphasisFlag:
    def test_generate_accepts_no_emphasis(self, tmp_path: Path) -> None:
        """--no-emphasis flag is accepted (even if generate is a stub)."""
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke(
            [
                "generate",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--no-emphasis",
                "--blueprint",
                str(valid_bp),
            ]
        )
        assert code != 2


# ---------------------------------------------------------------------------
# Pipeline exception trap → exit 3 / 4
# ---------------------------------------------------------------------------


class TestPipelineExceptionTrap:
    """app() must map pipeline exceptions to exit codes 3/4 now (T016).

    The trap lives in app() so future pipeline wiring inherits it; these
    tests inject a handler that raises to exercise the trap directly.
    """

    def test_backend_unreachable_returns_exit4(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A handler raising BackendUnreachableError → app returns 4."""
        import examen.cli.main as cli_main
        from examen.generate.backend import BackendUnreachableError

        def _boom(_args: object) -> int:
            raise BackendUnreachableError("api unreachable")

        monkeypatch.setitem(cli_main._COMMAND_HANDLERS, "generate", _boom)
        code = _invoke(["generate", "--semester", "2026-1", "--course", "anatomy"])
        assert code == 4

    def test_runtime_error_returns_exit3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A handler raising RuntimeError → app returns 3."""
        import examen.cli.main as cli_main

        def _boom(_args: object) -> int:
            raise RuntimeError("response not yet provided")

        monkeypatch.setitem(cli_main._COMMAND_HANDLERS, "generate", _boom)
        code = _invoke(["generate", "--semester", "2026-1", "--course", "anatomy"])
        assert code == 3


# ---------------------------------------------------------------------------
# build: pipeline ValueError → exit 2 (config/coverage fault, NOT a RuntimeError)
# ---------------------------------------------------------------------------


def _write_valid_curriculum_map(tmp_path: Path, name: str = "curriculum_map.yaml") -> Path:
    """Write a valid curriculum_map.yaml matching the valid blueprint chapters."""
    content = textwrap.dedent("""\
        semester: "2026-1"
        course_slug: "anatomy"
        entries:
          - week: 1
            chapter: "8장. 호흡계통"
            chapter_no: 8
            subtopic: null
            sections: ["1. 기도", "2. 폐"]
          - week: 2
            chapter: "9장. 근육계통"
            chapter_no: 9
            subtopic: null
            sections: ["1. 골격근", "2. 평활근"]
    """)
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestBuildPipelineValueError:
    """A ValueError raised inside build_exam must map to exit 2, not escape to 1.

    A bare ValueError is NOT a RuntimeError, so the app() trap would otherwise
    let it bubble up to exit 1, violating the CLI contract (config/coverage
    faults are exit 2).
    """

    def test_build_pipeline_value_error_returns_exit2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """build_exam raising ValueError (e.g. coverage gap) → CLI exit 2."""
        import examen.cli.main as cli_main

        valid_bp = _write_valid_blueprint(tmp_path)
        valid_cm = _write_valid_curriculum_map(tmp_path)

        def _boom(**_kwargs: object) -> tuple[list, Path]:
            raise ValueError("build_exam: slot 'slot-001' chapter_no=99 has no chapter data")

        # Patch build_exam where _run_build imports it (examen.pipeline).
        import examen.pipeline as pipeline_mod

        monkeypatch.setattr(pipeline_mod, "build_exam", _boom)
        # _run_build does `from examen.pipeline import build_exam`, so patching
        # the module attribute is sufficient (import happens at call time).

        code = cli_main.app(
            [
                "build",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--blueprint",
                str(valid_bp),
                "--curriculum-map",
                str(valid_cm),
            ]
        )
        assert code == 2


# ---------------------------------------------------------------------------
# --semester / --course boundary validation (INJ-01) → exit 2 before path use
# ---------------------------------------------------------------------------


class TestSemesterCourseValidation:
    """Malformed --semester / --course must be rejected at the CLI boundary.

    examen interpolates these values into filesystem paths (output/paths.py
    builds ``f"{semester}-{course_slug}"``). A path-traversal payload such as
    ``../../etc`` would otherwise reach ``mkdir``/``write_text``. Validation
    must happen BEFORE any path is constructed (security finding INJ-01).
    """

    def test_e2_traversal_semester_returns_exit2(self) -> None:
        """E2 — '../../etc' as --semester is rejected with exit 2."""
        code = _invoke(["ingest", "--semester", "../../etc", "--course", "anatomy"])
        assert code == 2

    def test_e3_traversal_course_creates_no_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E3 — '../passwd' as --course exits 2 and creates no filesystem dirs."""
        # Default data root is the relative ``data/`` dir, resolved against cwd.
        monkeypatch.chdir(tmp_path)
        code = _invoke(["ingest", "--semester", "2026-1", "--course", "../passwd"])
        assert code == 2
        # No path was constructed → nothing created under (or escaping) the root.
        assert not (tmp_path / "data").exists()
        assert not (tmp_path.parent / "passwd").exists()

    def test_e4_semester_with_slash_returns_exit2(self) -> None:
        """E4 — a slash in --semester is rejected with exit 2."""
        code = _invoke(["ingest", "--semester", "2026-1/x", "--course", "anatomy"])
        assert code == 2

    def test_e5_bad_term_char_returns_exit2(self) -> None:
        """E5 — an out-of-range term ('99') in --semester is rejected (exit 2)."""
        code = _invoke(["ingest", "--semester", "2026-99", "--course", "anatomy"])
        assert code == 2

    def test_e6_uppercase_course_returns_exit2(self) -> None:
        """E6 — an uppercase --course violates CourseSlug and exits 2."""
        code = _invoke(["ingest", "--semester", "2026-1", "--course", "ANATOMY"])
        assert code == 2

    def test_message_includes_value_and_pattern(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """FR-010 — the located error names the offending value and the pattern."""
        code = _invoke(["ingest", "--semester", "../../etc", "--course", "anatomy"])
        assert code == 2
        err = capsys.readouterr().err
        assert "../../etc" in err
        assert r"^\d{4}-[12SW]$" in err

    def test_e1_valid_args_pass_validation(self, tmp_path: Path) -> None:
        """E1 — valid --semester/--course are NOT rejected as validation errors.

        Reaches normal handling (may exit 0/3 for other reasons, never 2 for
        the semester/course boundary).
        """
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke(
            [
                "ingest",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--blueprint",
                str(valid_bp),
            ]
        )
        assert code != 2
