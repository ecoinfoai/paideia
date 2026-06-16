"""Exam question YAML parser producing a list of ExamItem instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from paideia_shared.schemas import CourseSlug, ExamItem, SemesterCode

# Korean → English vocabulary mapping for production exam YAMLs.
# Spec form uses English keys directly; production form uses Korean.
_KOREAN_FIELD_MAP = {
    "번호": "item_no",
    "챕터": "chapter",
    "문제": "text",
    "정답": "answer_key",
}
_SOURCE_KO_TO_EN = {
    "교과서": "textbook",
    "형성평가": "formative",
    "퀴즈": "quiz",
}
_DIFFICULTY_KO_TO_EN = {
    "쉬움": "easy",
    "보통": "medium",
    "어려움": "hard",
}
# Production-only narrative fields stripped before validation.
_KOREAN_STRIP_KEYS = (
    "주차",
    "핵심설명",
    "추가설명",
    "문제유형",
    "난이도",
)


def _normalize_entry_korean(entry: dict[str, Any]) -> dict[str, Any]:
    """Translate a Korean-keyed exam entry to the English ExamItem schema.

    Production exam YAMLs (e.g. ``실제_출제문제.yaml``) use Korean field
    names plus narrative fields not part of the spec contract. This helper
    maps the names, picks distractors from `보기1`..`보기5`, translates
    Korean enum values, and strips narrative-only fields.
    """
    payload: dict[str, Any] = {}
    for ko_key, en_key in _KOREAN_FIELD_MAP.items():
        if ko_key in entry:
            payload[en_key] = entry[ko_key]
    if "정답" in entry:
        payload["answer_key"] = str(entry["정답"])
    distractors: list[str] = []
    for n in (1, 2, 3, 4, 5):
        key = f"보기{n}"
        if key in entry and entry[key] is not None:
            distractors.append(str(entry[key]))
    if distractors:
        payload["distractors"] = distractors
    if (src_kr := entry.get("출처")) and src_kr in _SOURCE_KO_TO_EN:
        payload["source"] = _SOURCE_KO_TO_EN[src_kr]
    if (diff_kr := entry.get("예상_난이도")) and diff_kr in _DIFFICULTY_KO_TO_EN:
        payload["expected_difficulty"] = _DIFFICULTY_KO_TO_EN[diff_kr]
    # Pass through any English keys already present (spec form mixed-in).
    for key in (
        "item_no",
        "chapter",
        "text",
        "answer_key",
        "distractors",
        "source",
        "expected_difficulty",
        "bloom",
        "points",
    ):
        if key in entry and key not in payload:
            payload[key] = entry[key]
    return payload


def parse_exam_yaml(path: Path, semester: SemesterCode, course_slug: CourseSlug) -> list[ExamItem]:
    """Parse the exam-question YAML into validated ExamItem instances.

    Args:
        path: Path to the exam YAML.
        semester: SemesterCode to attach to each ExamItem.
        course_slug: CourseSlug to attach to each ExamItem.

    Returns:
        List of ExamItem instances ordered by item_no.

    Raises:
        TypeError: If path is not a pathlib.Path.
        FileNotFoundError: If the file is missing.
        ValueError: If the document layout is malformed or item_no duplicates exist.
        pydantic.ValidationError: If any item fails the ExamItem contract.
    """
    if not isinstance(path, Path):
        raise TypeError(f"parse_exam_yaml: expected Path, got {type(path).__name__}.")

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    # T069 — accept both root layouts (production yamls land as a bare list
    # of question dicts; the mapping-with-`items` form is the spec contract
    # form used by fixtures). Both layouts must yield the same downstream
    # ExamItem list (Constitution III — variability via configuration).
    if isinstance(data, list):
        items_raw: list = data
    elif isinstance(data, dict) and "items" in data:
        items_raw = data["items"]
    else:
        raise ValueError(
            f"parse_exam_yaml: expected either a top-level list or a mapping "
            f"with 'items' key in {path}; got {type(data).__name__}."
        )
    if not isinstance(items_raw, list) or not items_raw:
        raise ValueError(
            f"parse_exam_yaml: 'items' must be a non-empty list in {path}; "
            f"got {type(items_raw).__name__}."
        )

    seen_item_nos: list[int] = []
    items: list[ExamItem] = []
    for entry in items_raw:
        if not isinstance(entry, dict):
            raise ValueError(
                f"parse_exam_yaml: each item must be a mapping in {path}; "
                f"got {type(entry).__name__}."
            )
        # Detect Korean production form by the presence of `번호`/`문제`,
        # otherwise treat as the spec contract form (English keys).
        if "번호" in entry or "문제" in entry:
            normalized = _normalize_entry_korean(entry)
        else:
            normalized = {k: v for k, v in entry.items() if k not in _KOREAN_STRIP_KEYS}
        payload = {
            **normalized,
            "semester": semester,
            "course_slug": course_slug,
        }
        item = ExamItem.model_validate(payload)
        if item.item_no in seen_item_nos:
            raise ValueError(f"parse_exam_yaml: duplicate item_no={item.item_no} in {path}.")
        seen_item_nos.append(item.item_no)
        items.append(item)

    return sorted(items, key=lambda it: it.item_no)
