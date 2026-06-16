"""T021 (RED) — unit tests for ``balance_answer_keys`` (examen port, B1–B7).

Pins the answer-balance contract (``contracts/answer_balance.md``) ported from
examen into maieutica, adapted to ``QuizItemCandidate``:

- B1: no run of 3 consecutive identical ``answer_no``.
- B2: no answer number exceeds half the set.
- B3: the multiset of correct-answer option TEXTS is preserved (positions only).
- B4: ``option_evidence[i]`` still corresponds to ``options[i]`` after a swap
  (parallel swap — examen's ``distractor_rationale`` ↔ maieutica's
  ``option_evidence``).
- B5: leading circled digits (①–⑤) are renumbered to positional order on options.
- B6: idempotent + deterministic.
- B7: V1 (``len(options)==5``), V3 (``len(option_evidence)==5``), V4 hold on
  every output item.
"""

from __future__ import annotations

from collections import Counter

from paideia_shared.schemas import LeapExplanation, QuizItemCandidate

_CIRCLED = "①②③④⑤"


def _make_candidate(
    *,
    item_no: int,
    answer_no: int,
    options: list[str] | None = None,
    option_evidence: list[str] | None = None,
) -> QuizItemCandidate:
    """Build a schema-valid candidate with positionally-prefixed options.

    Each option and its parallel evidence carry a shared per-position marker
    (``slotN``) so a parallel swap can be verified to keep option ↔ evidence
    aligned (B4).
    """
    if options is None:
        options = [
            f"{_CIRCLED[i]} 보기 {i + 1}번 본문 — slot{i + 1} 가스교환 설명 채움 문장입니다."
            for i in range(5)
        ]
    if option_evidence is None:
        option_evidence = [f"근거 slot{i + 1}" for i in range(5)]
    wrong = "허파꽈리는 가스교환의 장소이다."
    leap_text = "호흡막 두께와 확산 효율을 연결해 보라."
    leap = LeapExplanation(text=leap_text, textbook_evidence=None)
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=item_no,
        week=9,
        chapter_no=8,
        chapter="8장 호흡계통",
        section="1. 허파꽈리와 가스교환",
        key_concept=f"개념{item_no}",
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text="다음 중 허파꽈리에 대한 설명으로 옳지 않은 것은?",
        options=options,
        answer_no=answer_no,
        option_evidence=option_evidence,
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=None,
        answer_explanation_combined=f"{wrong} ─ 도약 ─ {leap_text}",
        option_length_ok=True,
        explanation_length_ok=True,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


def _max_run(seq: list[int]) -> int:
    """Return the length of the longest run of identical consecutive values."""
    best = run = 0
    prev: int | None = None
    for v in seq:
        run = run + 1 if v == prev else 1
        prev = v
        best = max(best, run)
    return best


def _slot_of(text: str) -> str:
    """Extract the embedded ``slotN`` marker from an option / evidence string."""
    for token in text.split():
        if token.startswith("slot"):
            return token
    raise AssertionError(f"no slot marker in {text!r}")


class TestBalanceAnswerKeys:
    def test_run_and_majority_on_15_all_same(self) -> None:
        """15 items all answer_no=3 → run≤2 (B1) and no number >50% (B2)."""
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=3) for i in range(1, 16)]
        out = balance_answer_keys(items)

        seq = [it.answer_no for it in out]
        assert _max_run(seq) <= 2  # B1
        counts = Counter(seq)
        for num in range(1, 6):
            assert counts.get(num, 0) <= len(out) // 2  # B2

    def test_answer_content_multiset_preserved(self) -> None:
        """The set of correct-answer option TEXTS is unchanged (B3)."""
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=3) for i in range(1, 16)]
        before = Counter(it.options[it.answer_no - 1][1:] for it in items)  # drop prefix
        out = balance_answer_keys(items)
        after = Counter(it.options[it.answer_no - 1][1:] for it in out)
        assert before == after

    def test_parallel_option_evidence_swap(self) -> None:
        """option_evidence[i] stays paired with options[i] after swap (B4)."""
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=3) for i in range(1, 16)]
        out = balance_answer_keys(items)
        for it in out:
            for i in range(5):
                assert _slot_of(it.options[i]) == _slot_of(it.option_evidence[i])

    def test_circled_prefixes_positional_after_swap(self) -> None:
        """Options' leading circled digits are in positional order (B5)."""
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=3) for i in range(1, 16)]
        out = balance_answer_keys(items)
        for it in out:
            assert [opt[0] for opt in it.options] == list(_CIRCLED)

    def test_idempotent_and_deterministic(self) -> None:
        """balance(balance(x)) == balance(x) by answer_no seq + option texts (B6)."""
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=3) for i in range(1, 16)]
        once = balance_answer_keys(items)
        twice = balance_answer_keys(once)

        assert [it.answer_no for it in once] == [it.answer_no for it in twice]
        assert [it.options for it in once] == [it.options for it in twice]
        assert [it.option_evidence for it in once] == [it.option_evidence for it in twice]

    def test_schema_invariants_preserved(self) -> None:
        """V1, V3, V4 hold on every output item (B7)."""
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=3) for i in range(1, 16)]
        out = balance_answer_keys(items)
        for it in out:
            assert len(it.options) == 5  # V1
            assert len(it.option_evidence) == 5  # V3
            expected = f"{it.wrong_explanation} ─ 도약 ─ {it.leap.text}"
            assert it.answer_explanation_combined == expected  # V4

    def test_small_n_best_effort_run_break(self) -> None:
        """Small-N outside the feasible band → run-breaking still applies (run≤2).

        N=4 is outside the distribution band (lo=1, hi=1, 5·lo=5 > 4) so the
        distribution phase is skipped, but a breakable run of three (a differing
        value exists to swap with) is still broken — matching examen's
        best-effort Edge Case.
        """
        from maieutica.verify.format_checks import balance_answer_keys

        # [2, 2, 2, 4] — a run of three 2s with a differing value (4) to swap in.
        answers = [2, 2, 2, 4]
        items = [_make_candidate(item_no=i + 1, answer_no=a) for i, a in enumerate(answers)]
        out = balance_answer_keys(items)
        assert _max_run([it.answer_no for it in out]) <= 2

    def test_all_same_no_swap_partner_degrades(self) -> None:
        """N=3 all-same has no swap partner → run unbroken, never raises.

        Faithful to examen: ``_break_runs`` degrades gracefully when no
        differing value exists, rather than fabricating a new answer number.
        """
        from maieutica.verify.format_checks import balance_answer_keys

        items = [_make_candidate(item_no=i, answer_no=2) for i in range(1, 4)]
        out = balance_answer_keys(items)
        # Content preserved; positions unchanged (no valid swap), no crash.
        assert [it.answer_no for it in out] == [2, 2, 2]

    def test_empty_input(self) -> None:
        from maieutica.verify.format_checks import balance_answer_keys

        assert balance_answer_keys([]) == []
