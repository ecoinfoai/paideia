"""T012 (RED) — groundedness anchors the CORRECT ANSWER's evidence in-subsection.

Contract ``contracts/dedup_by_anchor.md`` (groundedness part):

- **G1**: when a ``subsection_chunk_id`` is supplied, ``textbook_evidence``
  anchors the CORRECT answer option's evidence — the textbook sentence that
  ``option_evidence[answer_no - 1]`` refers to — NOT ``key_concept``.
- **G2**: the anchor's line lies INSIDE the assigned subsection range and its
  ``chunk_id`` equals the slot's ``subsection_chunk_id`` (whole-chapter anchors
  are an SC-005 violation).  Two items in the same subsection whose correct
  evidences point at different lines yield different ``(chunk_id, line)`` keys.
- **G3**: a correct-answer evidence absent from the textbook (external) or equal
  to the under-fill sentinel → ``status="미확인"`` (the sentinel is never
  searched).

Backward-compat: calling ``verify_groundedness(item, idx)`` WITHOUT
``subsection_chunk_id`` must still anchor by ``key_concept`` (legacy path).
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
# Fixture: a chapter with TWO subsections (chunks), each its own line range.
# ---------------------------------------------------------------------------

_LINES = [
    "8장 호흡계통",  # 1
    "1. 허파꽈리와 가스교환",  # 2  (subsection A heading)
    "허파꽈리에서 산소와 이산화탄소가 확산으로 교환된다.",  # 3  (A body)
    "허파꽈리 벽은 단층편평상피로 구성되어 매우 얇다.",  # 4  (A body)
    "2. 기관과 기관지",  # 5  (subsection B heading)
    "기관은 연골고리로 둘러싸여 기도를 열어 둔다.",  # 6  (B body)
    "기관지는 좌우 허파로 갈라져 공기를 전달한다.",  # 7  (B body)
]

_CHUNK_A = "chunk0801"
_CHUNK_B = "chunk0802"


def _make_index() -> EvidenceIndex:
    chunks = [
        TextbookChunk(
            semester="2026-1",
            course_slug="anatomy",
            chunk_id=_CHUNK_A,
            chapter_no=8,
            chapter="8장 호흡계통",
            section="1. 허파꽈리와 가스교환",
            source_file="8장 호흡계통.txt",
            line_start=2,
            line_end=4,
            text="\n".join(_LINES[1:4]),
            removed_spans=[],
        ),
        TextbookChunk(
            semester="2026-1",
            course_slug="anatomy",
            chunk_id=_CHUNK_B,
            chapter_no=8,
            chapter="8장 호흡계통",
            section="2. 기관과 기관지",
            source_file="8장 호흡계통.txt",
            line_start=5,
            line_end=7,
            text="\n".join(_LINES[4:7]),
            removed_spans=[],
        ),
    ]
    return EvidenceIndex.from_chapter(lines=_LINES, chunks=chunks, source_file="8장 호흡계통.txt")


def _make_candidate(
    *,
    answer_no: int,
    option_evidence: list[str],
    key_concept: str | None = "허파꽈리",
) -> QuizItemCandidate:
    wrong = "정답 보기는 교재 근거와 어긋난다."
    leap = LeapExplanation(text="호흡막 두께와 확산 효율을 연결해 보라.", textbook_evidence=None)
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
        stem_polarity="긍정형",
        text="다음 중 옳은 것은?",
        options=[
            "① 보기 하나",
            "② 보기 둘",
            "③ 보기 셋",
            "④ 보기 넷",
            "⑤ 보기 다섯",
        ],
        answer_no=answer_no,
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
# G1 + G2 — correct-answer evidence, scoped to the assigned subsection
# ---------------------------------------------------------------------------


class TestAnswerAnchorScoped:
    def test_anchors_correct_answer_evidence_in_subsection(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        verbatim = _LINES[3]  # line 4, inside subsection A (chunk0801)
        item = _make_candidate(
            answer_no=2,
            option_evidence=[
                "교재: 다른 진술.",
                verbatim,  # the CORRECT option's evidence (answer_no=2)
                "교재: 또 다른 진술.",
                "교재: 네 번째.",
                "교재: 다섯 번째.",
            ],
        )
        out = verify_groundedness(item, _make_index(), subsection_chunk_id=_CHUNK_A)
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "확인"  # G1
        assert ev.chunk_id == _CHUNK_A  # G2
        assert ev.line is not None and 2 <= ev.line <= 4  # within subsection A

    def test_evidence_as_quoting_sentence_matches_line(self) -> None:
        """Two-direction match: evidence is a sentence quoting a textbook line."""
        from maieutica.verify.groundedness import verify_groundedness

        # The textbook line is a substring of the (longer) evidence sentence.
        evidence_sentence = f"교재에 따르면 {_LINES[2]} 라고 한다."
        item = _make_candidate(
            answer_no=1,
            option_evidence=[
                evidence_sentence,
                "교재: 다른 진술.",
                "교재: 셋.",
                "교재: 넷.",
                "교재: 다섯.",
            ],
        )
        out = verify_groundedness(item, _make_index(), subsection_chunk_id=_CHUNK_A)
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "확인"
        assert ev.chunk_id == _CHUNK_A
        assert ev.line == 3

    def test_two_items_same_subsection_different_lines_differ(self) -> None:
        """Granularity dedup relies on: different evidences → different anchors."""
        from maieutica.verify.groundedness import verify_groundedness

        item_a = _make_candidate(
            answer_no=1,
            option_evidence=[_LINES[2], "x", "y", "z", "w"],  # line 3
        )
        item_b = _make_candidate(
            answer_no=1,
            option_evidence=[_LINES[3], "x", "y", "z", "w"],  # line 4
        )
        idx = _make_index()
        out_a = verify_groundedness(item_a, idx, subsection_chunk_id=_CHUNK_A)
        out_b = verify_groundedness(item_b, idx, subsection_chunk_id=_CHUNK_A)
        key_a = (out_a.textbook_evidence.chunk_id, out_a.textbook_evidence.line)
        key_b = (out_b.textbook_evidence.chunk_id, out_b.textbook_evidence.line)
        assert key_a == (_CHUNK_A, 3)
        assert key_b == (_CHUNK_A, 4)
        assert key_a != key_b

    def test_scope_excludes_other_subsection(self) -> None:
        """A line that lives in subsection B is NOT found when scoped to A."""
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(
            answer_no=1,
            option_evidence=[_LINES[5], "x", "y", "z", "w"],  # line 6, in B
        )
        out = verify_groundedness(item, _make_index(), subsection_chunk_id=_CHUNK_A)
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"  # not inside the assigned subsection A


# ---------------------------------------------------------------------------
# G3 — external / sentinel → 미확인
# ---------------------------------------------------------------------------


class TestAnswerAnchorUnconfirmed:
    def test_external_evidence_unconfirmed(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(
            answer_no=1,
            option_evidence=[
                "외부지식: 미토콘드리아 전자전달계의 ATP 합성.",
                "x",
                "y",
                "z",
                "w",
            ],
        )
        out = verify_groundedness(item, _make_index(), subsection_chunk_id=_CHUNK_A)
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"

    def test_sentinel_evidence_not_searched(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        item = _make_candidate(
            answer_no=1,
            option_evidence=[
                MISSING_EVIDENCE_PLACEHOLDER,
                "x",
                "y",
                "z",
                "w",
            ],
        )
        out = verify_groundedness(item, _make_index(), subsection_chunk_id=_CHUNK_A)
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"
        assert ev.search_term is None  # sentinel never recorded/searched


# ---------------------------------------------------------------------------
# Backward-compat — no subsection_chunk_id → legacy key_concept anchoring
# ---------------------------------------------------------------------------


class TestLegacyPathIntact:
    def test_no_subsection_anchors_by_key_concept(self) -> None:
        from maieutica.verify.groundedness import verify_groundedness

        # key_concept present in chapter; the answer option evidence is external.
        item = _make_candidate(
            key_concept="허파꽈리",
            answer_no=1,
            option_evidence=["외부지식 only", "x", "y", "z", "w"],
        )
        out = verify_groundedness(item, _make_index())  # no subsection param
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "확인"
        assert ev.search_term == "허파꽈리"  # legacy: key_concept, not the option
