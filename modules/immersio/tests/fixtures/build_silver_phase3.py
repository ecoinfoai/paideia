"""Synthesize silver fixtures for spec 005-immersio-phase3-combined-analysis (T014/T015).

Builds four self-contained silver trees mirroring needs-map v0.1.1 + immersio
Phase 0+2 layouts, used as inputs by the Phase 3 ``combine`` pipeline tests:

1. ``silver_phase3_minimal`` (T014) — 30 students:
       22 응답+응시 (8 valid for OLS complete-case via missing axes ≤ 5)
       5 응시-only (결시=False but factor scores all None)
       3 응답-only (결시 학생; on_roster True)
       Plus 0 off-roster respondents (kept here for clarity; T015's
       ``silver_phase3_minimal`` does NOT trigger R-10
       ``n_off_roster_respondents`` — the off-roster scenario is exercised
       by the joiner unit test (T016) via in-line synthesis.)
   Cluster k=3 with deliberately separated means (cluster 0 = 60, 1 = 75,
   2 = 85) so US2 ANOVA always lands p<0.05 even on small fixtures.

2. ``silver_phase3_no_clusters`` (T015) — k=1 fallback (cluster_assignment
   parquet present but all rows cluster_id=0; cluster_names.json maps
   {0: "단일 군집 (산출 불가)"}).

3. ``silver_phase3_missing_factor_scores`` (T015) — factor_scores.parquet
   absent (US5 fail-fast trigger; cluster_assignment + manifest still
   present).

4. ``silver_phase3_small_subgroup`` (T015) — silver_phase3_minimal variant
   with one occupation category n=2 to exercise n<10 auto-exclude.

Output layout (inside each fixture root):
    silver/
      needs-map/2026-1-anatomy/
        factor_scores.parquet
        cluster_assignment.parquet
        cluster_names.json    # SPEC-GAP option A sidecar (developer 2026-04-30)
        manifest.json
      immersio/2026-1-anatomy/
        student_master.parquet
        diagnostic_response.parquet
        학생지표.parquet
        manifest.json

All parquet writes use pyarrow with ``compression="snappy"``,
``use_dictionary=False``, ``write_statistics=False`` per research §R13
determinism vector 2. Row order is ``student_id`` ascending.

Determinism: this script is import-safe and idempotent — calling
``build_all(repo_root)`` twice produces byte-identical parquet files
because it sets ``run_seed=0`` and writes deterministic ISO-8601 stamps
(``"2026-04-29T00:00:00Z"``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# 8-axis vocabulary (constitution v1.1.0).
_AXES: tuple[str, ...] = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)

# 13 chapter labels (anatomy fixture vocabulary; matches Phase 1+2 scheme).
_CHAPTERS: tuple[str, ...] = (
    "세포",
    "조직",
    "골격계",
    "근육계",
    "신경계",
    "내분비계",
    "심혈관계",
    "림프계",
    "호흡기계",
    "소화기계",
    "비뇨기계",
    "생식기계",
    "감각계",
)

_FIXED_GENERATED_AT_UTC = "2026-04-29T00:00:00Z"
_RUN_SEED = 0


# ---------------------------------------------------------------------------
# Student roster generation — deterministic, seed=0
# ---------------------------------------------------------------------------


def _student_id(idx: int) -> str:
    """Return a 10-digit zero-padded student id (canonical form)."""
    return f"2026{idx:06d}"


def _build_roster_minimal() -> list[dict[str, Any]]:
    """Build a 30-student roster: 22 응답+응시 / 5 응시-only / 3 응답-only.

    Layout (idx ascending, sections round-robin A/B/C):
        idx 0-21  → 응답+응시 (cluster id round-robin 0/1/2; mean 60/75/85)
        idx 22-26 → 응시-only (factor scores all None; cluster_id None)
        idx 27-29 → 응답-only (결시; factor scores populated; cluster_id 0/1/2)
    """
    rng = np.random.default_rng(_RUN_SEED)

    rows: list[dict[str, Any]] = []
    sections = ["A", "B", "C"]

    for i in range(22):  # 22 응답+응시
        cluster = i % 3
        mean = {0: 60.0, 1: 75.0, 2: 85.0}[cluster]
        score = float(np.clip(rng.normal(mean, 5.0), 0.0, 100.0))
        rows.append(
            {
                "idx": i,
                "student_id": _student_id(i),
                "name_kr": f"학생{i:02d}",
                "section": sections[i % 3],
                "on_roster": True,
                "responded": True,
                "exam_taken": True,
                "cluster_id": cluster,
                "total_score": score,
            }
        )

    for j in range(5):  # 응시-only (결시 아님, 진단 미응답)
        i = 22 + j
        cluster = j % 3
        mean = {0: 60.0, 1: 75.0, 2: 85.0}[cluster]
        score = float(np.clip(rng.normal(mean, 5.0), 0.0, 100.0))
        rows.append(
            {
                "idx": i,
                "student_id": _student_id(i),
                "name_kr": f"학생{i:02d}",
                "section": sections[i % 3],
                "on_roster": True,
                "responded": False,
                "exam_taken": True,
                "cluster_id": None,  # no factor scores ⇒ no cluster
                "total_score": score,
            }
        )

    for k in range(3):  # 응답-only (결시 학생)
        i = 27 + k
        cluster = k % 3
        rows.append(
            {
                "idx": i,
                "student_id": _student_id(i),
                "name_kr": f"학생{i:02d}",
                "section": sections[i % 3],
                "on_roster": True,
                "responded": True,
                "exam_taken": False,
                "cluster_id": cluster,
                "total_score": None,
            }
        )

    return rows


def _build_roster_small_subgroup() -> list[dict[str, Any]]:
    """Variant with deliberate occupation subgroup of n=2 (auto-exclude trigger).

    Built atop the minimal roster but tags 2 students with
    occupation='industry-edge' (n=2 ⇒ excluded by n<10) and the rest with
    'student' (n=28). Stored in the diagnostic_response payload, which the
    Phase 3 subgroup_compare module reads.
    """
    base = _build_roster_minimal()
    occupations = ["industry-edge"] * 2 + ["student"] * (len(base) - 2)
    for row, occ in zip(base, occupations, strict=True):
        row["occupation"] = occ
    return base


# ---------------------------------------------------------------------------
# Parquet write — deterministic flags
# ---------------------------------------------------------------------------


def _write_parquet_deterministic(df: pd.DataFrame, path: Path) -> None:
    """Write parquet with pyarrow flags pinned for byte-identical re-runs.

    research §R13 determinism vector 2: ``use_dictionary=False`` and
    ``write_statistics=False`` are required so the parquet metadata block
    does not vary between runs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(
        table,
        path,
        compression="snappy",
        use_dictionary=False,
        write_statistics=False,
    )


