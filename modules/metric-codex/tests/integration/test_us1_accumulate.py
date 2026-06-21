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

from tests.fixtures.scenario_a import (
    COURSE,
    NAME_A,
    NAME_B,
    SEMESTER,
    SID_A,
    SID_B,
    build_scenario_a,
    make_dirs,
    write_school_excel,
    write_school_map,
    write_student_metrics,
)

_SID_C = "2026000003"
_NAME_C = "박민수"

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


# ---------------------------------------------------------------------------
# Cross-run accumulation (FR-006 add + correction)
# ---------------------------------------------------------------------------


def _school_only(tmp_path: Path) -> tuple[Path, Path]:
    """Build a school-Excel-only data_root; return ``(data_root, excel_path)``."""
    data_root, bronze, _immersio, _needsmap = make_dirs(tmp_path)
    write_school_map(bronze / "성적출석_map.yaml")
    return data_root, bronze / "성적출석.xlsx"


def test_cross_run_add_student(tmp_path: Path) -> None:
    """Run 2 adding a NEW student grows the store; prior students are retained."""
    data_root, excel = _school_only(tmp_path)

    # Run 1 — A and B.
    write_school_excel(
        excel,
        rows=[(SID_A, NAME_A, 85, 90.5, 15), (SID_B, NAME_B, 70, 75.0, 12)],
    )
    assert _ingest(data_root) == 0
    count_run1 = len(_load_entries(data_root))
    assert set(_load_entries(data_root)["student_id"]) == {SID_A, SID_B}

    # Run 2 — A, B, and a NEW student C.
    write_school_excel(
        excel,
        rows=[
            (SID_A, NAME_A, 85, 90.5, 15),
            (SID_B, NAME_B, 70, 75.0, 12),
            (_SID_C, _NAME_C, 60, 65.0, 10),
        ],
    )
    assert _ingest(data_root) == 0

    df = _load_entries(data_root)
    assert set(df["student_id"]) == {SID_A, SID_B, _SID_C}
    # C contributes 3 new minimal entries (total/percent/attendance).
    assert len(df) == count_run1 + 3


def test_cross_run_correction(tmp_path: Path) -> None:
    """Run 2 correcting a score for the same natural key updates value, keeps count."""
    data_root, excel = _school_only(tmp_path)

    # Run 1 — A score_total = 85.
    write_school_excel(excel, rows=[(SID_A, NAME_A, 85, 90.5, 15)])
    assert _ingest(data_root) == 0
    count_run1 = len(_load_entries(data_root))

    # Run 2 — same student, corrected score_total = 99.
    write_school_excel(excel, rows=[(SID_A, NAME_A, 99, 90.5, 15)])
    assert _ingest(data_root) == 0

    df = _load_entries(data_root)
    # Count unchanged — correction replaces in place, not appends.
    assert len(df) == count_run1
    total = df[(df["student_id"] == SID_A) & (df["entry_kind"] == "score_total")]
    assert len(total) == 1
    assert total.iloc[0]["value_num"] == 99.0


# ---------------------------------------------------------------------------
# Boundary — --school-excel must live inside --data-root (Important C)
# ---------------------------------------------------------------------------


def _write_combined_parquet(path: Path, *, sid: str, name: str) -> None:
    """Write a minimal 진단×시험결합.parquet row for one student."""
    import json

    axis_fields: dict[str, object] = {}
    for axis in [
        "digital_efficacy", "motivation", "time_availability", "material_preference",
        "study_strategy", "study_environment", "social_learning", "feedback_seeking",
    ]:
        axis_fields[f"{axis}_raw"] = 1.0
        axis_fields[f"{axis}_z"] = 0.1
        axis_fields[f"{axis}_missing"] = False

    rows = [{
        "student_id": sid,
        "name_kr": name,
        "on_roster": True,
        "section": "A",
        "semester": SEMESTER,
        "course_slug": COURSE,
        **axis_fields,
        "cluster_id": 1,
        "cluster_label": "표준형",
        "cluster_distance": 0.5,
        "exam_taken": True,
        "total_score": 80.0,
        "score_percent": 80.0,
        "section_percentile": 75.0,
        "cohort_percentile": 70.0,
        "z_score": 1.2,
        "chapter_correct_rates": json.dumps({"순환": 0.9}, ensure_ascii=False),
        "source_correct_rates": json.dumps({}, ensure_ascii=False),
        "difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
        "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
        "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
        "prior_readiness_q5": None,
        "prior_readiness_q6": None,
        "time_pattern_q21": None,
        "time_pattern_q22": None,
        "time_pattern_q23": None,
        "interest_topics_q9": None,
        "interest_topics_q10": None,
        "interest_topics_q11": None,
        "categorical_intent_q12": None,
        "categorical_intent_q13": None,
        "진단응답": True,
        "시험응시": True,
        "needs_map_schema_version": "0.1.0",
        "immersio_phase2_schema_version": "0.1.0",
    }]
    import pandas as pd
    pd.DataFrame(rows).to_parquet(path)


