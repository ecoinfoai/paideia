"""T025 — US1 pseudonym map (PRIV-03).

The written ``pseudonym_map.parquet`` is bijective and deterministic: pseudonyms
are assigned ``S001, S002, …`` ascending by ``student_id``, one per student, and
the mapping is reproducible run-to-run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from metric_codex.cli.main import app
from metric_codex.output.paths import silver_dir
from metric_codex.store.pseudonym import build_pseudonym_map

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


def _load_map(data_root: Path) -> pd.DataFrame:
    sd = silver_dir(SEMESTER, COURSE, data_root=data_root)
    return pd.read_parquet(sd / "pseudonym_map.parquet")


def test_pseudonym_map_ascending_and_bijective(tmp_path: Path) -> None:
    """Pseudonyms are S001/S002 ascending by student_id; bijective."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    df = _load_map(data_root).sort_values("student_id").reset_index(drop=True)
    assert list(df["student_id"]) == [SID_A, SID_B]
    assert list(df["pseudonym"]) == ["S001", "S002"]

    # Bijection: distinct student_ids ↔ distinct pseudonyms, equal counts.
    assert df["student_id"].is_unique
    assert df["pseudonym"].is_unique
    assert len(df["student_id"]) == len(df["pseudonym"])


def test_pseudonym_map_carries_names(tmp_path: Path) -> None:
    """name_kr is retained on the map (for later re-identification)."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    df = _load_map(data_root)
    by_sid = dict(zip(df["student_id"], df["name_kr"], strict=True))
    assert by_sid[SID_A] == "김철수"
    assert by_sid[SID_B] == "이영희"


def test_build_pseudonym_map_deterministic_unit() -> None:
    """build_pseudonym_map is deterministic and ascending regardless of input order."""
    ids = {SID_B: "이영희", SID_A: "김철수"}
    entries = build_pseudonym_map(ids)
    assert [e.student_id for e in entries] == [SID_A, SID_B]
    assert [e.pseudonym for e in entries] == ["S001", "S002"]
    # Re-running on the same set yields identical assignment.
    again = build_pseudonym_map(ids)
    assert [(e.student_id, e.pseudonym) for e in entries] == [
        (e.student_id, e.pseudonym) for e in again
    ]