def _write_json_deterministic(payload: Any, path: Path) -> None:
    """Write a JSON file with sorted keys + 2-space indent + trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Synthesis: needs-map silver trio (factor_scores + cluster_assignment + manifest)
# ---------------------------------------------------------------------------


def _build_factor_scores_df(roster: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a needs-map factor_scores.parquet equivalent (FactorScoreRow rows).

    Synthetic structure: motivation_z is correlated with cluster_id (so US2
    ANOVA on motivation lands p<0.05), the other 7 axes are i.i.d. N(0, 1).
    Non-respondents (responded=False) get all-None entries with
    ``{axis}_missing=True``. Sorted by student_id ascending.
    """
    rng = np.random.default_rng(_RUN_SEED + 1)
    rows: list[dict[str, Any]] = []
    for r in sorted(roster, key=lambda x: x["student_id"]):
        if not r["responded"]:
            row: dict[str, Any] = {
                "student_id": r["student_id"],
                "on_roster": r["on_roster"],
                "responded": False,
                "section": r["section"],
            }
            for axis in _AXES:
                row[axis] = None
                row[f"{axis}_z"] = None
                row[f"{axis}_missing"] = True
            rows.append(row)
            continue

        # Respondent: correlated motivation, i.i.d. others. Likert mean (1-7
        # scale): convert z to raw via mean=4 + 0.7*z (kept in [1, 7]).
        cluster_offset = {0: -1.0, 1: 0.0, 2: 1.0}[r["cluster_id"]]
        motivation_z = float(rng.normal(cluster_offset, 0.5))
        row = {
            "student_id": r["student_id"],
            "on_roster": r["on_roster"],
            "responded": True,
            "section": r["section"],
        }
        for axis in _AXES:
            if axis == "motivation":
                z = motivation_z
            else:
                z = float(rng.normal(0.0, 1.0))
            raw = float(np.clip(4.0 + 0.7 * z, 1.0, 7.0))
            row[axis] = raw
            row[f"{axis}_z"] = z
            row[f"{axis}_missing"] = False
        rows.append(row)

    return pd.DataFrame(rows).sort_values("student_id").reset_index(drop=True)


