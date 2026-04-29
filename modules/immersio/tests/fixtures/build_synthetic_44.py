"""T057 — Synthetic 44-item ItemStatistics fixture builder (US4 e2e).

Build six items, one per ``distractor_label`` rule, plus thirty-eight
"특이사항 없음" items so the cohort exercises the full label catalogue
that ``label_distractor_pattern`` (T029/T039) emits.

The fixture is consumed by:

* ``tests/integration/test_distractor_labels_e2e.py`` (T056)
* future Phase 8 orchestrator integration tests if they need a known-
  label cohort

Unit-level shape: this builder produces ``ItemStatistics`` Pydantic
instances directly, bypassing the silver→bronze→OMR pipeline (the spec
allows fixture builders to commit canonical inputs — research §R-13
extension). Two callers gain identical lists across runs because every
field is statically defined.

Usage::

    from immersio.tests.fixtures.build_synthetic_44 import (
        build_label_showcase_items,
    )
    items = build_label_showcase_items()
    assert len({it.distractor_label for it in items}) >= 6
"""

from __future__ import annotations

from typing import Final

from paideia_shared.schemas import ItemStatistics

_BASE_RESPONDERS: Final[int] = 100


def _item(
    *,
    item_no: int,
    correct_rate: float,
    discrimination: float,
    label: str,
    omit_rate: float = 0.0,
    top_distractor_rate: float | None = None,
    is_top_distractor_adjacent: bool = True,
    chapter: str = "1장. 서론",
    item_type: str = "지식축적",
    difficulty_level: int = 2,
    expected_difficulty: str = "보통",
    source: str = "교과서",
) -> ItemStatistics:
    n_resp = _BASE_RESPONDERS
    n_correct = int(round(n_resp * correct_rate))
    n_omit = int(round(n_resp * omit_rate))

    remaining = max(0.0, 1.0 - correct_rate - omit_rate)
    if top_distractor_rate is None:
        top_distractor_rate = min(0.20, remaining)
    top_distractor_rate = min(top_distractor_rate, remaining)
    other_total = max(0.0, remaining - top_distractor_rate)
    o3 = other_total / 3.0

    return ItemStatistics(
        item_no=item_no,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=1,
        item_type=item_type,
        difficulty_level=difficulty_level,
        expected_difficulty=expected_difficulty,
        source=source,
        correct_answer=1,
        n_responders=n_resp,
        n_correct=n_correct,
        n_omit=n_omit,
        correct_rate=correct_rate,
        omit_rate=omit_rate,
        discrimination_index=discrimination,
        point_biserial=discrimination,
        top_distractor_no=2,
        top_distractor_rate=top_distractor_rate,
        is_top_distractor_adjacent=is_top_distractor_adjacent,
        option_distribution={
            1: correct_rate,
            2: top_distractor_rate,
            3: o3,
            4: o3,
            5: o3,
        },
        distractor_label=label,
    )


def build_label_showcase_items() -> list[ItemStatistics]:
    """44 items where each of the 6 rule labels appears at least once.

    Mapping:
      * item_no 1 — "역변별 의심 — 출제 재검토" (D = -0.05)
      * item_no 2 — "모두 풀 수 있는 기본 문항" (correct_rate = 0.97)
      * item_no 3 — "어려운 변별 우수 문항(유지 권장)"
                      (correct_rate = 0.25, D = 0.32)
      * item_no 4 — "시간 부족 또는 포기형" (omit_rate = 0.15)
      * item_no 5 — "근접 distractor에 의한 변별 성공형"
                      (top_distractor_rate = 0.35, adjacent = True)
      * item_no 6 — "변별 기여 적음 — 차년도 교체 검토"
                      (correct_rate = 0.65, |D| < 0.10)
      * item_no 7..44 — "특이사항 없음" (mid correct rate, healthy D)
    """
    items: list[ItemStatistics] = [
        _item(
            item_no=1,
            correct_rate=0.55,
            discrimination=-0.05,
            label="역변별 의심 — 출제 재검토",
        ),
        _item(
            item_no=2,
            correct_rate=0.97,
            discrimination=0.05,
            label="모두 풀 수 있는 기본 문항",
        ),
        _item(
            item_no=3,
            correct_rate=0.25,
            discrimination=0.32,
            label="어려운 변별 우수 문항(유지 권장)",
            difficulty_level=3,
            expected_difficulty="어려움",
        ),
        _item(
            item_no=4,
            correct_rate=0.40,
            discrimination=0.15,
            label="시간 부족 또는 포기형",
            omit_rate=0.15,
        ),
        _item(
            item_no=5,
            correct_rate=0.40,
            discrimination=0.20,
            label="근접 distractor에 의한 변별 성공형",
            top_distractor_rate=0.35,
            is_top_distractor_adjacent=True,
        ),
        _item(
            item_no=6,
            correct_rate=0.65,
            discrimination=0.05,
            label="변별 기여 적음 — 차년도 교체 검토",
        ),
    ]
    for n in range(7, 45):
        items.append(
            _item(
                item_no=n,
                correct_rate=0.70,
                discrimination=0.30,
                label="특이사항 없음",
            )
        )
    return items


__all__ = ["build_label_showcase_items"]
