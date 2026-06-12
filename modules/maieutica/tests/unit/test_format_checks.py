"""T029 (RED) — unit tests for ``maieutica.verify.format_checks``.

The verify stage authoritatively (re)computes the staged QuizItemCandidate's
soft flags via ``model_copy``:

- ``option_length_ok``: each option 30–50 chars incl. spaces (FR-010).
- ``explanation_length_ok``: wrong_explanation and leap.text each <=200 (FR-011).
- ``duplicate_flag``: candidates sharing a ``key_concept`` flagged (FR-008/009).
- answer_no distribution is RECORDED for the manifest — maieutica does NOT
  rebalance answer keys (that is examen FR-015's job).
"""

from __future__ import annotations

from paideia_shared.schemas import LeapExplanation, QuizItemCandidate

_GOOD_OPTIONS = [
    "① 허파꽈리는 가스교환이 일어나는 호흡계통의 기본 단위이다.",
    "② 허파꽈리 벽은 단층편평상피로 구성되어 매우 얇은 편이다.",
    "③ 허파꽈리 주위에는 모세혈관이 그물처럼 분포하고 있다고 한다.",
    "④ 허파꽈리에서는 산소와 이산화탄소가 확산으로 교환된다고 한다.",
    "⑤ 허파꽈리는 기관 안에서 직접 공기를 데우는 기능을 한다고 한다.",
]
_SHORT_OPTION = "② 기관지는 공기 통로이다."  # 15 chars — below 30


def _make_candidate(
    *,
    item_no: int = 1,
    key_concept: str | None = "허파꽈리",
    options: list[str] | None = None,
    wrong_explanation: str = "허파꽈리는 가스교환의 장소이다.",
    leap_text: str = "호흡막 두께와 확산 효율을 연결해 보라.",
    answer_no: int = 5,
    option_length_ok: bool = True,
    explanation_length_ok: bool = True,
    duplicate_flag: bool = False,
) -> QuizItemCandidate:
    leap = LeapExplanation(text=leap_text, textbook_evidence=None)
    opts = options if options is not None else list(_GOOD_OPTIONS)
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=item_no,
        week=9,
        chapter_no=8,
        chapter="8장 호흡계통",
        section="1. 허파꽈리와 가스교환",
        key_concept=key_concept,
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text="다음 중 허파꽈리에 대한 설명으로 옳지 않은 것은?",
        options=opts,
        answer_no=answer_no,
        option_evidence=["근거"] * 5,
        wrong_explanation=wrong_explanation,
        leap=leap,
        textbook_evidence=None,
        answer_explanation_combined=f"{wrong_explanation} ─ 도약 ─ {leap_text}",
        option_length_ok=option_length_ok,
        explanation_length_ok=explanation_length_ok,
        duplicate_flag=duplicate_flag,
        review_note="",
        adoption_status="생성",
        note=None,
    )


class TestCheckFormat:
    def test_option_length_ok_true_for_good(self) -> None:
        from maieutica.verify.format_checks import check_format

        out = check_format(_make_candidate())
        assert out.option_length_ok is True

    def test_option_length_ok_false_for_short_option(self) -> None:
        from maieutica.verify.format_checks import check_format

        opts = list(_GOOD_OPTIONS)
        opts[1] = _SHORT_OPTION  # 25-ish chars, below the 30 floor
        # quiz_gen set provisional True — verify must override to False.
        out = check_format(_make_candidate(options=opts, option_length_ok=True))
        assert out.option_length_ok is False

    def test_explanation_length_ok_false_for_long_wrong(self) -> None:
        from maieutica.verify.format_checks import check_format

        long_wrong = "가" * 250  # 250 chars > 200
        out = check_format(
            _make_candidate(wrong_explanation=long_wrong, explanation_length_ok=True)
        )
        assert out.explanation_length_ok is False

    def test_explanation_length_ok_false_for_long_leap(self) -> None:
        from maieutica.verify.format_checks import check_format

        out = check_format(
            _make_candidate(leap_text="나" * 250, explanation_length_ok=True)
        )
        assert out.explanation_length_ok is False

    def test_returns_new_candidate(self) -> None:
        from maieutica.verify.format_checks import check_format

        item = _make_candidate(option_length_ok=False)
        out = check_format(item)
        assert out is not item
        assert item.option_length_ok is False  # frozen original untouched


class TestDetectDuplicates:
    def test_shared_key_concept_flagged(self) -> None:
        from maieutica.verify.format_checks import detect_duplicates

        a = _make_candidate(item_no=1, key_concept="허파꽈리")
        b = _make_candidate(item_no=2, key_concept="허파꽈리")
        out = detect_duplicates([a, b])
        assert out[0].duplicate_flag is False  # first occurrence kept
        assert out[1].duplicate_flag is True

    def test_distinct_key_concept_not_flagged(self) -> None:
        from maieutica.verify.format_checks import detect_duplicates

        a = _make_candidate(item_no=1, key_concept="허파꽈리")
        b = _make_candidate(item_no=2, key_concept="기관지")
        out = detect_duplicates([a, b])
        assert all(not c.duplicate_flag for c in out)

    def test_none_key_concept_never_grouped(self) -> None:
        from maieutica.verify.format_checks import detect_duplicates

        a = _make_candidate(item_no=1, key_concept=None)
        b = _make_candidate(item_no=2, key_concept=None)
        out = detect_duplicates([a, b])
        assert all(not c.duplicate_flag for c in out)


class TestAnswerNoDistribution:
    def test_records_distribution(self) -> None:
        from maieutica.verify.format_checks import answer_no_distribution

        items = [
            _make_candidate(item_no=1, answer_no=1),
            _make_candidate(item_no=2, answer_no=1),
            _make_candidate(item_no=3, answer_no=3),
        ]
        dist = answer_no_distribution(items)
        assert dist[1] == 2
        assert dist[3] == 1
        # All five positions are present (zero for unused positions).
        assert dist[2] == 0
        assert set(dist.keys()) == {1, 2, 3, 4, 5}

    def test_no_rebalancing(self) -> None:
        """Recording the distribution must NOT change any answer_no."""
        from maieutica.verify.format_checks import answer_no_distribution

        items = [_make_candidate(item_no=i, answer_no=1) for i in range(1, 6)]
        before = [c.answer_no for c in items]
        answer_no_distribution(items)
        after = [c.answer_no for c in items]
        assert before == after == [1, 1, 1, 1, 1]