def _build_cluster_assignment_df(
    roster: list[dict[str, Any]], *, k: int
) -> pd.DataFrame:
    """Build cluster_assignment.parquet (ClusterAssignmentRow rows).

    Only respondents with cluster_id present. k=1 fallback: every respondent
    gets cluster_id=0.
    """
    rng = np.random.default_rng(_RUN_SEED + 2)
    rows: list[dict[str, Any]] = []
    for r in sorted(roster, key=lambda x: x["student_id"]):
        if not r["responded"]:
            continue
        cid = 0 if k == 1 else int(r["cluster_id"])
        rows.append(
            {
                "student_id": r["student_id"],
                "cluster_id": cid,
                "distance_to_centroid": float(abs(rng.normal(0.0, 1.0))),
            }
        )
    return pd.DataFrame(rows).sort_values("student_id").reset_index(drop=True)


def _build_cluster_names(*, k: int) -> dict[int, str]:
    """Build the cluster_names sidecar dict (option A).

    SPEC-GAP-001 (developer 2026-04-30; qa-engineer PASS option A 2026-04-30):
    NeedsMapManifest does not currently persist cluster_names — needs-map's
    ``ClusterReport.cluster_names`` is in-memory only and gets serialised
    nowhere on the silver tier. T014 fixtures land it as a sidecar JSON
    (``cluster_names.json``) next to ``cluster_assignment.parquet``; the
    joiner (T016) reads from this sidecar. Once spec 003 follow-up patch
    teaches needs-map ``pipeline.py`` to ``json.dump(cluster_report.cluster_names,
    sidecar_path, ensure_ascii=False, sort_keys=True, indent=2)``, this
    builder needs no code change — the fixture sidecar matches the future
    real one byte-for-byte.
    """
    if k == 1:
        return {0: "단일 군집 (산출 불가)"}
    return {0: "성장 잠재형", 1: "안정 학습형", 2: "고성취 자기주도형"}


