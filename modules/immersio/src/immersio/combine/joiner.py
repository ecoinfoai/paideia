"""Left-join student_master ⊕ factor_scores ⊕ cluster_assignment ⊕ 학생지표 (T016).

Implements the FR-016 left-join policy: every roster student becomes one row
of ``CombinedAnalysisRow``-shaped output (60 columns, fixed order per
``contracts/parquet_silver_combined.md``). Off-roster respondents are
*excluded* from the silver output but their count is returned in
:class:`UnmatchedCounts` for the manifest's R-10 audit gate.

The joiner is intentionally thin — it does no I/O. Callers (cli/pipeline)
are responsible for reading the parquet/json files (including the
SPEC-GAP-001 ``cluster_names.json`` sidecar) and invoking
:func:`join_silver_phase3` with the loaded frames + dict. This keeps the
joiner deterministic and trivially fixture-testable.

Group 6 — needs-map auxiliary group columns (10 columns) — is *not*
populated by this version. The R-10 mapping that decides which
``diagnostic_response.axis`` rows feed each auxiliary column is
encapsulated in :mod:`combine.subgroup_compare` (T052) and will be applied
post-joiner. Until then those columns are filled with ``None`` and the
returned rows still satisfy ``CombinedAnalysisRow`` (all 10 group-6 fields
default to ``None``).
"""

from __future__ import annotations

from dataclasses import dataclass

import json
import pandas as pd

from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

# Per data-model.md M1 / contracts/parquet_silver_combined.md.
_COMBINED_COLUMN_ORDER: tuple[str, ...] = (
    # Group 1 — Identity (6)
    "student_id",
    "name_kr",
    "on_roster",
    "section",
    "semester",
    "course_slug",
    # Group 2 — needs-map factor_scores (24 = 8 axes × 3)
    *[
        f"{axis}_{suffix}"
        for axis in STANDARD_AXIS_KEYS
        for suffix in ("raw", "z", "missing")
    ],
    # Group 3 — needs-map cluster (3)
    "cluster_id",
    "cluster_label",
    "cluster_distance",
    # Group 4 — immersio exam scores (6)
    "exam_taken",
    "total_score",
    "score_percent",
    "section_percentile",
    "cohort_percentile",
    "z_score",
    # Group 5 — immersio exam dict columns (7; serialized as JSON later)
    "chapter_correct_rates",
    "source_correct_rates",
    "difficulty_correct_rates",
    "expected_difficulty_correct_rates",
    "item_type_correct_rates",
    "interest_chapters_correct_rate",
    "aversion_chapters_correct_rate",
    # Group 6 — needs-map auxiliary group columns (10; populated in T052 era)
    "prior_readiness_q5",
    "prior_readiness_q6",
    "time_pattern_q21",
    "time_pattern_q22",
    "time_pattern_q23",
    "interest_topics_q9",
    "interest_topics_q10",
    "interest_topics_q11",
    "categorical_intent_q12",
    "categorical_intent_q13",
    # Group 7 — combined metadata (4)
    "진단응답",
    "시험응시",
    "needs_map_schema_version",
    "immersio_phase2_schema_version",
)

assert len(_COMBINED_COLUMN_ORDER) == 60, (
    f"60-column contract drift: got {len(_COMBINED_COLUMN_ORDER)}"
)

_GROUP6_AUX_COLUMNS: tuple[str, ...] = (
    "prior_readiness_q5",
    "prior_readiness_q6",
    "time_pattern_q21",
    "time_pattern_q22",
    "time_pattern_q23",
    "interest_topics_q9",
    "interest_topics_q10",
    "interest_topics_q11",
    "categorical_intent_q12",
    "categorical_intent_q13",
)

_DICT_COLUMNS: tuple[str, ...] = (
    "chapter_correct_rates",
    "source_correct_rates",
    "difficulty_correct_rates",
    "expected_difficulty_correct_rates",
    "item_type_correct_rates",
)


@dataclass(frozen=True, slots=True)
class UnmatchedCounts:
    """R-10 silent-drop audit counts produced by :func:`join_silver_phase3`.

    Fields are ≥ 0 by construction (set difference cardinalities). The
    manifest writer (T017) lifts these into the four
    ``n_unmatched_*`` / ``n_off_roster_respondents`` keys of
    ``manifest_phase3.json``.
    """

    unmatched_factor_scores: int
    unmatched_cluster_assignment: int
    unmatched_student_metrics: int
    off_roster_respondents: int


