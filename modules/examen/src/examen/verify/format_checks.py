"""T028 / T035 — Format verification: option length, 5-option, stem_polarity,
and formative-specific checks.

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

T035 addition — Formative-specific checks (``check_formative``)
---------------------------------------------------------------
For items with ``source == "formative"``:
- The stem must be 부정형 (verified by detecting 부정형 keywords).
- A best-effort scope check flags suspicious option text (heuristic; never
  raises — violations are recorded in ``review_note``).

Scope (US1/US2)
---------------
Answer-key balance and duplicate detection are US4/US5 tasks and are
NOT implemented here.

Design
------
Returns a new ``ExamItemDraft`` via ``model_copy`` (frozen Pydantic model).
Never raises on a rule violation — flags it in the returned item's
``option_length_ok`` field or ``review_note``.
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

# 형성 변환 프롬프트 계약: 틀린 보기(=정답)의 근거는 "틀린" 마커로 시작한다.
# convert_formative 프롬프트가 LLM 에게 "틀린 진술:" 접두사를 요구하므로
# answer_no 가 가리키는 근거에 이 마커가 있는지 검증한다.
_WRONG_RATIONALE_MARKER = "틀린"


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


# ---------------------------------------------------------------------------
# T035 — Formative-specific verification
# ---------------------------------------------------------------------------

def check_formative(item: ExamItemDraft) -> ExamItemDraft:
    """Apply formative-specific format checks to ``item``.

    Called after ``check_format`` for items with ``source == "formative"``.

    Checks (non-raising — violations recorded in review_note):
    1. stem_polarity declared as ``"부정형"`` — if not, record in review_note.
    2. stem text contains 부정형 keyword — if not, record in review_note.
    3. Answer-marker contract: the ``distractor_rationale`` entry at
       ``answer_no`` must carry the agreed "틀린" marker (the prompt asks the
       LLM to prefix the wrong option's rationale with "틀린 진술:").  This
       proves the option at ``answer_no`` is actually the FALSE one rather than
       trusting ``stem_polarity`` alone.  Missing/misplaced marker → violation.
    4. Best-effort groundedness scope flag: if ``textbook_evidence`` is None
       (expected for formative), record informational note.

    Args:
        item: The exam item to check (should have source="formative").

    Returns:
        A new ``ExamItemDraft`` with any formative violations added to
        ``review_note``.
    """
    if item.source != "formative":
        # 형성 전용 — 다른 출처 아이템은 그대로 반환
        return item

    review_note = item.review_note or ""
    notes: list[str] = []

    # Check 1: stem_polarity 선언이 부정형인지 확인
    if item.stem_polarity != "부정형":
        notes.append(
            f"[formative_check] stem_polarity 오류: "
            f"형성 변환 문항은 반드시 부정형이어야 하나 "
            f"선언={item.stem_polarity!r}"
        )

    # Check 2: 발문 텍스트에서 부정형 키워드 감지
    detected = _detect_stem_polarity(item.text)
    if detected is not None and detected != "부정형":
        notes.append(
            f"[formative_check] 발문 텍스트가 긍정형으로 감지됨 — "
            f"부정형 발문으로 수정 필요 "
            f"(text: {item.text[:40]!r})"
        )
    elif detected is None and item.text.strip():
        # 감지 불명 → informational 경고
        notes.append(
            f"[formative_check] 발문에서 부정형/긍정형 키워드를 감지하지 못함 "
            f"(text: {item.text[:40]!r}) — 교수 검토 필요"
        )

    # Check 3: answer-marker 계약 — answer_no 근거가 "틀린" 마커를 가졌는지.
    # 부정형 문항이므로 정답은 '틀린 보기'여야 하고, 프롬프트는 그 근거에
    # "틀린 진술:" 접두사를 요구한다. answer_no 가 가리키는 근거에 마커가 없으면
    # 정답이 실제로 틀린 보기인지 확신할 수 없다 → 검토 필요.
    rationales = list(item.distractor_rationale)
    idx = item.answer_no - 1
    if 0 <= idx < len(rationales):
        answer_rationale = rationales[idx]
        if _WRONG_RATIONALE_MARKER not in answer_rationale:
            notes.append(
                f"[formative_check] 정답({item.answer_no}번) 보기 근거에 "
                f"'{_WRONG_RATIONALE_MARKER}' 마커가 없습니다 — "
                f"정답이 실제 틀린 보기인지 확인 필요 "
                f"(근거: {answer_rationale[:40]!r})"
            )
        # 추가: 정답이 아닌 보기에 "틀린" 마커가 있으면 정답 지정 오류 의심
        other_wrong = [
            i + 1
            for i, r in enumerate(rationales)
            if i != idx and _WRONG_RATIONALE_MARKER in r
        ]
        if other_wrong:
            notes.append(
                f"[formative_check] 정답이 아닌 보기 {other_wrong} 에 "
                f"'{_WRONG_RATIONALE_MARKER}' 마커가 있습니다 — "
                "정답 번호 지정 오류 가능성 검토 필요"
            )
    else:
        notes.append(
            f"[formative_check] answer_no={item.answer_no} 가 "
            f"distractor_rationale 범위(1~{len(rationales)})를 벗어남"
        )

    # Check 4: textbook_evidence 없음 → 범위 근거 앵커 미보유 (informational)
    if item.textbook_evidence is None:
        notes.append(
            "[formative_check] textbook_evidence=None — "
            "형성 변환 문항의 보기 근거는 model_answer/공유정보 범위에 한정"
        )

    if notes:
        extra = "\n".join(notes)
        review_note = f"{review_note}\n{extra}" if review_note else extra

    updates: dict[str, object] = {}
    if review_note != (item.review_note or ""):
        updates["review_note"] = review_note

    return item.model_copy(update=updates) if updates else item


__all__ = ["check_format", "check_formative"]