def _build_needs_map_manifest(
    *,
    semester: str,
    course_slug: str,
    k_used: int,
    silhouette: float | None,
) -> dict[str, Any]:
    """Build a minimal but schema-valid NeedsMapManifest payload.

    schema_version 1.1.0 (matches production needs-map v0.1.1). All sha256
    placeholders are hex zeros — these are inputs to the fixture, not real
    file fingerprints.
    """
    sha_zero = "0" * 64
    return {
        "schema_version": "1.1.0",
        "semester": semester,
        "course_slug": course_slug,
        "output_key": f"{semester}-{course_slug}",
        "module_version": "needs-map/0.1.1",
        "created_at_utc": _FIXED_GENERATED_AT_UTC,
        "inputs": {
            "diagnostic_response_path": "fixture://diagnostic_response.parquet",
            "diagnostic_response_sha256": sha_zero,
            "student_master_path": "fixture://student_master.parquet",
            "student_master_sha256": sha_zero,
            "diagnostic_mapping_path": "fixture://diagnostic_mapping.yaml",
            "diagnostic_mapping_sha256": sha_zero,
            "missing_policy_source": {axis: "default" for axis in _AXES},
        },
        "standard_axes_used": list(_AXES),
        "standard_axes_skipped": [],
        "phases_executed": ["A", "B", "C", "D", "E", "F"],
        "rows_per_phase": [
            {"phase": "A", "rows_written": 0},
            {"phase": "B", "rows_written": 0},
            {"phase": "C", "rows_written": 0},
            {"phase": "D", "rows_written": 0},
            {"phase": "E", "rows_written": 0},
            {"phase": "F", "rows_written": 0},
        ],
        "cluster_k_used": k_used,
        "cluster_silhouette_used": silhouette,
        "free_text_dictionary_match_rate": None,
        "dictionary_language_mismatch_warning": False,
        "weak_structure_warning": False,
        "llm_provider": None,
        "llm_model": None,
        "llm_calls": [],
        "pii_redaction_validated": True,
        "previous_run_archive_path": None,
        "warnings": [],
        "unrecognized_inputs": [],
        "font_resolution": None,
        "sentiment": None,
        "new_outputs": None,
        "vocabulary": None,
    }


# ---------------------------------------------------------------------------
# Synthesis: immersio Phase 0+2 silver quad
# ---------------------------------------------------------------------------


