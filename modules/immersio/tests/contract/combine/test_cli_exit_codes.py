"""Contract test — combine cli exit codes (T045, US5).

Verifies FR-024 exit code mapping per
``contracts/cli_combine.md`` §"Exit codes".
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from immersio.combine import cli


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location(
        "build_silver_phase3", builder_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _argv(
    *,
    silver_dir: Path,
    gold_dir: Path,
    semester: str = "2026-1",
    course: str = "anatomy",
    include_cluster: bool = False,
) -> list[str]:
    args = [
        "--semester",
        semester,
        "--course",
        course,
        "--silver-dir",
        str(silver_dir),
        "--gold-dir",
        str(gold_dir),
    ]
    if include_cluster:
        args.append("--include-cluster")
    return args


# ----------------------------------------------------------------------
# Exit 0 — success
# ----------------------------------------------------------------------


def test_exit_0_on_happy_path(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_exit0")
    builder.build_silver_phase3_minimal(tmp)
    rc = cli.main(_argv(silver_dir=tmp / "silver", gold_dir=tmp / "gold"))
    assert rc == cli.EXIT_OK == 0


# ----------------------------------------------------------------------
# Exit 1 — input validation failure (regex mismatch)
# ----------------------------------------------------------------------


def test_exit_1_invalid_semester(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_exit1_sem")
    builder.build_silver_phase3_minimal(tmp)
    rc = cli.main(
        _argv(
            silver_dir=tmp / "silver",
            gold_dir=tmp / "gold",
            semester="2026/1",  # wrong separator
        )
    )
    assert rc == cli.EXIT_INPUT_VALIDATION == 1
    err = capsys.readouterr().err
    assert "ERROR [combine.input]: invalid-semester" in err


def test_exit_1_invalid_course(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_exit1_course")
    builder.build_silver_phase3_minimal(tmp)
    rc = cli.main(
        _argv(
            silver_dir=tmp / "silver",
            gold_dir=tmp / "gold",
            course="Anatomy",  # uppercase rejected
        )
    )
    assert rc == cli.EXIT_INPUT_VALIDATION
    err = capsys.readouterr().err
    assert "invalid-course" in err


def test_exit_1_missing_required_argv(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """argparse missing required → mapped to exit 1."""
    rc = cli.main([])
    assert rc == cli.EXIT_INPUT_VALIDATION


# ----------------------------------------------------------------------
# Exit 3 — required input file missing
# ----------------------------------------------------------------------


def test_exit_3_missing_factor_scores(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_exit3_fs")
    builder.build_silver_phase3_missing_factor_scores(tmp)
    rc = cli.main(_argv(silver_dir=tmp / "silver", gold_dir=tmp / "gold"))
    assert rc == cli.EXIT_INPUT_FILE_MISSING == 3
    err = capsys.readouterr().err
    assert "ERROR [combine.input]: missing-file" in err
    assert "factor_scores.parquet" in err


def test_exit_3_missing_silver_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Silver dir 자체가 없으면 첫 입력 file 미존재로 exit 3."""
    rc = cli.main(
        _argv(silver_dir=tmp_path / "no-silver", gold_dir=tmp_path / "gold")
    )
    assert rc == cli.EXIT_INPUT_FILE_MISSING


# ----------------------------------------------------------------------
# stderr format compliance
# ----------------------------------------------------------------------


def test_stderr_format_compliance(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """T046 — `ERROR [combine.<phase>]: <category> — <message>` 형식."""
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_stderr_fmt")
    builder.build_silver_phase3_missing_factor_scores(tmp)
    cli.main(_argv(silver_dir=tmp / "silver", gold_dir=tmp / "gold"))
    err = capsys.readouterr().err
    import re

    pattern = re.compile(r"^ERROR \[combine\.[a-z]+\]: [\w-]+ — .+$", re.MULTILINE)
    assert pattern.search(err), f"stderr does not match format: {err!r}"


# ----------------------------------------------------------------------
# No partial outputs on fail-fast (Constitution V)
# ----------------------------------------------------------------------


def test_no_silver_parquet_on_exit_3(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Constitution V: 실패 시 silver 산출 0건."""
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_no_partial")
    builder.build_silver_phase3_missing_factor_scores(tmp)
    cli.main(_argv(silver_dir=tmp / "silver", gold_dir=tmp / "gold"))
    silver_target = (
        tmp
        / "silver"
        / "immersio"
        / "2026-1-anatomy"
        / "진단×시험결합.parquet"
    )
    assert not silver_target.exists()


def test_no_gold_artefacts_on_exit_3(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_no_partial_gold")
    builder.build_silver_phase3_missing_factor_scores(tmp)
    cli.main(_argv(silver_dir=tmp / "silver", gold_dir=tmp / "gold"))
    gold_target = tmp / "gold" / "immersio" / "2026-1-anatomy"
    assert not gold_target.exists() or not any(gold_target.iterdir())


# ----------------------------------------------------------------------
# US2 wiring via --include-cluster
# ----------------------------------------------------------------------


def test_include_cluster_flag_propagates(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("cli_us2")
    builder.build_silver_phase3_minimal(tmp)
    rc = cli.main(
        _argv(
            silver_dir=tmp / "silver",
            gold_dir=tmp / "gold",
            include_cluster=True,
        )
    )
    assert rc == cli.EXIT_OK
    fig5 = (
        tmp
        / "gold"
        / "immersio"
        / "2026-1-anatomy"
        / "figs"
        / "fig5_cluster_boxplot.png"
    )
    assert fig5.exists()
