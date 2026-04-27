"""CLI smoke test (T034).

DELIBERATELY RED at T034: pipeline.py phase bodies are NotImplementedError stubs
so any --phases value triggers exit 99. This RED is the Phase 3 entry signal.
T056/T074/T105 wire each phase progressively; the test will then need to be
relaxed (e.g. accept exit 0 once Phase A+B fixtures land at T037-T040).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _have_paideia_needs_map() -> bool:
    return shutil.which("paideia-needs-map") is not None


@pytest.mark.skipif(
    not _have_paideia_needs_map(),
    reason="paideia-needs-map console_script not installed in this venv.",
)
def test_cli_smoke_red(tmp_path: Path) -> None:
    """Skeleton CLI should reach run_needs_map and surface NotImplementedError as exit 99.

    This is the deliberate RED signal for Phase 3.2 entry — the test will be
    rewritten once T056 wires Phase A+B with real fixture data.
    """
    executable = shutil.which("paideia-needs-map")
    assert executable is not None  # guarded by the skipif above
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
            str(tmp_path),
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 99, (
        f"Expected exit 99 (NotImplementedError stub), got {proc.returncode}. "
        f"stderr={proc.stderr}"
    )
    assert "[needs-map 0.1.0]" in proc.stdout
    assert "not yet implemented" in proc.stderr or "Phase A" in proc.stderr


def test_cli_module_invocation_smoke(tmp_path: Path) -> None:
    """python -m needs_map.cli.main as fallback invocation (cli.md §Module Invocation)."""
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
            str(tmp_path),
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 99
    assert "not yet implemented" in proc.stderr


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