def _build_student_master_df(roster: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the StudentMaster Phase 0 parquet.

    ``axis_scores`` dict is serialized as JSON string (consistent with the
    Phase 2 student_master parquet that production immersio writes).
    """
    rows: list[dict[str, Any]] = []
    axis_scores_json = json.dumps(
        {axis: None for axis in _AXES}, ensure_ascii=False, sort_keys=True
    )
    for r in sorted(roster, key=lambda x: x["student_id"]):
        rows.append(
            {
                "student_id": r["student_id"],
                "semester": "2026-1",
                "course_slug": "anatomy",
                "on_roster": r["on_roster"],
                "section": r["section"] if r["on_roster"] else None,
                "name_kr": r["name_kr"],
                "diagnostic_responded": r["responded"],
                "exam_taken": r["exam_taken"],
                "exam_absent": r["on_roster"] and not r["exam_taken"],
                "attendance_recorded": True,
                "exam_total_score": r["total_score"],
                "exam_max_score": 100.0 if r["exam_taken"] else None,
                "attendance_present_count": 14 if r["exam_taken"] else 0,
                "attendance_absent_count": 0,
                "attendance_late_count": 0,
                "attendance_excused_count": 0,
                "axis_scores": axis_scores_json,
            }
        )
    return pd.DataFrame(rows).sort_values("student_id").reset_index(drop=True)


def _build_diagnostic_response_df(
    roster: list[dict[str, Any]], factor_scores: pd.DataFrame
) -> pd.DataFrame:
    """Build the DiagnosticResponse long-form parquet (likert rows only).

    For each respondent × axis emit a likert row with value_int = round(raw).
    Plus subgroup category rows (occupation, prior_biology) where the roster
    provides them. R10 subgroup mapping consumed by Phase 3 subgroup_compare.
    """
    rows: list[dict[str, Any]] = []
    fs_by_id = {row["student_id"]: row for _, row in factor_scores.iterrows()}

    for r in sorted(roster, key=lambda x: x["student_id"]):
        if not r["responded"]:
            continue
        fs_row = fs_by_id[r["student_id"]]
        for axis in _AXES:
            raw = fs_row[axis]
            if raw is None:
                continue
            rows.append(
                {
                    "student_id": r["student_id"],
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": axis,
                    "axis_kind": "likert",
                    "option_key": None,
                    "value_int": int(round(float(raw))),
                    "value_bool": None,
                    "value_text": None,
                    "source_column": f"col_{axis}",
                }
            )
        # Optional subgroup category (occupation) when roster declares it.
        if "occupation" in r:
            rows.append(
                {
                    "student_id": r["student_id"],
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": "occupation",
                    "axis_kind": "freetext",
                    "option_key": None,
                    "value_int": None,
                    "value_bool": None,
                    "value_text": r["occupation"],
                    "source_column": "col_occupation",
                }
            )
    return (
        pd.DataFrame(rows)
        .sort_values(["student_id", "axis", "option_key"], na_position="last")
        .reset_index(drop=True)
    )


def _build_student_metrics_df(roster: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the StudentExamMetrics 학생지표.parquet (Phase 2 silver).

    Dict columns are serialized as JSON strings per research §R8 — pyarrow
    cannot represent empty struct types. The JSON is canonicalized
    (``sort_keys=True, ensure_ascii=False``) so re-runs are byte-identical.
    """
    rng = np.random.default_rng(_RUN_SEED + 3)
    rows: list[dict[str, Any]] = []
    takers = [r for r in roster if r["exam_taken"]]
    scores = np.array([r["total_score"] for r in takers], dtype=float)
    pop_mean = float(scores.mean())
    pop_sd = float(scores.std(ddof=0))

    def _json(d: dict[Any, Any]) -> str:
        return json.dumps(d, ensure_ascii=False, sort_keys=True)

    for r in sorted(roster, key=lambda x: x["student_id"]):
        if r["exam_taken"]:
            score = float(r["total_score"])
            score_pct = score  # max=100 ⇒ percent equals raw
            section_p = float(rng.uniform(0.0, 100.0))
            cohort_p = float(rng.uniform(0.0, 100.0))
            z = (
                (score - pop_mean) / pop_sd if pop_sd > 0 else None
            )
            chap_rates = {
                ch: float(np.clip(rng.beta(2, 2), 0.0, 1.0)) for ch in _CHAPTERS
            }
        else:
            score = None
            score_pct = None
            section_p = None
            cohort_p = None
            z = None
            chap_rates = {}

        rows.append(
            {
                "student_id": r["student_id"],
                "name_kr": r["name_kr"],
                "section": r["section"],
                "semester": "2026-1",
                "course_slug": "anatomy",
                "exam_taken": r["exam_taken"],
                "total_score": score,
                "score_percent": score_pct,
                "section_percentile": section_p,
                "cohort_percentile": cohort_p,
                "z_score": z,
                "chapter_correct_rates": _json(chap_rates),
                "source_correct_rates": _json({}),
                "difficulty_correct_rates": _json({}),
                "expected_difficulty_correct_rates": _json({}),
                "item_type_correct_rates": _json({}),
                "interest_chapters_correct_rate": None,
                "aversion_chapters_correct_rate": None,
            }
        )
    return pd.DataFrame(rows).sort_values("student_id").reset_index(drop=True)


def _build_immersio_phase2_manifest(
    *, semester: str, course_slug: str, n_students: int
) -> dict[str, Any]:
    """Minimal Phase 2 manifest (used only for SHA + schema_version probe)."""
    return {
        "schema_version": "0.1.0",
        "module_version": "immersio/0.1.0",
        "semester": semester,
        "course_slug": course_slug,
        "generated_at_utc": _FIXED_GENERATED_AT_UTC,
        "n_students": n_students,
    }


# ---------------------------------------------------------------------------
# Top-level fixture builders
# ---------------------------------------------------------------------------


def _write_silver_tree(
    *,
    out_root: Path,
    roster: list[dict[str, Any]],
    k: int,
    include_factor_scores: bool = True,
) -> None:
    """Land all silver parquet + manifest artifacts under ``out_root/silver``.

    Args:
        out_root: Destination fixture root (e.g. ``.../silver_phase3_minimal``).
        roster: Generated student roster.
        k: Cluster count (1 or 3 in current fixtures).
        include_factor_scores: When False, skip writing
            ``factor_scores.parquet`` (used by the
            ``silver_phase3_missing_factor_scores`` fixture to trigger US5
            fail-fast).
    """
    semester, course_slug = "2026-1", "anatomy"
    nm_root = out_root / "silver" / "needs-map" / f"{semester}-{course_slug}"
    im_root = out_root / "silver" / "immersio" / f"{semester}-{course_slug}"

    fs_df = _build_factor_scores_df(roster)
    if include_factor_scores:
        _write_parquet_deterministic(fs_df, nm_root / "factor_scores.parquet")

    ca_df = _build_cluster_assignment_df(roster, k=k)
    _write_parquet_deterministic(ca_df, nm_root / "cluster_assignment.parquet")

    cluster_names = _build_cluster_names(k=k)
    _write_json_deterministic(
        {str(cid): name for cid, name in cluster_names.items()},
        nm_root / "cluster_names.json",
    )

    silhouette = None if k == 1 else 0.32
    _write_json_deterministic(
        _build_needs_map_manifest(
            semester=semester,
            course_slug=course_slug,
            k_used=k,
            silhouette=silhouette,
        ),
        nm_root / "manifest.json",
    )

    sm_df = _build_student_master_df(roster)
    _write_parquet_deterministic(sm_df, im_root / "student_master.parquet")

    dr_df = _build_diagnostic_response_df(roster, fs_df)
    _write_parquet_deterministic(dr_df, im_root / "diagnostic_response.parquet")

    metrics_df = _build_student_metrics_df(roster)
    _write_parquet_deterministic(metrics_df, im_root / "학생지표.parquet")

    _write_json_deterministic(
        _build_immersio_phase2_manifest(
            semester=semester,
            course_slug=course_slug,
            n_students=len(roster),
        ),
        im_root / "manifest.json",
    )


def build_silver_phase3_minimal(out_root: Path) -> None:
    """T014 — 30-student fixture with k=3 well-separated clusters."""
    _write_silver_tree(out_root=out_root, roster=_build_roster_minimal(), k=3)


def build_silver_phase3_no_clusters(out_root: Path) -> None:
    """T015 — k=1 fallback (single cluster)."""
    _write_silver_tree(out_root=out_root, roster=_build_roster_minimal(), k=1)


def build_silver_phase3_missing_factor_scores(out_root: Path) -> None:
    """T015 — factor_scores.parquet absent (US5 fail-fast)."""
    _write_silver_tree(
        out_root=out_root,
        roster=_build_roster_minimal(),
        k=3,
        include_factor_scores=False,
    )


def build_silver_phase3_small_subgroup(out_root: Path) -> None:
    """T015 — occupation category n=2 to exercise n<10 auto-exclude."""
    _write_silver_tree(
        out_root=out_root, roster=_build_roster_small_subgroup(), k=3
    )


def build_all(fixtures_root: Path) -> None:
    """Land all four fixture trees under ``fixtures_root/silver_phase3_*``.

    Idempotent: re-running overwrites prior outputs byte-identically.
    """
    build_silver_phase3_minimal(fixtures_root / "silver_phase3_minimal")
    build_silver_phase3_no_clusters(fixtures_root / "silver_phase3_no_clusters")
    build_silver_phase3_missing_factor_scores(
        fixtures_root / "silver_phase3_missing_factor_scores"
    )
    build_silver_phase3_small_subgroup(
        fixtures_root / "silver_phase3_small_subgroup"
    )


__all__ = [
    "build_all",
    "build_silver_phase3_minimal",
    "build_silver_phase3_no_clusters",
    "build_silver_phase3_missing_factor_scores",
    "build_silver_phase3_small_subgroup",
]


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    build_all(here)
    print(f"OK silver_phase3_* fixtures land under {here}")
