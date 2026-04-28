"""T048 — RED tests for `analysis/topic_alignment.py` (research §R-09).

Maps needs-map silver multiselect responses (axes ``interest_topics`` and
``categorical_intent``) to ExamItem ``chapter`` field via a curated
keyword-matching dictionary (anatomy 7장 ↔ needs-map 옵션 텍스트).

Public API:

    align_chapters_to_exam_items(
        responses: list[DiagnosticResponse-like dict],
        exam_items: list[ExamItem-like dict],
    ) -> dict[student_id, dict[axis, list[item_no]]]

Output: per-student / per-axis list of item_no whose chapter matches the
student's chosen multiselect option text. Non-matching axes / no-pick
students surface as empty lists.
"""

from __future__ import annotations

from immersio.analysis.topic_alignment import (
    CHAPTER_KEYWORDS,
    align_chapters_to_exam_items,
)


def _resp(student_id: str, axis: str, option_key: str, value_bool: bool) -> dict:
    return {
        "student_id": student_id,
        "axis": axis,
        "axis_kind": "multiselect_onehot",
        "option_key": option_key,
        "value_bool": value_bool,
    }


def _item(item_no: int, chapter: str) -> dict:
    return {"item_no": item_no, "chapter": chapter}


def test_chapter_keyword_dictionary_covers_seven_anatomy_chapters() -> None:
    expected = {
        "1장. 서론",
        "2장. 세포와 조직",
        "3장. 골격계통",
        "4장. 혈액",
        "5장. 심장혈관계통",
        "6장. 호흡기계통",
        "7장. 소화기계통",
    }
    assert expected.issubset(set(CHAPTER_KEYWORDS.keys())), (
        f"missing anatomy chapters: {expected - set(CHAPTER_KEYWORDS.keys())}"
    )


def test_align_matches_blood_topic_to_chapter_4() -> None:
    responses = [
        _resp("S001", "interest_topics", "혈액과 면역계", True),
    ]
    items = [
        _item(10, "4장. 혈액"),
        _item(20, "5장. 심장혈관계통"),
    ]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    assert out["S001"]["interest_topics"] == [10]


def test_align_supports_categorical_intent_axis() -> None:
    responses = [
        _resp("S002", "categorical_intent", "소화기관계", True),
    ]
    items = [
        _item(33, "7장. 소화기계통"),
        _item(44, "1장. 서론"),
    ]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    assert out["S002"]["categorical_intent"] == [33]


def test_align_skips_non_target_axes() -> None:
    responses = [
        _resp("S003", "study_intensity_likert", "very_high", True),
        _resp("S003", "interest_topics", "심장혈관", True),
    ]
    items = [_item(1, "5장. 심장혈관계통")]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    # Likert axis ignored; only interest_topics surfaces
    assert "study_intensity_likert" not in out.get("S003", {})
    assert out["S003"]["interest_topics"] == [1]


def test_align_returns_empty_list_when_no_match() -> None:
    responses = [
        _resp("S004", "interest_topics", "전혀 관련 없는 옵션", True),
    ]
    items = [_item(1, "1장. 서론")]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    assert out["S004"]["interest_topics"] == []


def test_align_drops_unselected_options() -> None:
    responses = [
        _resp("S005", "interest_topics", "혈액과 면역계", False),  # 미선택
    ]
    items = [_item(1, "4장. 혈액")]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    assert out["S005"]["interest_topics"] == []


def test_align_preserves_item_no_order() -> None:
    responses = [
        _resp("S006", "interest_topics", "혈액과 면역계", True),
    ]
    items = [
        _item(30, "4장. 혈액"),
        _item(10, "4장. 혈액"),
        _item(20, "4장. 혈액"),
    ]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    # Items must come back sorted by item_no for deterministic xlsx output
    assert out["S006"]["interest_topics"] == [10, 20, 30]


def test_align_handles_multiple_students_independently() -> None:
    responses = [
        _resp("S007", "interest_topics", "혈액과 면역계", True),
        _resp("S008", "interest_topics", "심장혈관", True),
    ]
    items = [
        _item(1, "4장. 혈액"),
        _item(2, "5장. 심장혈관계통"),
    ]
    out = align_chapters_to_exam_items(responses=responses, exam_items=items)
    assert out["S007"]["interest_topics"] == [1]
    assert out["S008"]["interest_topics"] == [2]


def test_align_is_deterministic_across_two_calls() -> None:
    responses = [
        _resp("S009", "interest_topics", "혈액과 면역계", True),
        _resp("S009", "categorical_intent", "소화기관계", True),
    ]
    items = [
        _item(1, "4장. 혈액"),
        _item(2, "7장. 소화기계통"),
    ]
    a = align_chapters_to_exam_items(responses=responses, exam_items=items)
    b = align_chapters_to_exam_items(responses=responses, exam_items=items)
    assert a == b
