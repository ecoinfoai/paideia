"""Factory helpers returning minimal in-memory test stubs.

These stubs match the *shape* of real data structures but carry only
the minimum fields needed for Phase 1 smoke tests.  Later tasks should
expand them as real schemas are defined in ``retro_mester`` or
``paideia_shared``.
"""

from __future__ import annotations


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
