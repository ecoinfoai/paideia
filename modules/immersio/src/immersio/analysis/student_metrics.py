"""Per-student exam performance metrics (T051, FR-013-018, R-12).

Build one ``StudentExamMetrics`` row per student in the master roster:

* Takers (``exam_taken=True``) get total_score / score_percent / Hazen
  percentile (section + cohort) / population z-score / per-chapter,
  per-source, per-difficulty, per-expected_difficulty, per-item_type
  correct-rate dicts.
* Absents (``exam_taken=False``) get every score field as ``None`` so
  the StudentExamMetrics V1 invariant holds.
* When ``needs_map_responses`` is supplied (Phase 1 → Phase 2 join, R-09),
  the interest / aversion chapter correct rates are filled by routing
  ``interest_topics`` / ``categorical_intent`` multiselect picks through
  ``analysis.topic_alignment.align_chapters_to_exam_items``.

Determinism: the output list is sorted by ``student_id`` so silver
parquet + xlsx 학생성적 sheet rows are reproducible.

Hazen percentile (research §R-12): ``(n_below + 0.5 * n_equal) / n_total
* 100``. Z-score: ``(score - mean) / pop_sd`` with ddof=0; ``pop_sd ==
0`` falls through to ``None``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from paideia_shared.schemas import StudentExamMetrics

from .topic_alignment import align_chapters_to_exam_items


def _hazen_percentile(scores: np.ndarray, target: float) -> float:
    """Hazen-style percentile with half-split tie handling."""
    if scores.size == 0:
        return 0.0
    n_below = int((scores < target).sum())
    n_equal = int((scores == target).sum())
    return (n_below + 0.5 * n_equal) / scores.size * 100.0


def _per_taker_score(
    exam_result_df: pd.DataFrame, student_id: str
) -> tuple[float, dict[int, bool]]:
    """Return ``(total_score, {item_no: is_correct})`` for one student."""
    rows = exam_result_df[exam_result_df["student_id"] == student_id]
    correct_map: dict[int, bool] = {}
    total = 0
    for _, r in rows.iterrows():
        ok = bool(r.get("is_correct", False))
        correct_map[int(r["item_no"])] = ok
        total += int(ok)
    return float(total), correct_map


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _build_metadata_rates(
    correct_map: dict[int, bool],
    items_by_no: Mapping[int, Mapping[str, object]],
    field: str,
) -> dict:
    """Aggregate ``correct_map`` by ``items_by_no[*][field]`` value."""
    by_value: dict[object, list[bool]] = defaultdict(list)
    for item_no, ok in correct_map.items():
        item = items_by_no.get(item_no)
        if item is None:
            continue
        value = item.get(field)
        if value is None:
            continue
        by_value[value].append(ok)
    return {key: _rate(sum(flags), len(flags)) for key, flags in by_value.items()}


def _interest_aversion_rates(
    sid: str,
    correct_map: dict[int, bool],
    aligned: dict[str, dict[str, list[int]]],
) -> tuple[float | None, float | None]:
    student_axes = aligned.get(sid)
    if not student_axes:
        return None, None
    interest_items = student_axes.get("interest_topics", [])
    aversion_items = student_axes.get("categorical_intent", [])

    def _rate_for(item_nos: Sequence[int]) -> float | None:
        flags = [correct_map[no] for no in item_nos if no in correct_map]
        if not flags:
            return None
        return sum(flags) / len(flags)

    return _rate_for(interest_items), _rate_for(aversion_items)


def compute_student_metrics(
    *,
    exam_result_df: pd.DataFrame,
    student_master_df: pd.DataFrame,
    exam_items: Iterable[Mapping[str, object]],
    needs_map_responses: Iterable[Mapping[str, object]] | None = None,
) -> list[StudentExamMetrics]:
    """Build the per-student StudentExamMetrics list for the cohort.

    Args:
        exam_result_df: One row per (student, item) response. Required
            columns: ``student_id``, ``item_no``, ``is_correct`` (bool).
        student_master_df: One row per enrolled student. Required
            columns: ``student_id``, ``exam_taken`` (bool); optional
            ``name_kr``, ``section``.
        exam_items: Iterable of dict-like ExamItem rows; required keys
            ``item_no``, ``chapter``, ``source``, ``difficulty_level``,
            ``expected_difficulty``, ``item_type``.
        needs_map_responses: Optional needs-map silver multiselect rows
            for the interest / aversion chapter join. ``None`` ⇒ both
            join columns left as ``None`` (FR-016/017 silent fallback
            with manifest.notes recorded by the orchestrator).

    Returns:
        ``list[StudentExamMetrics]`` sorted by ``student_id``. Length
        matches ``student_master_df`` (1 row per master record, includes
        absents).

    Raises:
        ValueError: When ``student_master_df`` is empty.
    """
    if student_master_df.empty:
        raise ValueError("compute_student_metrics: student_master_df is empty")
    if "exam_taken" not in student_master_df.columns:
        raise ValueError("compute_student_metrics: student_master_df missing 'exam_taken' column")

    items_list = [dict(it) for it in exam_items]
    items_by_no: dict[int, Mapping[str, object]] = {int(it["item_no"]): it for it in items_list}

    semester = "2026-1"
    course_slug = "anatomy"

    # Pre-compute taker scores for percentile / z-score over the responder
    # population (결시 제외 per R-04).
    taker_scores: dict[str, float] = {}
    correct_maps: dict[str, dict[int, bool]] = {}
    for _, m in student_master_df.iterrows():
        sid = str(m["student_id"])
        if not bool(m["exam_taken"]):
            continue
        score, correct_map = _per_taker_score(exam_result_df, sid)
        taker_scores[sid] = score
        correct_maps[sid] = correct_map

    cohort_arr = np.array(list(taker_scores.values()), dtype=float)
    pop_mean = float(cohort_arr.mean()) if cohort_arr.size > 0 else 0.0
    pop_sd = float(cohort_arr.std(ddof=0)) if cohort_arr.size > 0 else 0.0
    max_score = float(len(items_list))

    # Section-scoped score distribution for in-section percentile.
    section_scores: dict[str, np.ndarray] = {}
    for _, m in student_master_df.iterrows():
        if not bool(m["exam_taken"]):
            continue
        sid = str(m["student_id"])
        section = m.get("section")
        if pd.isna(section) or section is None:
            continue
        section_scores.setdefault(str(section), [])  # type: ignore[arg-type]
        section_scores[str(section)].append(taker_scores[sid])  # type: ignore[union-attr]
    section_arrays: dict[str, np.ndarray] = {
        sec: np.array(vals, dtype=float) for sec, vals in section_scores.items()
    }

    # needs-map alignment
    aligned: dict[str, dict[str, list[int]]] = {}
    if needs_map_responses is not None:
        aligned = align_chapters_to_exam_items(responses=needs_map_responses, exam_items=items_list)

    out: list[StudentExamMetrics] = []
    for _, m in student_master_df.iterrows():
        sid = str(m["student_id"])
        name_kr = m.get("name_kr") if not pd.isna(m.get("name_kr")) else None
        section_raw = m.get("section")
        section = str(section_raw) if section_raw is not None and not pd.isna(section_raw) else None
        exam_taken = bool(m["exam_taken"])

        if not exam_taken:
            out.append(
                StudentExamMetrics(
                    student_id=sid,
                    name_kr=name_kr,
                    section=section,
                    semester=semester,
                    course_slug=course_slug,
                    exam_taken=False,
                )
            )
            continue

        score = taker_scores[sid]
        correct_map = correct_maps[sid]
        score_percent = score / max_score * 100.0 if max_score > 0 else 0.0

        cohort_pct = _hazen_percentile(cohort_arr, score)
        section_arr = section_arrays.get(section) if section else None
        section_pct = (
            _hazen_percentile(section_arr, score) if section_arr is not None else cohort_pct
        )

        z_score = (score - pop_mean) / pop_sd if pop_sd > 0 else None

        chapter_rates = _build_metadata_rates(correct_map, items_by_no, "chapter")
        source_rates = _build_metadata_rates(correct_map, items_by_no, "source")
        difficulty_rates = _build_metadata_rates(correct_map, items_by_no, "difficulty_level")
        expected_rates = _build_metadata_rates(correct_map, items_by_no, "expected_difficulty")
        item_type_rates = _build_metadata_rates(correct_map, items_by_no, "item_type")

        interest_rate, aversion_rate = _interest_aversion_rates(sid, correct_map, aligned)

        out.append(
            StudentExamMetrics(
                student_id=sid,
                name_kr=name_kr,
                section=section,
                semester=semester,
                course_slug=course_slug,
                exam_taken=True,
                total_score=score,
                score_percent=score_percent,
                section_percentile=section_pct,
                cohort_percentile=cohort_pct,
                z_score=z_score,
                chapter_correct_rates={str(k): v for k, v in chapter_rates.items()},
                source_correct_rates={str(k): v for k, v in source_rates.items()},
                difficulty_correct_rates={int(k): v for k, v in difficulty_rates.items()},
                expected_difficulty_correct_rates={str(k): v for k, v in expected_rates.items()},
                item_type_correct_rates={str(k): v for k, v in item_type_rates.items()},
                interest_chapters_correct_rate=interest_rate,
                aversion_chapters_correct_rate=aversion_rate,
            )
        )

    out.sort(key=lambda m: m.student_id)
    return out


__all__ = ["compute_student_metrics"]
