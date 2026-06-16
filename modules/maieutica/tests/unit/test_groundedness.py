"""T028 (RED) — unit tests for ``maieutica.verify.groundedness``.

``verify_groundedness(item, evidence_index)`` finalizes the candidate's
``textbook_evidence`` (provisionally ``None`` from quiz_gen T027) by searching
the answer-point / key concept against the CHAPTER-SCOPED evidence index:

- present in the chapter → ``status="확인"`` with chunk_id + ORIGINAL char range.
- absent / external → ``status="미확인"`` (no external knowledge silently passes).
- a ``MISSING_EVIDENCE_PLACEHOLDER`` sentinel must NOT be searched as a literal
  term (it is LLM under-fill padding) — that grounding is treated as unverified.

The frozen ``QuizItemCandidate`` is never mutated in place — a NEW candidate is
returned via ``model_copy``.
"""

from __future__ import annotations

from maieutica.generate.quiz_gen import MISSING_EVIDENCE_PLACEHOLDER
from maieutica.silver.evidence_index import EvidenceIndex
from paideia_shared.schemas import (
    LeapExplanation,
    QuizItemCandidate,
    TextbookChunk,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LINES = [
    "8장 호흡계통",
    "1. 허파꽈리와 가스교환",
    "허파꽈리에서 산소와 이산화탄소가 확산으로 교환된다.",
    "허파꽈리 벽은 단층편평상피로 구성되어 매우 얇다.",
]


def _make_index() -> EvidenceIndex:
    chunks = [
        TextbookChunk(
            semester="2026-1",
            course_slug="anatomy",
            chunk_id="chunk0800",
            chapter_no=8,
            chapter="8장 호흡계통",
            section="1. 허파꽈리와 가스교환",
            source_file="8장 호흡계통.txt",
            line_start=1,
            line_end=4,
            text="\n".join(_LINES),
            removed_spans=[],
        )
    ]
    return EvidenceIndex.from_chapter(lines=_LINES, chunks=chunks, source_file="8장 호흡계통.txt")


def _make_candidate(
    *,
    key_concept: str | None = "허파꽈리",
    option_evidence: list[str] | None = None,
) -> QuizItemCandidate:
    wrong = "허파꽈리는 가스교환의 장소이다."
    leap = LeapExplanation(text="호흡막 두께와 확산 효율을 연결해 보라.", textbook_evidence=None)
    if option_evidence is None:
        option_evidence = [
            "교재: 허파꽈리는 가스교환의 기본 단위.",
            "교재: 단층편평상피.",
            "교재: 모세혈관 분포.",
            "교재: 확산 교환.",
            "틀린 진술: 기관이 공기를 데움.",
        ]
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
        difficulty="중",
        stem_polarity="부정형",
        text="다음 중 허파꽈리에 대한 설명으로 옳지 않은 것은?",
        options=[
            "① 허파꽈리는 가스교환이 일어나는 호흡계통의 기본 단위이다.",
            "② 허파꽈리 벽은 단층편평상피로 구성되어 매우 얇은 편이다.",
            "③ 허파꽈리 주위에는 모세혈관이 그물처럼 분포하고 있다.",
            "④ 허파꽈리에서는 산소와 이산화탄소가 확산으로 교환된다.",
            "⑤ 허파꽈리는 기관 안에서 직접 공기를 데우는 기능을 한다.",
        ],
        answer_no=5,
        option_evidence=option_evidence,
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVerifyGroundedness:
    def test_present_concept_confirmed(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="허파꽈리")
        out = verify_groundedness(item, _make_index())
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "확인"
        assert ev.chunk_id == "chunk0800"
        assert ev.search_term == "허파꽈리"

    def test_char_range_anchors_original_text(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        original = "\n".join(_LINES)
        item = _make_candidate(key_concept="허파꽈리")
        out = verify_groundedness(item, _make_index())
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.char_start is not None and ev.char_end is not None
        assert original[ev.char_start : ev.char_end] == ev.found_text

    def test_absent_concept_unconfirmed(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="미토콘드리아전자전달계")
        out = verify_groundedness(item, _make_index())
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"
        assert ev.chunk_id is None
        assert ev.search_term == "미토콘드리아전자전달계"  # preserved on miss

    def test_none_key_concept_unconfirmed(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept=None)
        out = verify_groundedness(item, _make_index())
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"

    def test_sentinel_key_concept_not_searched_literally(self) -> None:
        """A sentinel key_concept must not be searched as a literal term."""
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept=MISSING_EVIDENCE_PLACEHOLDER)
        out = verify_groundedness(item, _make_index())
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"
        # The sentinel must not be recorded as the search term.
        assert ev.search_term is None

    def test_returns_new_candidate_original_unchanged(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="허파꽈리")
        out = verify_groundedness(item, _make_index())
        assert out is not item
        assert item.textbook_evidence is None  # frozen original untouched

    def test_deterministic_across_runs(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="허파꽈리")
        a = verify_groundedness(item, _make_index())
        b = verify_groundedness(item, _make_index())
        assert a.model_dump() == b.model_dump()


class TestLeapGroundedness:
    """T038: ``leap.textbook_evidence`` is also grounded (FR-012)."""

    def test_leap_evidence_confirmed_for_in_range_concept(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="허파꽈리")
        out = verify_groundedness(item, _make_index())
        leap_ev = out.leap.textbook_evidence
        assert leap_ev is not None
        assert leap_ev.status == "확인"
        assert leap_ev.chunk_id == "chunk0800"

    def test_leap_evidence_unconfirmed_for_external_concept(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="미토콘드리아전자전달계")
        out = verify_groundedness(item, _make_index())
        leap_ev = out.leap.textbook_evidence
        assert leap_ev is not None
        assert leap_ev.status == "미확인"

    def test_leap_evidence_unconfirmed_for_none_concept(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept=None)
        out = verify_groundedness(item, _make_index())
        leap_ev = out.leap.textbook_evidence
        assert leap_ev is not None
        assert leap_ev.status == "미확인"

    def test_leap_sentinel_not_searched_literally(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept=MISSING_EVIDENCE_PLACEHOLDER)
        out = verify_groundedness(item, _make_index())
        leap_ev = out.leap.textbook_evidence
        assert leap_ev is not None
        assert leap_ev.status == "미확인"
        assert leap_ev.search_term is None

    def test_leap_text_and_combined_form_preserved(self) -> None:
        """Grounding the leap must not alter leap.text or the V4 combined fold."""
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="허파꽈리")
        out = verify_groundedness(item, _make_index())
        assert out.leap.text == item.leap.text
        assert (
            out.answer_explanation_combined == f"{out.wrong_explanation} ─ 도약 ─ {out.leap.text}"
        )

    def test_original_leap_evidence_untouched(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(key_concept="허파꽈리")
        verify_groundedness(item, _make_index())
        assert item.leap.textbook_evidence is None  # frozen original untouched
