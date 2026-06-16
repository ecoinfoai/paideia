"""Test — `immersio combine` subcommand wire-in via cli/main.py (T048).

INTEGRATION (RULE 4): cli/main.py app() dispatches `combine` to
combine.cli.main with the right argv shape.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location("build_silver_phase3", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_combine_subcommand_dispatch_returns_zero(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """`immersio combine ...` end-to-end via cli/main.app()."""
    from immersio.cli.main import app

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_main_combine")
    builder.build_silver_phase3_minimal(tmp)
    rc = app(
        [
            "combine",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--silver-dir",
            str(tmp / "silver"),
            "--gold-dir",
            str(tmp / "gold"),
        ]
    )
    assert rc == 0


def test_combine_subcommand_with_include_cluster_flag(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    from immersio.cli.main import app

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_main_combine_us2")
    builder.build_silver_phase3_minimal(tmp)
    rc = app(
        [
            "combine",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--silver-dir",
            str(tmp / "silver"),
            "--gold-dir",
            str(tmp / "gold"),
            "--include-cluster",
        ]
    )
    assert rc == 0
    fig5 = tmp / "gold" / "immersio" / "2026-1-anatomy" / "figs" / "fig5_cluster_boxplot.png"
    assert fig5.exists()


def test_combine_subcommand_invalid_semester_returns_one(
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from immersio.cli.main import app

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_main_combine_bad")
    builder.build_silver_phase3_minimal(tmp)
    rc = app(
        [
            "combine",
            "--semester",
            "2026/1",
            "--course",
            "anatomy",
            "--silver-dir",
            str(tmp / "silver"),
            "--gold-dir",
            str(tmp / "gold"),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid-semester" in err