def _write_factor_scores(path: Path, *, sid: str) -> None:
    """Write a minimal factor_scores.parquet for one student."""
    import pandas as pd
    from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

    axis_fields: dict[str, object] = {}
    for axis in STANDARD_AXIS_KEYS:
        axis_fields[axis] = 1.0          # raw score column (no _raw suffix)
        axis_fields[f"{axis}_z"] = 0.1
        axis_fields[f"{axis}_missing"] = False
    rows = [{
        "student_id": sid,
        "on_roster": True,
        "responded": True,
        "section": "A",
        **axis_fields,
    }]
    pd.DataFrame(rows).to_parquet(path)


def _write_cluster_assignment_with_names(
    assignment_path: Path,
    names_path: Path,
    *,
    sid: str,
) -> None:
    """Write cluster_assignment.parquet + cluster_names.json for one student."""
    import json
    import pandas as pd
    rows = [{"student_id": sid, "cluster_id": 1, "distance_to_centroid": 0.5}]
    pd.DataFrame(rows).to_parquet(assignment_path)
    names_path.write_text(json.dumps({"1": "표준형"}), encoding="utf-8")


# ---------------------------------------------------------------------------
# T012 — superseded individual sources gone after combined ingest (MC-U26)
# ---------------------------------------------------------------------------


def test_superseded_sources_removed_on_combined_ingest(tmp_path: Path) -> None:
    """Run1: ingest individual sources. Run2: ingest combined. No double-count.

    After run2 the store must:
    - contain NO entries with source_id in {immersio:학생지표, needs-map:factor_scores,
      needs-map:cluster_assignment} (those individual source_ids are superseded).
    - have NO (student_id, key) pair counted more than once (no double-count).
    """
    data_root, bronze, immersio, needsmap = make_dirs(tmp_path)
    write_school_map(bronze / "성적출석_map.yaml")
    write_school_excel(bronze / "성적출석.xlsx", rows=[(SID_A, NAME_A, 85, 90.5, 15)])

    # Run 1: individual sources (학생지표 + factor_scores + cluster_assignment)
    write_student_metrics(immersio / "학생지표.parquet")
    _write_factor_scores(needsmap / "factor_scores.parquet", sid=SID_A)
    _write_cluster_assignment_with_names(
        needsmap / "cluster_assignment.parquet",
        needsmap / "cluster_names.json",
        sid=SID_A,
    )

    import pandas as pd
    from metric_codex.output.paths import silver_dir as _silver_dir

    rc = app(["ingest", "--semester", SEMESTER, "--course", COURSE,
              "--data-root", str(data_root), "--now", _NOW])
    assert rc == 0, "run1 ingest failed"

    sd = _silver_dir(SEMESTER, COURSE, data_root=data_root)
    df_run1 = pd.read_parquet(sd / "codex_entry.parquet")
    individual_source_ids = {"immersio:학생지표", "needs-map:factor_scores",
                             "needs-map:cluster_assignment"}
    # Run1 SHOULD have entries from individual source_ids
    run1_individual = df_run1[df_run1["source_id"].isin(individual_source_ids)]
    assert len(run1_individual) > 0, "precondition: run1 has individual source entries"

    # Run 2: replace with combined source (진단×시험결합)
    # The individual files stay on disk (degrade if combined supersedes)
    _write_combined_parquet(immersio / "진단×시험결합.parquet", sid=SID_A, name=NAME_A)

    rc = app(["ingest", "--semester", SEMESTER, "--course", COURSE,
              "--data-root", str(data_root), "--now", "2026-06-20T00:00:00Z"])
    assert rc == 0, "run2 ingest failed"

    df_run2 = pd.read_parquet(sd / "codex_entry.parquet")

    # After run2: NO entries with the superseded individual source_ids
    still_individual = df_run2[df_run2["source_id"].isin(individual_source_ids)]
    assert len(still_individual) == 0, (
        f"superseded entries still in store after combined ingest: "
        f"{still_individual['source_id'].unique().tolist()}"
    )

    # No (student_id, key) double-count
    dup = df_run2.groupby(["student_id", "key"]).size()
    doubles = dup[dup > 1]
    assert len(doubles) == 0, (
        f"double-counted (student_id, key) pairs after combined ingest:\n{doubles}"
    )


def test_school_excel_outside_data_root_exits_two(tmp_path: Path) -> None:
    """A --school-excel path outside --data-root is a clear input error (exit 2)."""
    data_root = build_scenario_a(tmp_path)

    # An excel placed OUTSIDE the data_root tree.
    outside = tmp_path / "outside" / "성적출석.xlsx"
    outside.parent.mkdir(parents=True)
    write_school_excel(outside)

    result = app(
        [
            "ingest",
            "--semester",
            SEMESTER,
            "--course",
            COURSE,
            "--data-root",
            str(data_root),
            "--school-excel",
            str(outside),
            "--now",
            "2026-06-19T00:00:00Z",
        ]
    )
    assert result == 2
