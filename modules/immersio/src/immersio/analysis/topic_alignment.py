"""needs-map multiselect ↔ ExamItem 챕터 alignment (T050, FR-016/017, R-09).

needs-map silver 의 multiselect 옵션 텍스트(예: '혈액과 면역계')는 시험 챕터
명(예: '4장. 혈액')과 정확 일치하지 않는다. 본 모듈은 코드 상수
``CHAPTER_KEYWORDS`` (anatomy 7장 vs needs-map 옵션 텍스트) 사전을 기반으로
키워드 매칭하여 student × axis × item_no 정렬을 만든다.

Public surface:

* ``CHAPTER_KEYWORDS`` — ``{chapter_name: tuple[option_keyword, ...]}``
* ``align_chapters_to_exam_items(responses, exam_items)`` —
  ``{student_id: {axis: list[item_no]}}``

v2 외부화 트리거 (research §R-09):
1. 두 번째 과목(예: microbio) 분석 시작
2. anatomy 챕터 명칭 학기 중 변경
3. needs-map multiselect 옵션 텍스트 변경

위 셋 중 하나 충족 시 후속 spec 으로 yaml 외부화 (Constitution III v1 한정 절충).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

# Anatomy 7 chapter ↔ needs-map multiselect option keyword dictionary.
# Keys = canonical ExamItem.chapter strings produced by the operator's
# exam YAML. Values = ordered list of substrings that must appear in the
# needs-map option text for a positive match. Matching is case-sensitive
# Korean — needs-map preserves user-facing option labels verbatim.
CHAPTER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "1장. 서론": ("서론", "기초", "항상성", "homeostasis"),
    "2장. 세포와 조직": ("세포", "조직"),
    "3장. 골격계통": ("골격", "근골격", "뼈"),
    "4장. 혈액": ("혈액", "면역"),
    "5장. 심장혈관계통": ("심장", "혈관", "순환", "심혈관"),
    "6장. 호흡기계통": ("호흡", "폐"),
    "7장. 소화기계통": ("소화", "위장", "소화기"),
}

_TARGET_AXES: frozenset[str] = frozenset({"interest_topics", "categorical_intent"})


def _option_matches_chapter(option_text: str, chapter: str) -> bool:
    """True iff any keyword of ``chapter`` is a substring of ``option_text``."""
    keywords = CHAPTER_KEYWORDS.get(chapter)
    if not keywords:
        return False
    return any(kw in option_text for kw in keywords)


def align_chapters_to_exam_items(
    *,
    responses: Iterable[Mapping[str, object]],
    exam_items: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, list[int]]]:
    """Map needs-map multiselect picks → matching ExamItem.item_no list.

    Args:
        responses: Iterable of dict-like rows mirroring
            ``DiagnosticResponse`` shape — required keys: ``student_id``,
            ``axis``, ``axis_kind``, ``option_key``, ``value_bool``. Only
            rows with ``axis_kind == "multiselect_onehot"``,
            ``axis in {interest_topics, categorical_intent}``, and
            ``value_bool is True`` participate.
        exam_items: Iterable of dict-like rows mirroring ``ExamItem`` —
            required keys: ``item_no``, ``chapter``.

    Returns:
        ``{student_id: {axis: sorted list of item_no}}``. Students whose
        multiselect picks match no chapter still surface with empty
        lists for the axes they answered. Item lists are sorted ascending
        for deterministic downstream xlsx output.
    """
    items_by_chapter: dict[str, list[int]] = defaultdict(list)
    for item in exam_items:
        ch = item.get("chapter")
        no = item.get("item_no")
        if isinstance(ch, str) and isinstance(no, int):
            items_by_chapter[ch].append(no)
    for chapter in items_by_chapter:
        items_by_chapter[chapter].sort()

    out: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    seen: dict[tuple[str, str], set[int]] = defaultdict(set)

    for r in responses:
        if r.get("axis_kind") != "multiselect_onehot":
            continue
        axis = r.get("axis")
        if axis not in _TARGET_AXES:
            continue
        sid = r.get("student_id")
        option_text = r.get("option_key")
        if (
            not isinstance(sid, str)
            or not isinstance(option_text, str)
            or not isinstance(axis, str)
        ):
            continue
        # Ensure (student, axis) key exists for every observed multiselect
        # row (selected or not) so an explicit empty list signals
        # "respondent had nothing aligned" rather than "respondent absent".
        out[sid][axis]  # noqa: B018 — defaultdict autovivification
        if not r.get("value_bool"):
            continue
        for chapter, item_nos in items_by_chapter.items():
            if _option_matches_chapter(option_text, chapter):
                for no in item_nos:
                    if no not in seen[(sid, axis)]:
                        seen[(sid, axis)].add(no)
                        out[sid][axis].append(no)

    # Sort and freeze defaultdict → plain dicts for deterministic equality
    return {
        sid: {axis: sorted(nos) for axis, nos in axes.items()}
        for sid, axes in out.items()
    }


__all__ = ["CHAPTER_KEYWORDS", "align_chapters_to_exam_items"]
