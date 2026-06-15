"""Smoke tests: verify retro_mester is importable and CLI --help exits 0."""

from __future__ import annotations


def test_import_retro_mester() -> None:
    """Assert that ``import retro_mester`` succeeds without error."""
    import retro_mester  # noqa: F401


def test_version() -> None:
    """Assert that ``retro_mester.__version__`` equals '0.1.0'."""
    import retro_mester

    assert retro_mester.__version__ == "0.1.0"


def test_cli_run_help_exits_zero() -> None:
    """Assert that ``retro-mester run --help`` exits 0 via the app() entrypoint."""
    from retro_mester.cli.main import app

    exit_code = app(["run", "--help"])
    assert exit_code == 0, f"Expected exit 0 from --help, got {exit_code}"


def test_cli_run_missing_data_exits_2() -> None:
    """Assert that ``retro-mester run`` with missing data root exits 2.

    The stub is replaced by the real pipeline (T029).  When no data directory
    exists the pipeline encounters missing input files → InputError → exit 2.
    """
    from retro_mester.cli.main import app

    exit_code = app(
        ["run", "--semester", "2026-1", "--course", "anatomy", "--data-root", "/nonexistent/data"]
    )
    assert exit_code == 2, f"Expected exit 2 for missing data, got {exit_code}"


def test_exit_code_constants() -> None:
    """Assert exit-code constants have the mandated values (0/2/3/5)."""
    from retro_mester.cli.main import (
        EXIT_INPUT_ERROR,
        EXIT_INTEGRITY_ERROR,
        EXIT_LLM_REQUIRED_FAIL,
        EXIT_SUCCESS,
    )

    assert EXIT_SUCCESS == 0
    assert EXIT_INPUT_ERROR == 2
    assert EXIT_INTEGRITY_ERROR == 3
    assert EXIT_LLM_REQUIRED_FAIL == 5
