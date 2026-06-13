"""T013 (RED) — unit tests for anchor-keyed ``detect_duplicates`` (D1–D4).

``detect_duplicates`` now judges duplicates by the answer's textbook anchor
``(textbook_evidence.chunk_id, textbook_evidence.line)`` rather than by
``key_concept`` (v0.1.0).  Among candidates sharing an anchor key the FIRST
occurrence is kept and the rest are REMOVED (dropped), so the returned set has
zero anchor-duplicates (contract ``contracts/dedup_by_anchor.md`` D1–D4).

Invariant: items in the SAME subsection (same ``chunk_id``) but a DIFFERENT
``line`` are NOT duplicates (different sentence = different focus) — both kept.
Items WITHOUT a confirmed anchor (``textbook_evidence is None``, ``status``
``미확인``, or ``chunk_id``/``line`` ``None``) are never grouped or removed here.
"""

from __future__ import annotations

from paideia_shared.schemas import (
    LeapExplanation,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)

_GOOD_OPTIONS = [
    "① 허파꽈리는 가스교환이 일어나는 호흡계통의 기본 단위이다.",
    "② 허파꽈리 벽은 단층편평상피로 구성되어 매우 얇은 편이다.",
    "③ 허파꽈리 주위에는 모세혈관이 그물처럼 분포하고 있다고 한다.",
    "④ 허파꽈리에서는 산소와 이산화탄소가 확산으로 교환된다고 한다.",
    "⑤ 허파꽈리는 기관 안에서 직접 공기를 데우는 기능을 한다고 한다.",
]


def _confirmed_anchor(chunk_id: str, line: int) -> MaieuticaTextbookEvidence:
    """Build a ``확인`` evidence anchored at ``(chunk_id, line)``."""
    return MaieuticaTextbookEvidence(
        chunk_id=chunk_id,
        source_file="8장 호흡계통.txt",
        char_start=0,
        char_end=10,
        line=line,
        found_text="허파꽈리는 가스교환이 일어난다.",
        search_term="허파꽈리",
        status="확인",
    )


def _unconfirmed_anchor() -> MaieuticaTextbookEvidence:
    """Build a ``미확인`` evidence (no citable anchor)."""
    return MaieuticaTextbookEvidence(
        source_file="8장 호흡계통.txt",
        search_term="허파꽈리",
        status="미확인",
    )


def _make_candidate(
    *,
    item_no: int = 1,
    textbook_evidence: MaieuticaTextbookEvidence | None = None,
    answer_no: int = 5,
) -> QuizItemCandidate:
    leap = LeapExplanation(text="호흡막 두께와 확산 효율을 연결해 보라.", textbook_evidence=None)
    wrong = "허파꽈리는 가스교환의 장소이다."
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=item_no,
        week=9,
        chapter_no=8,
        chapter="8장 호흡계통",
        section="1. 허파꽈리와 가스교환",
        key_concept="허파꽈리",
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text="다음 중 허파꽈리에 대한 설명으로 옳지 않은 것은?",
        options=list(_GOOD_OPTIONS),
        answer_no=answer_no,
        option_evidence=["근거"] * 5,
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=textbook_evidence,
        answer_explanation_combined=f"{wrong} ─ 도약 ─ {leap.text}",
        option_length_ok=True,
        explanation_length_ok=True,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


class TestDedupByAnchor:
    def test_same_anchor_removes_second_keeps_first(self) -> None:
        """D1/D2: same ``(chunk_id, line)`` → second dropped, first kept."""
        from maieutica.verify.format_checks import detect_duplicates

        a = _make_candidate(item_no=1, textbook_evidence=_confirmed_anchor("c8-1", 12))
        b = _make_candidate(item_no=2, textbook_evidence=_confirmed_anchor("c8-1", 12))
        out = detect_duplicates([a, b])
        assert len(out) == 1
        assert out[0].item_no == 1  # first occurrence kept

    def test_same_chunk_different_line_both_kept(self) -> None:
        """Invariant: same chunk_id, different line = different focus → both kept."""
        from maieutica.verify.format_checks import detect_duplicates

        a = _make_candidate(item_no=1, textbook_evidence=_confirmed_anchor("c8-1", 12))
        b = _make_candidate(item_no=2, textbook_evidence=_confirmed_anchor("c8-1", 13))
        out = detect_duplicates([a, b])
        assert len(out) == 2
        assert [c.item_no for c in out] == [1, 2]

    def test_unconfirmed_anchor_passes_through(self) -> None:
        """미확인/None anchors are never grouped or removed by dedup (T029 is separate)."""
        from maieutica.verify.format_checks import detect_duplicates

        confirmed = _make_candidate(
            item_no=1, textbook_evidence=_confirmed_anchor("c8-1", 12)
        )
        unconfirmed = _make_candidate(
            item_no=2, textbook_evidence=_unconfirmed_anchor()
        )
        none_anchor = _make_candidate(item_no=3, textbook_evidence=None)
        out = detect_duplicates([confirmed, unconfirmed, none_anchor])
        assert len(out) == 3
        assert [c.item_no for c in out] == [1, 2, 3]

    def test_unconfirmed_not_removed_even_when_confirmed_dup_present(self) -> None:
        """A 미확인 item is kept even alongside a removed confirmed-anchor duplicate."""
        from maieutica.verify.format_checks import detect_duplicates

        a = _make_candidate(item_no=1, textbook_evidence=_confirmed_anchor("c8-1", 12))
        b = _make_candidate(item_no=2, textbook_evidence=_confirmed_anchor("c8-1", 12))
        u = _make_candidate(item_no=3, textbook_evidence=_unconfirmed_anchor())
        out = detect_duplicates([a, b, u])
        # b removed (dup of a); a and u kept.
        assert [c.item_no for c in out] == [1, 3]

    def test_deterministic_same_input_same_output(self) -> None:
        """D2: same input → same output (length, order, identity)."""
        from maieutica.verify.format_checks import detect_duplicates

        items = [
            _make_candidate(item_no=1, textbook_evidence=_confirmed_anchor("c8-1", 12)),
            _make_candidate(item_no=2, textbook_evidence=_confirmed_anchor("c8-1", 13)),
            _make_candidate(item_no=3, textbook_evidence=_confirmed_anchor("c8-1", 12)),
            _make_candidate(item_no=4, textbook_evidence=_confirmed_anchor("c8-2", 20)),
        ]
        first = detect_duplicates(items)
        second = detect_duplicates(items)
        assert [c.item_no for c in first] == [c.item_no for c in second]
        assert all(x is y for x, y in zip(first, second, strict=True))

    def test_first_occurrence_kept_stable_order(self) -> None:
        """First-occurrence-kept ordering is stable across the kept set."""
        from maieutica.verify.format_checks import detect_duplicates

        items = [
            _make_candidate(item_no=1, textbook_evidence=_confirmed_anchor("c8-1", 12)),
            _make_candidate(item_no=2, textbook_evidence=_confirmed_anchor("c8-2", 20)),
            _make_candidate(item_no=3, textbook_evidence=_confirmed_anchor("c8-1", 12)),
            _make_candidate(item_no=4, textbook_evidence=_confirmed_anchor("c8-2", 20)),
            _make_candidate(item_no=5, textbook_evidence=_confirmed_anchor("c8-3", 30)),
        ]
        out = detect_duplicates(items)
        # Keep first of each anchor: items 1, 2, 5.
        assert [c.item_no for c in out] == [1, 2, 5]
