"""T030 (RED) — unit tests for ``maieutica.assemble.difficulty``.

``assign_difficulty(item)`` finalizes the provisional ``difficulty="중"`` from
quiz_gen (T027) with a DETERMINISTIC rule (no LLM, Principle I):

- 긍정형 명칭매칭 → 하 (positive-polarity name-recall).
- 부정형 단일개념, 낮은 오답 동질성 → 중.
- 부정형 통합·고동질 오답 (options lexically near) → 상.

The frozen candidate is never mutated — a NEW candidate is returned via
``model_copy``.
"""

from __future__ import annotations

from paideia_shared.schemas import LeapExplanation, QuizItemCandidate

# Low-homogeneity options: each option introduces distinct vocabulary.
_LOW_HOMOGENEITY_OPTIONS = [
    "① 허파꽈리는 가스교환이 일어나는 호흡계통의 기본 단위이다.",
    "② 기관지는 공기가 지나가는 통로의 역할을 담당한다고 본다.",
    "③ 가로막은 수축하여 가슴안의 부피를 넓혀 들숨을 만든다.",
    "④ 코안은 들어온 공기를 데우고 가습하며 먼지를 걸러 낸다.",
    "⑤ 후두덮개는 음식이 기도로 넘어가지 않도록 막아 준다고 한다.",
]

# High-homogeneity options: heavy shared vocabulary ("허파꽈리", "교환").
_HIGH_HOMOGENEITY_OPTIONS = [
    "① 허파꽈리에서 산소와 이산화탄소가 확산으로 교환되고 있다.",
    "② 허파꽈리에서 산소와 이산화탄소가 능동수송으로 교환된다.",
    "③ 허파꽈리에서 산소와 이산화탄소가 삼투로 교환된다고 한다.",
    "④ 허파꽈리에서 산소와 이산화탄소가 여과로 교환된다고 본다.",
    "⑤ 허파꽈리에서 산소와 이산화탄소가 음세포작용으로 교환된다.",
]


def _make_candidate(
    *,
    stem_polarity: str = "부정형",
    options: list[str] | None = None,
    key_concept: str | None = "허파꽈리",
    difficulty: str = "중",
) -> QuizItemCandidate:
    leap = LeapExplanation(text="다음 개념으로 연결해 보라.", textbook_evidence=None)
    wrong = "허파꽈리는 가스교환의 장소이다."
    opts = options if options is not None else list(_LOW_HOMOGENEITY_OPTIONS)
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=1,
        week=9,
        chapter_no=8,
        chapter="8장 호흡계통",
        section="1. 허파꽈리와 가스교환",
        key_concept=key_concept,
        question_type="지식축적",
        difficulty=difficulty,
        stem_polarity=stem_polarity,
        text="다음 중 허파꽈리에 대한 설명으로 옳은 것은?",
        options=opts,
        answer_no=1,
        option_evidence=["근거"] * 5,
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=None,
        answer_explanation_combined=f"{wrong} ─ 도약 ─ {leap.text}",
        option_length_ok=True,
        explanation_length_ok=True,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


class TestAssignDifficulty:
    def test_positive_name_match_is_low(self) -> None:
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate(stem_polarity="긍정형", options=_LOW_HOMOGENEITY_OPTIONS)
        assert assign_difficulty(item).difficulty == "하"

    def test_negative_single_concept_is_medium(self) -> None:
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate(stem_polarity="부정형", options=_LOW_HOMOGENEITY_OPTIONS)
        assert assign_difficulty(item).difficulty == "중"

    def test_negative_integrative_high_homogeneity_is_high(self) -> None:
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate(stem_polarity="부정형", options=_HIGH_HOMOGENEITY_OPTIONS)
        assert assign_difficulty(item).difficulty == "상"

    def test_positive_polarity_ignores_option_homogeneity(self) -> None:
        """긍정형 short-circuits to 하 even with high-homogeneity options."""
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate(stem_polarity="긍정형", options=_HIGH_HOMOGENEITY_OPTIONS)
        assert assign_difficulty(item).difficulty == "하"

    def test_provisional_medium_replaced(self) -> None:
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate(stem_polarity="긍정형", options=_LOW_HOMOGENEITY_OPTIONS)
        assert item.difficulty == "중"  # provisional
        assert assign_difficulty(item).difficulty == "하"  # finalized

    def test_returns_new_candidate(self) -> None:
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate()
        out = assign_difficulty(item)
        assert out is not item
        assert item.difficulty == "중"  # frozen original untouched
        assert out.question_type == item.question_type  # difficulty must not touch it

    def test_deterministic_across_runs(self) -> None:
        from maieutica.assemble.difficulty import assign_difficulty

        item = _make_candidate(stem_polarity="부정형", options=_HIGH_HOMOGENEITY_OPTIONS)
        a = assign_difficulty(item)
        b = assign_difficulty(item)
        assert a.difficulty == b.difficulty
