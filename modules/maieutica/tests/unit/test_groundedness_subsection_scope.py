"""T025 (RED) — SC-005 lock: the answer anchor stays INSIDE its subsection.

Contract ``contracts/dedup_by_anchor.md`` (groundedness, US3 / SC-005):

- **G2**: when a ``subsection_chunk_id`` is supplied, a ``확인`` anchor's
  ``chunk_id`` equals that subsection chunk and its ``line`` lies within the
  chunk's ``[line_start, line_end]``.  No adopted item's anchor may point at the
  chapter-title line or span the whole chapter (SC-005 "미확인 0", whole-chapter
  anchors forbidden).
- **G3**: when the correct answer's evidence is NOT locatable WITHIN the assigned
  subsection — absent (external), in a DIFFERENT subsection, the under-fill
  sentinel, or empty — the result is ``status="미확인"``.

These assertions overlap with ``test_groundedness_answer_anchor.py`` (T012) by
design: T018 widened ``verify_groundedness`` to the scoped/answer-anchored path,
which already restricts hits to the assigned chunk's line range.  This module
exists to LOCK the SC-005 properties explicitly — in particular that the
chapter-title line is never adopted as an anchor — so a future regression on the
scoped lookup is caught at the contract level.
"""

from __future__ import annotations

from maieutica.generate.quiz_gen import MISSING_EVIDENCE_PLACEHOLDER
from maieutica.silver.evidence_index import EvidenceIndex
from maieutica.verify.groundedness import verify_groundedness
from paideia_shared.schemas import (
    LeapExplanation,
    QuizItemCandidate,
    TextbookChunk,
)

# ---------------------------------------------------------------------------
# Fixture: a chapter whose line 1 is the CHAPTER TITLE (outside any subsection)
# and whose body splits into TWO subsections with their own line ranges.
# ---------------------------------------------------------------------------

_LINES = [
    "8장 호흡계통",  # 1  CHAPTER TITLE — outside every chunk (not citable)
    "1. 허파꽈리와 가스교환",  # 2  subsection A heading
    "허파꽈리에서 산소와 이산화탄소가 확산으로 교환된다.",  # 3  A body
    "허파꽈리 벽은 단층편평상피로 구성되어 매우 얇다.",  # 4  A body
    "2. 기관과 기관지",  # 5  subsection B heading
    "기관은 연골고리로 둘러싸여 기도를 열어 둔다.",  # 6  B body
    "기관지는 좌우 허파로 갈라져 공기를 전달한다.",  # 7  B body
]

_CHUNK_A = "chunk0801"
_CHUNK_B = "chunk0802"
_A_RANGE = (2, 4)
_B_RANGE = (5, 7)


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
            line_start=_A_RANGE[0],
            line_end=_A_RANGE[1],
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
            line_start=_B_RANGE[0],
            line_end=_B_RANGE[1],
            text="\n".join(_LINES[4:7]),
            removed_spans=[],
        ),
    ]
    return EvidenceIndex.from_chapter(
        lines=_LINES, chunks=chunks, source_file="8장 호흡계통.txt"
    )


def _make_candidate(
    *,
    answer_no: int,
    option_evidence: list[str],
    key_concept: str | None = "허파꽈리",
) -> QuizItemCandidate:
    leap = LeapExplanation(text="호흡막 두께와 확산 효율을 연결해 보라.", textbook_evidence=None)
    wrong = "정답 보기는 교재 근거와 어긋난다."
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
# G2 — a 확인 anchor lands in the OWNING subsection's line range
# ---------------------------------------------------------------------------


