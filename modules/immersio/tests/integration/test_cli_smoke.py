"""Smoke test for `immersio ingest` via the installed console script."""

from __future__ import annotations

import subprocess
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRONZE = FIXTURES / "bronze_minimal"
MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"


def test_cli_smoke(tmp_path: Path) -> None:
    out = tmp_path / "silver"
    completed = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "uv",
            "run",
            "--python",
            "3.11",
            "immersio",
            "ingest",
            "--bronze-dir",
            str(BRONZE),
            "--mapping",
            str(MAPPING),
            "--output-dir",
            str(out),
            "--no-git-commit",
            "--verbose",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(Path(__file__).resolve().parents[3]),
    )
    assert completed.returncode == 0, (
        f"CLI exit {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    expected_segments = [
        "[1/7] Discovering Bronze inputs",
        "[2/7] Loading mapping",
        "[3/7] Parsing diagnostic CSV",
        "[4/7] Parsing exam OMR",
        "[5/7] Parsing attendance",
        "[6/7] Combining sources",
        "[7/7] Writing Silver",
    ]
    for segment in expected_segments:
        assert segment in completed.stdout, (
            f"missing verbose segment {segment!r} in stdout: {completed.stdout}"
        )
    assert (out / "2026-1-anatomy" / "manifest.json").exists()
