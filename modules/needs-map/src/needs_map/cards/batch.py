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
    "motivation",
    "anxiety",
    "self_efficacy",
    "interest",
    "prior_knowledge",
    "life_context",
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
    """
    output_dir.mkdir(parents=True, exist_ok=True)

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
            student_z = {axis: fs_row.get(f"{axis}_z") for axis in _AXES}  # type: ignore[union-attr]
            cleaned_z: dict[str, float | None] = {}
            for axis, val in student_z.items():
                cleaned_z[axis] = (
                    None if val is None or (isinstance(val, float) and pd.isna(val)) else float(val)
                )
            axes_present = [a for a, v in cleaned_z.items() if v is not None]
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
            cleaned_z = dict.fromkeys(_AXES)
            axes_present = []
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
            cleaned_z, group_means, axes_present=axes_present
        )

        pdf_bytes = render_card_pdf(
            student_id=sid,
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