class TestAnchorInsideSubsectionRange:
    def test_anchor_chunk_id_and_line_within_assigned_subsection(self) -> None:
        """G2: chunk_id == subsection_chunk_id AND line ∈ [line_start, line_end]."""
        verbatim = _LINES[3]  # line 4, owned by subsection A
        item = _make_candidate(
            answer_no=2,
            option_evidence=[
                "교재: 다른 진술.",
                verbatim,  # correct option (answer_no=2)
                "교재: 셋.",
                "교재: 넷.",
                "교재: 다섯.",
            ],
        )
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_A
        )
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "확인"
        assert ev.chunk_id == _CHUNK_A  # owning subsection, not the whole chapter
        assert ev.line is not None
        assert _A_RANGE[0] <= ev.line <= _A_RANGE[1]  # ∈ subsection A range
        assert ev.line != 1  # never the chapter-title line

    def test_anchor_for_subsection_b_lands_in_b_range(self) -> None:
        """The same guarantee holds for the other subsection (no cross-leak)."""
        verbatim = _LINES[5]  # line 6, owned by subsection B
        item = _make_candidate(
            answer_no=1,
            option_evidence=[verbatim, "x", "y", "z", "w"],
        )
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_B
        )
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "확인"
        assert ev.chunk_id == _CHUNK_B
        assert ev.line is not None
        assert _B_RANGE[0] <= ev.line <= _B_RANGE[1]


# ---------------------------------------------------------------------------
# G3 — correct evidence not locatable WITHIN the assigned subsection → 미확인
# ---------------------------------------------------------------------------


class TestCorrectEvidenceUnconfirmed:
    def test_evidence_only_in_other_subsection_is_unconfirmed(self) -> None:
        """SC-005: a hit in a DIFFERENT subsection must NOT anchor here.

        The evidence is a verbatim line of subsection B, but the slot is
        assigned to subsection A.  The scoped lookup must reject the B line
        (it lies outside A's range) → 미확인, never a whole-chapter anchor.
        """
        item = _make_candidate(
            answer_no=1,
            option_evidence=[_LINES[6], "x", "y", "z", "w"],  # line 7, in B
        )
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_A
        )
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"
        assert ev.chunk_id is None
        assert ev.line is None

    def test_external_evidence_is_unconfirmed(self) -> None:
        """External (not-in-textbook) correct-option evidence → 미확인."""
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
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_A
        )
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"
        assert ev.chunk_id is None

    def test_sentinel_evidence_is_unconfirmed_and_not_searched(self) -> None:
        """The under-fill sentinel is never searched → 미확인, no search_term."""
        item = _make_candidate(
            answer_no=1,
            option_evidence=[MISSING_EVIDENCE_PLACEHOLDER, "x", "y", "z", "w"],
        )
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_A
        )
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"
        assert ev.search_term is None

    def test_empty_evidence_is_unconfirmed(self) -> None:
        """An empty correct-option evidence string → 미확인 (G3)."""
        item = _make_candidate(
            answer_no=1,
            option_evidence=["", "x", "y", "z", "w"],
        )
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_A
        )
        ev = out.textbook_evidence
        assert ev is not None
        assert ev.status == "미확인"


# ---------------------------------------------------------------------------
# SC-005 — the chapter-title line is NEVER adopted as an anchor
# ---------------------------------------------------------------------------


class TestChapterTitleNeverAnchored:
    def test_title_line_evidence_scoped_to_body_is_unconfirmed(self) -> None:
        """Even if an item's evidence IS the chapter title, scoping to a body
        subsection (whose range excludes line 1) prevents a title anchor."""
        item = _make_candidate(
            answer_no=1,
            option_evidence=[_LINES[0], "x", "y", "z", "w"],  # the title text
        )
        out = verify_groundedness(
            item, _make_index(), subsection_chunk_id=_CHUNK_A
        )
        ev = out.textbook_evidence
        assert ev is not None
        # The title line is outside subsection A's range → not anchored.
        assert ev.status == "미확인"
        assert ev.line is None

    def test_no_scoped_confirmed_anchor_ever_points_at_title_line(self) -> None:
        """Across every body subsection, no 확인 anchor lands on line 1."""
        idx = _make_index()
        for chunk_id, (lo, hi) in (
            (_CHUNK_A, _A_RANGE),
            (_CHUNK_B, _B_RANGE),
        ):
            # Anchor each subsection's own first body line; verify it never
            # collapses onto the chapter-title line.
            body_line_text = _LINES[lo]  # first line of the subsection
            item = _make_candidate(
                answer_no=1,
                option_evidence=[body_line_text, "x", "y", "z", "w"],
            )
            out = verify_groundedness(item, idx, subsection_chunk_id=chunk_id)
            ev = out.textbook_evidence
            assert ev is not None
            assert ev.status == "확인"
            assert ev.line != 1
            assert lo <= ev.line <= hi
