"""T028 — Format verification: option length, 5-option, stem_polarity.

``check_format(item) -> ExamItemDraft``

Validates and flags format-rule compliance on a generated exam item:

1. ``option_length_ok``: every option is 30–40 codepoints (including its
   number prefix).  Flags violations with ``option_length_ok=False``.
   Does NOT raise — the quality report (US5) surfaces the violation.
2. 5-option enforcement: the schema validator already guarantees
   ``len(options) == 5``; this function preserves the count unchanged.
3. ``stem_polarity`` consistency: detect/record whether the stem text
   suggests 부정형 ("옳지 않은", "아닌", "틀린", etc.) vs 긍정형 ("옳은",
   "맞는", etc.) and cross-check against the declared ``stem_polarity``.
   Mismatch is NOT corrected — the item is returned as-is (the professor
   resolves ambiguous polarity during review).

Scope (US1 only)
----------------
Answer-key balance and duplicate detection are US4/US5 tasks and are
NOT implemented here.

Design
------
Returns a new ``ExamItemDraft`` via ``model_copy`` (frozen Pydantic model).
Never raises on a rule violation — flags it in the returned item's
``option_length_ok`` field.
"""

from __future__ import annotations

from paideia_shared.schemas import ExamItemDraft

# ---------------------------------------------------------------------------
# Stem polarity detection keywords
# ---------------------------------------------------------------------------

# 부정형 발문에 나타나는 키워드 (substrings)
_NEGATIVE_STEM_CUES = ("옳지 않은", "아닌", "틀린", "잘못된", "해당하지 않는", "옳지않은")

# 긍정형 발문에 나타나는 키워드
_POSITIVE_STEM_CUES = ("옳은", "맞는", "해당하는", "올바른")

# 옵션 길이 허용 범위 (코드포인트 기준, 번호 포함)
_OPTION_MIN_LEN = 30
_OPTION_MAX_LEN = 40


def _compute_option_length_ok(options: list[str]) -> bool:
    """Check that all options are within 30–40 codepoints.

    Args:
        options: List of option strings.  Each should include its number
            prefix (e.g. ``"① 뇌하수체는..."``).

    Returns:
        ``True`` iff every option satisfies ``30 <= len(opt) <= 40``.
    """
    if not options:
        return False
    return all(_OPTION_MIN_LEN <= len(opt) <= _OPTION_MAX_LEN for opt in options)


def _detect_stem_polarity(text: str) -> str | None:
    """Detect polarity of the stem text from keyword matching.

    Args:
        text: The question stem text.

    Returns:
        ``"부정형"``, ``"긍정형"``, or ``None`` if inconclusive.
    """
    # 부정형 키워드 먼저 확인 (더 구체적)
    for cue in _NEGATIVE_STEM_CUES:
        if cue in text:
            return "부정형"
    for cue in _POSITIVE_STEM_CUES:
        if cue in text:
            return "긍정형"
    return None


def check_format(item: ExamItemDraft) -> ExamItemDraft:
    """Compute and set format-check flags on ``item``.

    Actions:
    1. Re-compute ``option_length_ok`` — overrides whatever the generator
       set (the verify stage owns this field).
    2. Detect ``stem_polarity`` from ``item.text``.  If detected polarity
       differs from ``item.stem_polarity``, the mismatch is recorded in
       ``review_note`` (the professor resolves during draft review).
       ``stem_polarity`` itself is NOT changed.
    3. Return a new frozen ``ExamItemDraft`` via ``model_copy``.

    The 5-option count is guaranteed by the schema; no separate check needed.

    Args:
        item: The exam item to format-check.

    Returns:
        A new ``ExamItemDraft`` with recalculated ``option_length_ok`` and
        potentially updated ``review_note``.
    """
    # Step 1: 옵션 길이 재계산 (verify 단계가 소유 — 생성 시 임시 값 덮어쓰기)
    option_length_ok = _compute_option_length_ok(list(item.options))

    # Step 2: stem_polarity 일관성 확인
    detected_polarity = _detect_stem_polarity(item.text)
    review_note = item.review_note or ""

    if detected_polarity is not None and detected_polarity != item.stem_polarity:
        # 발문 텍스트에서 감지한 극성과 선언된 극성이 다름 → review_note 에 기록
        note_entry = (
            f"[format_check] stem_polarity 불일치: "
            f"선언={item.stem_polarity!r}, "
            f"감지={detected_polarity!r} "
            f"(text: {item.text[:40]!r})"
        )
        review_note = f"{review_note}\n{note_entry}" if review_note else note_entry

    # Step 3: frozen model → model_copy 로 새 객체 반환
    updates: dict[str, object] = {"option_length_ok": option_length_ok}
    if review_note != (item.review_note or ""):
        updates["review_note"] = review_note

    return item.model_copy(update=updates)


__all__ = ["check_format"]
