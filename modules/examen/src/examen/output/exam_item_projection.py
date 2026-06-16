"""T047 — ExamItem projection: ExamItemDraft → immersio ExamItem sidecar.

``project_to_exam_item(draft, semester, course_slug) -> ExamItem``

Maps an ``ExamItemDraft`` (examen Gold) to the immersio ``ExamItem`` schema so
that the exam generation pipeline feeds directly into the immersio analysis
pipeline (FR-018, spec R9).

Field mapping (R9):
  draft.item_no          → item_no
  draft.chapter          → chapter
  draft.source           → source (same literals: "textbook"/"formative"/"quiz")
  draft.difficulty       → expected_difficulty:
                             "1_쉬움"   → "easy"
                             "2_보통"   → "medium"
                             "3_어려움" → "hard"
  draft.bloom            → bloom (propagated; may be None)
  str(draft.answer_no)   → answer_key  (ExamItem.answer_key is str)
  draft.text             → text
  draft.options          → distractors (list[str])
  semester (caller arg)  → semester
  course_slug (arg)      → course_slug
  points = 1.0           (ExamItem default)

``write_exam_item_projection(items, path, semester, course_slug)``

Serialises the projected list to a Gold sidecar YAML file that immersio can
load directly (``yaml.safe_load`` → ``[ExamItem(**d) for d in data]``).

Output properties (determinism):
- ``sort_keys=True`` — alphabetical key order.
- ``allow_unicode=True`` — Korean chars written as-is.
- Ends with exactly one newline.
- Byte-identical across identical-input calls.

Written atomically via ``examen.output.paths.atomic_write``.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import ExamItem, ExamItemDraft

from examen.output.determinism import dump_yaml
from examen.output.paths import atomic_write

# ---------------------------------------------------------------------------
# Difficulty mapping — ExamItemDraft → ExamItem.expected_difficulty
# ---------------------------------------------------------------------------

_DIFFICULTY_MAP: dict[str, str] = {
    "1_쉬움": "easy",
    "2_보통": "medium",
    "3_어려움": "hard",
}


def project_to_exam_item(
    draft: ExamItemDraft,
    *,
    semester: str,
    course_slug: str,
) -> ExamItem:
    """Project one ExamItemDraft to an immersio-compatible ExamItem.

    Args:
        draft: The generated exam item draft (Gold artefact from examen).
        semester: Semester code to attach (e.g. ``"2026-1"``).
        course_slug: Course slug to attach (e.g. ``"anatomy"``).

    Returns:
        A valid :class:`~paideia_shared.schemas.ExamItem` that immersio can
        join against exam result data by ``(semester, course_slug, item_no)``.
    """
    # dict-index (NOT .get) so an unexpected difficulty value (future schema
    # extension / typo) fails LOUD with KeyError instead of silently
    # projecting expected_difficulty=None.
    expected_difficulty = _DIFFICULTY_MAP[draft.difficulty]

    return ExamItem(
        semester=semester,  # type: ignore[arg-type]
        course_slug=course_slug,  # type: ignore[arg-type]
        item_no=draft.item_no,
        chapter=draft.chapter,
        source=draft.source,
        expected_difficulty=expected_difficulty,  # type: ignore[arg-type]
        bloom=draft.bloom,
        answer_key=str(draft.answer_no),
        points=1.0,
        text=draft.text,
        distractors=list(draft.options),
    )


def write_exam_item_projection(
    items: list[ExamItemDraft],
    path: Path,
    *,
    semester: str,
    course_slug: str,
) -> None:
    """Write the ExamItem projection sidecar as a deterministic yaml file.

    Immersio can load this file with::

        import yaml
        from paideia_shared.schemas import ExamItem
        data = yaml.safe_load(path.read_text("utf-8"))
        exam_items = [ExamItem(**d) for d in data]

    The file is written atomically (temp→rename) and is byte-identical
    for identical inputs (``dump_yaml`` uses ``sort_keys=True`` +
    ``allow_unicode=True``).

    Args:
        items: List of ExamItemDraft objects to project and write.
        path: Destination yaml path.  Parent directory must exist.
        semester: Semester code for the projection.
        course_slug: Course slug for the projection.
    """
    # 직렬화 먼저 — 실패 시 파일 부수효과 없음 (constitution V)
    projected = [
        project_to_exam_item(item, semester=semester, course_slug=course_slug) for item in items
    ]
    data = [ei.model_dump(mode="python") for ei in projected]
    serialized = dump_yaml(data)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, _write)


__all__ = ["project_to_exam_item", "write_exam_item_projection"]
