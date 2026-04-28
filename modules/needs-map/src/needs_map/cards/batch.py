"""Batch card generation (T104, FR-019/021/022).

Walks the union of student_master and factor_scores rows (sorted by student_id
ascending — determinism axis 2) and writes one PDF per student to
``output_dir/cards/``. Missing factor_scores → "진단 미응답" card (FR-021,
adversary H-6 — never silently skipped).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from paideia_shared.schemas import ClusterReport, FreeTextRow

from ..llm.fallback import LLMCallTracker
from .coaching import compose_coaching
from .layout import render_card_pdf
from .radar import render_radar_png

if TYPE_CHECKING:
    import instructor

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


def _resolve_weak_axis(student_row: pd.Series) -> str | None:
    """Return the axis with the lowest substantive z-score; None if all NaN."""
    z_scores: dict[str, float] = {}
    for axis in _AXES:
        z = student_row.get(f"{axis}_z")
        if z is not None and not pd.isna(z):
            z_scores[axis] = float(z)
    if not z_scores:
        return None
    return min(z_scores, key=lambda k: z_scores[k])


def _categories_for_student(
    free_text_rows: list[FreeTextRow], student_id: str
) -> list[str]:
    cats: list[str] = []
    for row in free_text_rows:
        if row.student_id != student_id:
            continue
        for c in row.matched_categories:
            if c not in cats:
                cats.append(c)
    return cats


def _compute_cohort_means_raw(
    factor_scores_df: pd.DataFrame,
) -> dict[str, float | None]:
    """Per-axis cohort mean on the raw 1-7 scale (FR-021).

    Computes ``np.nanmean`` axis-by-axis so missing data on one axis does
    not contaminate the others. Returns ``None`` when an axis is fully
    NaN across the cohort (rendered as a gap on the radar's dotted ring
    instead of a misleading zero).
    """
    import numpy as np

    means: dict[str, float | None] = {}
    for axis in _AXES:
        if axis not in factor_scores_df.columns:
            means[axis] = None
            continue
        col = factor_scores_df[axis]
        if col.dropna().empty:
            means[axis] = None
            continue
        means[axis] = float(np.nanmean(col.to_numpy(dtype=float)))
    return means


def _count_responders(factor_scores_df: pd.DataFrame) -> int:
    """Cohort size for the radar legend.

    Uses ``responded`` boolean column when present (Phase B builds this);
    falls back to row count for safety.
    """
    if "responded" in factor_scores_df.columns:
        return int(factor_scores_df["responded"].astype(bool).sum())
    return int(len(factor_scores_df))


def _mask_student_id(student_id: str) -> str:
    """Mask a 10-digit student id for the radar legend (e.g. ``2026****01``)."""
    if len(student_id) >= 6:
        return f"{student_id[:4]}****{student_id[-2:]}"
    return student_id


def generate_all_cards(
    *,
    factor_scores_df: pd.DataFrame,
    student_master_df: pd.DataFrame,
    cluster_report: ClusterReport | None,
    free_text_rows: list[FreeTextRow],
    group_means: dict[str, float],
    semester: str,
    course_name_kr: str,
    output_dir: Path,
    created_at_utc: str,
    llm_client: instructor.Instructor | None,
    llm_tracker: LLMCallTracker,
    llm_model: str,
    llm_retries: int,
) -> int:
    """Generate one PDF per student into ``output_dir``. Returns count.

    Iterates the union of student_master.student_id and factor_scores.student_id
    sorted ascending. Off-roster respondents get a normal card; roster
    non-responders get the "진단 미응답" card (FR-021).

    v0.1.1 (T042): the radar receives ``student_raw_scores`` (raw 1-7
    likert values directly from FactorScoreRow) and a per-axis cohort
    mean ``cohort_means_raw`` computed once via ``np.nanmean`` so each
    card render reads from the same cohort baseline. The legacy
    ``group_means`` argument (z-space) is kept for back-compat but no
    longer feeds the radar.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    _ = group_means  # legacy z-space param retained for caller compatibility

    cohort_means_raw = _compute_cohort_means_raw(factor_scores_df)
    cohort_n = _count_responders(factor_scores_df)

    sm_lookup = student_master_df.set_index("student_id").to_dict(orient="index")
    fs_lookup = factor_scores_df.set_index("student_id").to_dict(orient="index")
    cluster_by_student: dict[str, int] = {}
    if cluster_report is not None:
        cluster_by_student = {row.student_id: row.cluster_id for row in cluster_report.rows}

    cluster_sizes: dict[int, int] = {}
    if cluster_report is not None:
        for row in cluster_report.rows:
            cluster_sizes[row.cluster_id] = cluster_sizes.get(row.cluster_id, 0) + 1

    all_ids = sorted(set(sm_lookup.keys()) | set(fs_lookup.keys()))

    count = 0
    for sid in all_ids:
        master = sm_lookup.get(sid, {})
        fs_row = fs_lookup.get(sid)
        section_raw = master.get("section") if master else None
        section = (
            None
            if isinstance(section_raw, float) and pd.isna(section_raw)
            else section_raw
        )
        on_roster = bool(master.get("on_roster")) if master else False
        responded = fs_row is not None
        name_kr = master.get("name_kr") if master else None
        if isinstance(name_kr, float) and pd.isna(name_kr):
            name_kr = ""

        if responded:
            student_raw: dict[str, float | None] = {}
            for axis in _AXES:
                val = fs_row.get(axis)  # type: ignore[union-attr]
                student_raw[axis] = (
                    None if val is None or (isinstance(val, float) and pd.isna(val)) else float(val)
                )
            weak_axis = _resolve_weak_axis(pd.Series(fs_row))  # type: ignore[arg-type]
            cluster_id = cluster_by_student.get(sid)
            cluster_label = (
                cluster_report.cluster_names.get(cluster_id)
                if cluster_report is not None and cluster_id is not None
                else None
            )
            cluster_size = cluster_sizes.get(cluster_id) if cluster_id is not None else None
            distance_z = None
            if cluster_report is not None:
                for row in cluster_report.rows:
                    if row.student_id == sid and row.distance_to_centroid is not None:
                        distance_z = float(row.distance_to_centroid)
                        break
            categories = _categories_for_student(free_text_rows, sid)
        else:
            student_raw = dict.fromkeys(_AXES)
            weak_axis = None
            cluster_label = None
            cluster_size = None
            distance_z = None
            categories = []

        coaching_text, coaching_source = compose_coaching(
            cluster_label=cluster_label,
            weak_axis=weak_axis,
            responded=responded,
            on_roster=on_roster,
            student_id=sid,
            student_name=str(name_kr) if name_kr else "",
            llm_client=llm_client,
            llm_tracker=llm_tracker,
            llm_model=llm_model,
            llm_retries=llm_retries,
        )

        radar_png = render_radar_png(
            student_raw_scores=student_raw,
            cohort_means_raw=cohort_means_raw,
            student_id_short=sid,
            cohort_n=cohort_n,
        )

        pdf_bytes = render_card_pdf(
            student_id=sid,
            student_name=str(name_kr) if name_kr else None,
            section=section if isinstance(section, str) else None,
            semester=semester,
            course_name_kr=course_name_kr,
            cluster_label=cluster_label,
            cluster_size=cluster_size,
            distance_z=distance_z,
            free_text_categories=categories,
            coaching_text=coaching_text,
            coaching_source=coaching_source,
            radar_png=radar_png,
            created_at_utc=created_at_utc,
        )
        (output_dir / f"{sid}.pdf").write_bytes(pdf_bytes)
        count += 1
    return count
