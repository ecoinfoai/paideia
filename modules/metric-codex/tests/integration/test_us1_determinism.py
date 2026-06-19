"""T023 — US1 determinism / idempotency (SC-007 / DET-01).

Running ``metric-codex ingest`` twice with the SAME ``--now`` produces a
byte-identical ``codex_entry.parquet`` and does not grow the entry count
(re-ingestion is idempotent, FR-009).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from metric_codex.cli.main import app
from metric_codex.output.paths import silver_dir

from tests.fixtures.scenario_a import COURSE, SEMESTER, build_scenario_a

_NOW = "2026-06-19T00:00:00Z"


def _ingest(data_root: Path) -> int:
    return app(
        [
            "ingest",
            "--semester",
            SEMESTER,
            "--course",
            COURSE,
            "--data-root",
            str(data_root),
            "--now",
            _NOW,
        ]
    )


def _store(data_root: Path) -> Path:
    return silver_dir(SEMESTER, COURSE, data_root=data_root) / "codex_entry.parquet"


def test_codex_entry_bytes_identical_across_runs(tmp_path: Path) -> None:
    """Two ingest runs with the same --now → byte-identical codex_entry.parquet."""
    data_root = build_scenario_a(tmp_path)

    assert _ingest(data_root) == 0
    first = _store(data_root).read_bytes()

    assert _ingest(data_root) == 0
    second = _store(data_root).read_bytes()

    assert first == second


def test_entry_count_unchanged_on_reingest(tmp_path: Path) -> None:
    """Re-ingesting identical inputs does not grow the entry count (idempotent)."""
    data_root = build_scenario_a(tmp_path)

    assert _ingest(data_root) == 0
    count_first = len(pd.read_parquet(_store(data_root)))

    assert _ingest(data_root) == 0
    count_second = len(pd.read_parquet(_store(data_root)))

    assert count_first == count_second
