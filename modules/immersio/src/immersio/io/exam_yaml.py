"""Exam question YAML parser producing a list of ExamItem instances."""

from __future__ import annotations

from pathlib import Path

import yaml
from paideia_shared.schemas import CourseSlug, ExamItem, SemesterCode


def parse_exam_yaml(
    path: Path, semester: SemesterCode, course_slug: CourseSlug
) -> list[ExamItem]:
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
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError(
            f"parse_exam_yaml: expected top-level mapping with 'items' key in {path}; "
            f"got {type(data).__name__}."
        )
    items_raw = data["items"]
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
        payload = {
            **entry,
            "semester": semester,
            "course_slug": course_slug,
        }
        item = ExamItem.model_validate(payload)
        if item.item_no in seen_item_nos:
            raise ValueError(
                f"parse_exam_yaml: duplicate item_no={item.item_no} in {path}."
            )
        seen_item_nos.append(item.item_no)
        items.append(item)

    return sorted(items, key=lambda it: it.item_no)
