"""CLI smoke tests (T034 reworked at T057).

Phase A+B is wired (T056 + T057), so the previous skeleton-RED expectation
flips: the happy-path subprocess invocation now produces exit 0 and writes
the two parquet outputs. The Phase C/D/E/F NotImplementedError stub still
surfaces as exit 99 — covered by the dedicated phase_c_red test below.

Argument validation tests (--k=1, --k=7, missing input) are unchanged from
T032 since they trip before reaching the (now-implemented) pipeline.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
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


def _have_paideia_needs_map() -> bool:
    return shutil.which("paideia-needs-map") is not None


@pytest.mark.skipif(
    not _have_paideia_needs_map(),
    reason="paideia-needs-map console_script not installed in this venv.",
)
def test_cli_smoke_phase_ab_green(tmp_path: Path) -> None:
    """Phase A+B subprocess invocation now exits 0 and writes both parquets."""
    executable = shutil.which("paideia-needs-map")
    assert executable is not None
    staged_in = _stage(tmp_path / "in")
    proc = subprocess.run(  # noqa: S603 — absolute path resolved via shutil.which
        [
            executable,
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-B",
            "--no-llm",
            "--input-root",
            str(staged_in),
            "--output-root",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"expected exit 0, got {proc.returncode}. stderr={proc.stderr}"
    assert "[needs-map 0.1.0]" in proc.stdout
    assert "phase=A rows_written=6" in proc.stdout
    assert "phase=B rows_written=9" in proc.stdout
    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    assert (silver / "scale_reliability.parquet").is_file()
    assert (silver / "factor_scores.parquet").is_file()
    assert (silver / "manifest.json").is_file()


def test_cli_module_invocation_phase_ab_green(tmp_path: Path) -> None:
    """`python -m needs_map.cli.main` fallback (cli.md §Module Invocation)."""
    staged_in = _stage(tmp_path / "in")
    proc = subprocess.run(  # noqa: S603 — sys.executable trusted
        [
            sys.executable,
            "-m",
            "needs_map.cli.main",
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-B",
            "--no-llm",
            "--input-root",
            str(staged_in),
            "--output-root",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"expected exit 0, got {proc.returncode}. stderr={proc.stderr}"
    assert "phase=B rows_written=9" in proc.stdout


def test_cli_phase_d_still_red(tmp_path: Path) -> None:
    """Phase D is not yet wired (T105 pending) — pipeline raises NotImplementedError → exit 99."""
    staged_in = _stage(tmp_path / "in")
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "needs_map.cli.main",
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-D",
            "--no-llm",
            "--input-root",
            str(staged_in),
            "--output-root",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 99
    assert "Phase D not wired" in proc.stderr


def test_cli_phase_c_now_green(tmp_path: Path) -> None:
    """Phase C is wired (T074) — exit 0 + cluster_assignment.parquet written."""
    staged_in = _stage(tmp_path / "in")
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "needs_map.cli.main",
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-C",
            "--no-llm",
            "--input-root",
            str(staged_in),
            "--output-root",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "phase=C" in proc.stdout
    assert (
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "cluster_assignment.parquet"
    ).is_file()


def test_cli_missing_input_exit_2(tmp_path: Path) -> None:
    """Missing diagnostic_response.parquet → exit 2 (cli.md input contract)."""
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "needs_map.cli.main",
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
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "input missing" in proc.stderr


def test_cli_rejects_k_one(tmp_path: Path) -> None:
    """--k=1 must exit 1 — sample-too-small auto-fallback only (FR-010)."""
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "needs_map.cli.main",
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
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "k=1 is reserved" in proc.stderr


def test_cli_rejects_k_out_of_range(tmp_path: Path) -> None:
    """--k=7 (or any out-of-range int) exits 1."""
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "needs_map.cli.main",
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
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "out of allowed range" in proc.stderr
