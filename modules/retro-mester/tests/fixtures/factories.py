"""Factory helpers returning minimal in-memory test stubs.

These stubs match the *shape* of real data structures but carry only
the minimum fields needed for Phase 1 smoke tests.  Later tasks should
expand them as real schemas are defined in ``retro_mester`` or
``paideia_shared``.

The full-shape builders near the bottom (``make_full_combined_row`` and
the scenario helpers) mirror the 60-column ``CombinedAnalysisRow`` shape
that downstream stories (US1/US2/US4) consume.  They are pure builders —
they add no assertions and touch no production code.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

# Eight needs-map factor axes (raw/z/missing triple per axis).
_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def make_combined_row(
    student_id: str = "S001",
    chapter: int = 1,
    score: float = 75.0,
    cluster: str = "A",
) -> dict:
    """Return a minimal CombinedAnalysisRow-like dict.

    Mirrors the shape of an immersio combined-phase3 analysis row.
    Only the fields most likely to be consumed by retro segment/gaps
    stages are included; expand as needed.

    Args:
        student_id: Unique student identifier string.
        chapter: Chapter number (1-based).
        score: Numeric score (0–100).
        cluster: Cluster label from combined analysis.

    Returns:
        Dict with keys matching the CombinedAnalysisRow stub schema.
    """
    return {
        "student_id": student_id,
        "chapter": chapter,
        "score": score,
        "cluster": cluster,
    }


def make_item_statistics(
    item_id: str = "Q001",
    chapter: int = 1,
    difficulty: float = 0.65,
    discrimination: float = 0.30,
    n_correct: int = 13,
    n_total: int = 20,
) -> dict:
    """Return a minimal ItemStatistics-like dict.

    Mirrors the shape of an item-level statistics record (p-value,
    discrimination index, counts).  Used by segment, gaps, and
    validity stages.

    Args:
        item_id: Item/question identifier.
        chapter: Chapter the item belongs to.
        difficulty: p-value (proportion correct, 0–1).
        discrimination: Point-biserial or D-index (-1 to 1).
        n_correct: Number of correct responses.
        n_total: Total number of respondents.

    Returns:
        Dict with keys matching the ItemStatistics stub schema.
    """
    return {
        "item_id": item_id,
        "chapter": chapter,
        "difficulty": difficulty,
        "discrimination": discrimination,
        "n_correct": n_correct,
        "n_total": n_total,
    }


def make_retro_config(
    semester: str = "2026-1",
    course: str = "anatomy",
    llm_mode: str = "off",
    prior_year: str | None = None,
) -> dict:
    """Return a minimal retro pipeline config dict.

    Mirrors the structure expected by the retro-mester config loader
    (to be implemented in later tasks).

    Args:
        semester: Semester code (e.g. "2026-1").
        course: Course slug (e.g. "anatomy").
        llm_mode: LLM mode ("off" | "subscription" | "api").
        prior_year: Optional prior-year semester code for YoY alignment.

    Returns:
        Dict with top-level retro config keys.
    """
    return {
        "semester": semester,
        "course": course,
        "llm_mode": llm_mode,
        "prior_year": prior_year,
    }


# ---------------------------------------------------------------------------
# Full-shape CombinedAnalysisRow builder (60 columns) + scenario helpers
# ---------------------------------------------------------------------------


def make_full_combined_row(
    student_id: str = "2026000001",
    semester: str = "2026-1",
    course_slug: str = "anatomy",
    chapter_correct_rates: dict[str, float] | None = None,
    cluster_label: str | None = None,
    prior_readiness_q5: str | None = None,
    prior_readiness_q6: str | None = None,
) -> dict:
    """Return a full 60-column ``CombinedAnalysisRow``-compatible dict.

    Mirrors the silver ``진단×시험결합.parquet`` row shape consumed by the
    retro segment/gaps/cause stages: dict columns are JSON-serialised
    strings, the eight needs-map axes carry a raw/z/missing triple, and
    the consistency invariants (V2–V5) hold for the defaults.

    Args:
        student_id: Canonical student identifier.
        semester: Semester code (e.g. ``"2026-1"``).
        course_slug: Course slug (e.g. ``"anatomy"``).
        chapter_correct_rates: Per-chapter correct-rate map; defaults to a
            single ``"1장"`` entry when ``None``.
        cluster_label: Cluster label; ``None`` keeps the cluster triple
            null (V4-consistent).
        prior_readiness_q5: Ordinal prior-readiness label for q5, or
            ``None``.  Pass a confirmed label here for US2 fixtures — the
            ordinal vocabulary is resolved by T014, so callers supply it
            rather than this builder guessing one.
        prior_readiness_q6: Ordinal prior-readiness label for q6, or
            ``None``.

    Returns:
        Dict with all 60 CombinedAnalysisRow columns populated.
    """
    if chapter_correct_rates is None:
        chapter_correct_rates = {"1장": 0.6}
    has_cluster = cluster_label is not None
    row: dict = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": semester,
        "course_slug": course_slug,
        "cluster_id": 1 if has_cluster else None,
        "cluster_label": cluster_label,
        "cluster_distance": 0.1 if has_cluster else None,
        "exam_taken": True,
        "total_score": 60.0,
        "score_percent": 60.0,
        "section_percentile": 50.0,
        "cohort_percentile": 50.0,
        "z_score": 0.0,
        "chapter_correct_rates": json.dumps(chapter_correct_rates),
        "source_correct_rates": json.dumps({"형성평가": 0.5}),
        "difficulty_correct_rates": json.dumps({"1": 0.7, "2": 0.5, "3": 0.3}),
        "expected_difficulty_correct_rates": json.dumps(
            {"쉬움": 0.7, "보통": 0.5, "어려움": 0.3}
        ),
        "item_type_correct_rates": json.dumps({"지식축적": 0.6, "이해": 0.5}),
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
        "prior_readiness_q5": prior_readiness_q5,
        "prior_readiness_q6": prior_readiness_q6,
        "time_pattern_q21": None,
        "time_pattern_q22": None,
        "time_pattern_q23": None,
        "interest_topics_q9": None,
        "interest_topics_q10": None,
        "interest_topics_q11": None,
        "categorical_intent_q12": None,
        "categorical_intent_q13": None,
        "진단응답": False,
        "시험응시": True,
        "needs_map_schema_version": "0.1.1",
        "immersio_phase2_schema_version": "0.1.0",
    }
    for axis in _AXES:
        row[f"{axis}_raw"] = None
        row[f"{axis}_z"] = None
        row[f"{axis}_missing"] = True
    return row


def make_zero_evidence_scenario(
    chapter: str = "3장",
    segment: str = "어려움",
) -> dict:
    """Return a (chapter × segment)-with-zero-answer-data scenario (US1).

    Builds a combined row whose ``chapter_correct_rates`` deliberately
    omits ``chapter`` so the target (chapter × segment) has no answer
    evidence — the 근거부족 (insufficient-evidence) case US1 must surface.

    Args:
        chapter: Chapter name that should have zero evidence.
        segment: Segment label paired with the zero-evidence chapter.

    Returns:
        Dict with ``chapter``, ``segment``, and a ``combined_rows`` list
        whose rows carry no correct-rate entry for ``chapter``.
    """
    # The single row only reports a *different* chapter, so the target
    # chapter has zero answer rows downstream.
    other_chapter = "1장" if chapter != "1장" else "2장"
    return {
        "chapter": chapter,
        "segment": segment,
        "combined_rows": [
            make_full_combined_row(chapter_correct_rates={other_chapter: 0.6}),
        ],
    }


def make_chapter_mismatch_scenario(
    items_chapter: str = "3장 세포",
    combined_chapter: str = "3장 세포와 조직",
) -> dict:
    """Return an items↔combined chapter-name mismatch scenario (US1 M3).

    The item statistics and the combined-analysis row reference the same
    chapter under *different* names, exercising the mismatch-detection /
    ``manifest.warnings`` path.

    Args:
        items_chapter: Chapter name as it appears in item statistics.
        combined_chapter: Chapter name as it appears in combined rows.

    Returns:
        Dict with ``items_chapter``, ``combined_chapter``, an ``items``
        list, and a ``combined_rows`` list using the mismatched names.
    """
    return {
        "items_chapter": items_chapter,
        "combined_chapter": combined_chapter,
        "items": [make_item_statistics(item_id="Q001", chapter=1)],
        "combined_rows": [
            make_full_combined_row(chapter_correct_rates={combined_chapter: 0.5}),
        ],
    }


def write_prior_forward_yaml(
    dest_dir: Path,
    *,
    corrupt: bool = False,
    missing_key: str | None = None,
    semester: str = "2025-1",
    course_slug: str = "anatomy",
    created_for_year: str = "2026-1",
    filename: str = "차년도방향.yaml",
) -> Path:
    """Write a prior-year ``차년도방향.yaml`` fixture and return its path (US4).

    Supports building healthy, corrupt, and missing-key variants so US4
    (FR-008) can exercise the prior-year audit's fail-soft handling.

    Args:
        dest_dir: Directory to write the file into (created if absent).
        corrupt: When ``True``, write malformed YAML that fails to parse.
        missing_key: When set, drop this top-level key from the otherwise
            well-formed document.
        semester: Prior semester code.
        course_slug: Course slug.
        created_for_year: The year this forward plan targets.
        filename: Output file name.

    Returns:
        Path to the written YAML file.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / filename
    if corrupt:
        # Unbalanced brackets / bad indentation → yaml.safe_load raises.
        path.write_text("schema_version: [retro-forward/1.0\n  : :\n", encoding="utf-8")
        return path

    data: dict = {
        "schema_version": "retro-forward/1.0",
        "semester": semester,
        "course_slug": course_slug,
        "created_for_year": created_for_year,
        "ledger": [
            {
                "entry_id": "entry-A",
                "semester": semester,
                "course_slug": course_slug,
                "chapter": "1장 해부학 서론",
                "target_cognitive_level": "미상",
                "segment": "전체",
                "metric": "단원 정답률",
                "baseline_value": 0.45,
                "target_value": 0.70,
                "cluster_vocab": None,
                "measure_at": "차년도 기말",
                "created_for_year": created_for_year,
            }
        ],
        "baseline": [],
    }
    if missing_key is not None:
        data.pop(missing_key, None)
    path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )
    return path
