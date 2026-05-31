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
        code = _invoke([
            "ingest",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--blueprint", str(bad_bp),
        ])
        assert code == 2

    def test_explicit_missing_blueprint_returns_exit2(self, tmp_path: Path) -> None:
        """Explicit --blueprint pointing to a non-existent file returns exit 2."""
        missing = tmp_path / "no_such_blueprint.yaml"
        code = _invoke([
            "ingest",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--blueprint", str(missing),
        ])
        assert code == 2

    def test_valid_blueprint_does_not_return_exit2(self, tmp_path: Path) -> None:
        """With a valid blueprint, ingest should not exit 2 for validation reasons.

        It may exit non-zero for other reasons (bronze data missing, etc.) but
        NOT for blueprint validation failure.
        """
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke([
            "ingest",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--blueprint", str(valid_bp),
        ])
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
        code = _invoke([
            "generate",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--backend", "subscription",
            "--blueprint", str(valid_bp),
        ])
        # Exit 2 = validation failure; we only check it's not a config error.
        assert code != 2

    def test_generate_accepts_api_backend(self, tmp_path: Path) -> None:
        """--backend api is accepted (even if generate is a stub)."""
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke([
            "generate",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--backend", "api",
            "--blueprint", str(valid_bp),
        ])
        assert code != 2


# ---------------------------------------------------------------------------
# no-emphasis flag
# ---------------------------------------------------------------------------

class TestNoEmphasisFlag:
    def test_generate_accepts_no_emphasis(self, tmp_path: Path) -> None:
        """--no-emphasis flag is accepted (even if generate is a stub)."""
        valid_bp = _write_valid_blueprint(tmp_path)
        code = _invoke([
            "generate",
            "--semester", "2026-1",
            "--course", "anatomy",
            "--no-emphasis",
            "--blueprint", str(valid_bp),
        ])
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
