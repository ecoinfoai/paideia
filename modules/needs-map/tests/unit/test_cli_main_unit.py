"""In-process unit tests for cli/main.py (T111 coverage boost).

Subprocess-based cli_smoke covers the user-visible behavior, but coverage.py
only sees in-process imports. These call ``main([...])`` directly so the
module's argparse + exit-code mapping show up in the coverage matrix.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_FULL_MAPPING = Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")


def _stage(tmp_path: Path) -> Path:
    silver_dir = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(_FULL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return tmp_path


def test_main_phase_ab_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from needs_map.cli.main import main

    rc = main(
        [
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-B",
            "--no-llm",
            "--input-root",
            str(_stage(tmp_path / "in")),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "[needs-map 0.1.0]" in captured.out
    assert "phase=A" in captured.out
    assert "phase=B" in captured.out


def test_main_phase_full_returns_zero(tmp_path: Path) -> None:
    from needs_map.cli.main import main

    rc = main(
        [
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "all",
            "--no-llm",
            "--input-root",
            str(_stage(tmp_path / "in")),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0


def test_main_k_one_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from needs_map.cli.main import main

    rc = main(
        [
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--k",
            "1",
            "--no-llm",
            "--input-root",
            str(tmp_path),
            "--output-root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "k=1 is reserved" in err


def test_main_k_seven_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from needs_map.cli.main import main

    rc = main(
        [
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--k",
            "7",
            "--no-llm",
            "--input-root",
            str(tmp_path),
            "--output-root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "out of allowed range" in capsys.readouterr().err


def test_main_missing_input_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from needs_map.cli.main import main

    rc = main(
        [
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-B",
            "--no-llm",
            "--input-root",
            str(tmp_path / "empty"),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 2
    assert "input missing" in capsys.readouterr().err


def test_main_bad_semester_pattern_returns_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from needs_map.cli.main import main

    rc = main(
        [
            "run",
            "--semester",
            "2026-Q1",  # not in SemesterCode pattern
            "--course",
            "anatomy",
            "--no-llm",
            "--input-root",
            str(tmp_path),
            "--output-root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "argument validation failed" in capsys.readouterr().err
