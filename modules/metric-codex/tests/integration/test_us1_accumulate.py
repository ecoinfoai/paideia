"""T022 — US1 Scenario A: structured + unstructured data coexist per student.

After ``metric-codex ingest`` runs over a data_root where one student appears in
BOTH the school Excel (minimal value_num) AND immersio/needs-map Silver (rich
value_num percentiles + value_text free-text), the written
``codex_entry.parquet`` carries ONE student_id record that combines both
(SC-001 / FR-007).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from metric_codex.cli.main import app
from metric_codex.output.paths import silver_dir

from tests.fixtures.scenario_a import COURSE, SEMESTER, SID_A, SID_B, build_scenario_a

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


def _load_entries(data_root: Path) -> pd.DataFrame:
    store = silver_dir(SEMESTER, COURSE, data_root=data_root) / "codex_entry.parquet"
    return pd.read_parquet(store)


def test_ingest_exit_zero_writes_store(tmp_path: Path) -> None:
    """ingest returns 0 and writes the codex_entry / source_ledger / pseudonym parquet."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    sd = silver_dir(SEMESTER, COURSE, data_root=data_root)
    assert (sd / "codex_entry.parquet").is_file()
    assert (sd / "source_ledger.parquet").is_file()
    assert (sd / "pseudonym_map.parquet").is_file()
    assert (sd / "manifest_metric-codex.json").is_file()


def test_student_a_has_both_structured_and_unstructured(tmp_path: Path) -> None:
    """Student A's record combines minimal value_num AND rich value_text entries."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    df = _load_entries(data_root)
    a = df[df["student_id"] == SID_A]

    # Minimal layer score/attendance from school Excel — value_num present.
    minimal = a[a["layer"] == "minimal"]
    assert set(minimal["entry_kind"]) == {"score_total", "score_percent", "attendance"}
    assert minimal["value_num"].notna().all()
    assert minimal["value_text"].isna().all()

    # Rich layer percentiles from immersio — value_num present.
    rich_num = a[(a["layer"] == "rich") & (a["value_num"].notna())]
    assert "percentile_section" in set(rich_num["entry_kind"])

    # Rich layer free-text categories from needs-map — value_text present.
    rich_text = a[(a["layer"] == "rich") & (a["value_text"].notna())]
    assert set(rich_text["entry_kind"]) == {"freetext_category"}
    assert set(rich_text["value_text"]) == {"health", "career"}

    # Coexistence: same single student_id carries all three.
    assert len(a["student_id"].unique()) == 1


def test_student_b_minimal_only(tmp_path: Path) -> None:
    """Student B (school-only) appears with minimal entries and no rich data."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    df = _load_entries(data_root)
    b = df[df["student_id"] == SID_B]
    assert set(b["layer"]) == {"minimal"}
    assert set(b["entry_kind"]) == {"score_total", "score_percent", "attendance"}