def _decode_json_dict_column(value: object) -> dict:
    """Decode a JSON-stringified dict column back into a Python dict.

    Fixture and Phase 0/2 silver may store dict columns as JSON strings
    (research §R8 — pyarrow can't represent empty struct types). When the
    upstream is already a dict (in-memory dataframe), return it as-is.
    pandas NaN (left-join filler for off-roster students) → empty dict.
    """
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, float):
        # NaN sentinel for missing left-join row.
        return {}
    if isinstance(value, str):
        if not value:
            return {}
        return json.loads(value)
    raise TypeError(
        f"unexpected dict-column value type {type(value).__name__}: {value!r}"
    )


def join_silver_phase3(
    *,
    student_master: pd.DataFrame,
    factor_scores: pd.DataFrame,
    cluster_assignment: pd.DataFrame,
    cluster_names: dict[int, str],
    student_metrics: pd.DataFrame,
    diagnostic_response: pd.DataFrame,  # noqa: ARG001 — reserved for T052 R-10
) -> tuple[pd.DataFrame, UnmatchedCounts]:
    """Left-join 5 silver inputs into the Phase 3 combined master frame.

    Args:
        student_master: ``StudentMaster`` rows (Phase 0 silver).
        factor_scores: ``FactorScoreRow`` rows (needs-map Phase B silver).
        cluster_assignment: ``ClusterAssignmentRow`` rows (needs-map Phase C).
        cluster_names: cluster_id → label dict from the SPEC-GAP-001
            ``cluster_names.json`` sidecar.
        student_metrics: ``StudentExamMetrics`` rows (immersio Phase 2 silver).
        diagnostic_response: ``DiagnosticResponse`` long-form parquet —
            currently only used for the off-roster respondent count;
            Group 6 auxiliary mapping (T052) will consume it later.

    Returns:
        ``(df, counts)`` where ``df`` is a 60-column DataFrame matching
        the contract's column order, sorted by ``student_id`` ascending,
        and ``counts`` is an :class:`UnmatchedCounts` with the four R-10
        audit fields.

    Raises:
        ValueError: If ``cluster_names`` does not cover every
            ``cluster_id`` actually present in ``cluster_assignment``
            (Fail-Fast — silently labelling clusters as ``None`` would
            mask an upstream needs-map / sidecar mismatch).
    """
    master_ids = set(student_master["student_id"])

    fs_ids = set(factor_scores["student_id"])
    ca_ids = set(cluster_assignment["student_id"])
    sm_ids = set(student_metrics["student_id"])

    # Roster-side respondent IDs — needed for cluster_assignment unmatched count
    # because non-respondents are not expected to land in cluster_assignment.
    # spec data-model.md M7 says "0 정상"; the silent-drop signal is therefore
    # *roster-respondent* set minus cluster_assignment, NOT raw master minus
    # cluster_assignment (that delta is the legitimate non-respondent group).
    respondent_master_ids: set[str]
    if "responded" in factor_scores.columns:
        respondents_in_fs = set(
            factor_scores.loc[factor_scores["responded"], "student_id"]
        )
        respondent_master_ids = master_ids & respondents_in_fs
    else:
        respondent_master_ids = master_ids & fs_ids

    counts = UnmatchedCounts(
        unmatched_factor_scores=len(master_ids - fs_ids),
        unmatched_cluster_assignment=len(respondent_master_ids - ca_ids),
        unmatched_student_metrics=len(master_ids - sm_ids),
        off_roster_respondents=len(fs_ids - master_ids),
    )

    # Validate cluster_names coverage.
    used_cluster_ids = {
        int(cid) for cid in cluster_assignment["cluster_id"].dropna().unique()
    }
    missing_labels = used_cluster_ids - set(cluster_names)
    if missing_labels:
        raise ValueError(
            f"join_silver_phase3: cluster_names sidecar missing labels for "
            f"cluster_id(s) {sorted(missing_labels)} present in cluster_assignment"
        )

    df = student_master.copy()

    # ------------------------------------------------------------------
    # Group 2 — factor_scores merge (24 columns: raw / z / missing per axis)
    # ------------------------------------------------------------------
    fs_cols_to_pull: list[str] = ["student_id"]
    for axis in STANDARD_AXIS_KEYS:
        fs_cols_to_pull.extend([axis, f"{axis}_z", f"{axis}_missing"])
    fs_subset = factor_scores[fs_cols_to_pull].copy()
    fs_subset = fs_subset.rename(columns={axis: f"{axis}_raw" for axis in STANDARD_AXIS_KEYS})
    df = df.merge(fs_subset, on="student_id", how="left")

    # For students absent from factor_scores: fill missing flags with True
    # (V2 invariant: raw is None ⇔ missing is True).
    for axis in STANDARD_AXIS_KEYS:
        flag_col = f"{axis}_missing"
        df[flag_col] = df[flag_col].fillna(True).astype(bool)

    # ------------------------------------------------------------------
    # Group 3 — cluster_assignment merge (3 columns)
    # ------------------------------------------------------------------
    ca_subset = cluster_assignment[
        ["student_id", "cluster_id", "distance_to_centroid"]
    ].rename(columns={"distance_to_centroid": "cluster_distance"})
    df = df.merge(ca_subset, on="student_id", how="left")

    # cluster_id can be NaN for non-respondents → keep nullable Int64
    df["cluster_id"] = df["cluster_id"].astype("Int64")
    df["cluster_label"] = df["cluster_id"].map(
        lambda cid: cluster_names[int(cid)] if pd.notna(cid) else None
    )

    # ------------------------------------------------------------------
    # Group 4+5 — student_metrics merge (6 score + 7 dict columns)
    # ------------------------------------------------------------------
    sm_score_cols = (
        "student_id",
        "total_score",
        "score_percent",
        "section_percentile",
        "cohort_percentile",
        "z_score",
    )
    sm_dict_cols = _DICT_COLUMNS + (
        "interest_chapters_correct_rate",
        "aversion_chapters_correct_rate",
    )
    sm_subset = student_metrics[list(sm_score_cols) + list(sm_dict_cols)].copy()
    df = df.merge(sm_subset, on="student_id", how="left")

    # exam_taken comes from student_master; ensure it's bool.
    df["exam_taken"] = df["exam_taken"].astype(bool)

    # Decode dict columns (parquet stored them as JSON strings; the joiner
    # returns native dicts so Pydantic + downstream stats can use them).
    for col in _DICT_COLUMNS:
        df[col] = df[col].map(_decode_json_dict_column)
        # Students absent from student_metrics inherit empty dict.
        df[col] = df[col].apply(lambda x: x if isinstance(x, dict) else {})

    # ------------------------------------------------------------------
    # Group 6 — auxiliary groups (10 columns; T052 hydrates per R-10)
    # ------------------------------------------------------------------
    for col in _GROUP6_AUX_COLUMNS:
        df[col] = None

    # ------------------------------------------------------------------
    # Group 7 — combined metadata (4 columns)
    # ------------------------------------------------------------------
    raw_cols = [f"{axis}_raw" for axis in STANDARD_AXIS_KEYS]
    df["진단응답"] = df[raw_cols].notna().any(axis=1)
    df["시험응시"] = df["exam_taken"]
    df["needs_map_schema_version"] = "1.1.0"
    df["immersio_phase2_schema_version"] = "0.1.0"

    # ------------------------------------------------------------------
    # Final column ordering + row sort.
    # ------------------------------------------------------------------
    df = df[list(_COMBINED_COLUMN_ORDER)]
    df = df.sort_values("student_id", ascending=True, kind="stable").reset_index(
        drop=True
    )

    # Convert pandas NA / NaT / NaN sentinels to None for Pydantic
    # downstream — Pydantic V2 only accepts None for ``Optional`` fields,
    # not pd.NA / numpy.nan. Skip dict columns (they hold real dicts) and
    # bool columns (no NaN possible: Group 2 *_missing fillna(True), Group
    # 4 exam_taken from student_master, Group 7 진단응답/시험응시 fully
    # populated). Coercing bool columns to object would break downstream
    # boolean negation (`~series` over object yields garbage), so we keep
    # their bool dtype.
    bool_cols: set[str] = {f"{axis}_missing" for axis in STANDARD_AXIS_KEYS} | {
        "on_roster",
        "exam_taken",
        "진단응답",
        "시험응시",
    }
    for col in df.columns:
        if col in _DICT_COLUMNS or col in bool_cols:
            continue
        df[col] = df[col].astype(object).where(df[col].notna(), None)

    return df, counts


__all__ = ["UnmatchedCounts", "join_silver_phase3"]
