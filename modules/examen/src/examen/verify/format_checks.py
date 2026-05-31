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

Later additions (US3–US5) in this module
-----------------------------------------
- ``check_quiz_variation`` (T042): Jaccard variation guard for quiz items.
- ``check_explanation_lengths`` (T048): wrong/leap/intent length checks.
- ``detect_duplicates`` (T048): key_concept near-duplicate flagging.
- ``balance_answer_keys`` (T050): answer-position rebalance to 15–25% / no
  run-of-3.
All remain non-raising — violations are flagged, never crash the pipeline.

Design
------
Returns a new ``ExamItemDraft`` via ``model_copy`` (frozen Pydantic model).
Never raises on a rule violation — flags it in the returned item's
``option_length_ok`` field or ``review_note``.
"""

from __future__ import annotations

import math

from paideia_shared.schemas import ExamItemDraft, SourceInventoryEntry

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


# ---------------------------------------------------------------------------
# T042 — Quiz variation jaccard guard
# ---------------------------------------------------------------------------

# 자카드 유사도 임계값 (0 < J < 0.8 이 정상 변형 범위)
_JACCARD_UPPER = 0.8   # 이 이상 → 원본과 너무 유사 (재작성 불충분)
_JACCARD_LOWER = 0.0   # 이 이하 → 원본과 완전히 다름 (개념 보존 의심)


def token_jaccard(a: str, b: str) -> float:
    """Compute token-set Jaccard similarity between two strings.

    Tokenises by splitting on whitespace.  Empty tokens are ignored.
    Empty inputs produce Jaccard == 0.0 (no shared tokens, no union).

    Jaccard(A, B) = |A ∩ B| / |A ∪ B|

    Args:
        a: First string.
        b: Second string.

    Returns:
        Float in [0.0, 1.0].  Returns 0.0 if both strings are empty.
    """
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / len(union)


def check_quiz_variation(
    item: ExamItemDraft,
    original_entry: SourceInventoryEntry,
) -> ExamItemDraft:
    """Apply Jaccard variation guard to a quiz-derived item.

    Computes token Jaccard similarity between the varied item's
    stem+options text and the original quiz entry's stem+options text.
    The normal variation range is ``0 < J < 0.8``:

    - J == 0 (wholly different): the concept may not be preserved →
      flag in ``review_note``.
    - J >= 0.8 (too similar / identical): the wording was not rewritten
      sufficiently → flag in ``review_note``.
    - 0 < J < 0.8: passes — no jaccard flag added.

    Does NOT raise — violations are flagged in ``review_note`` for professor
    review (constitution: non-crashing verify).

    Args:
        item: The varied ExamItemDraft (source="quiz").
        original_entry: The original quiz SourceInventoryEntry.

    Returns:
        A new ``ExamItemDraft`` with any jaccard violation added to
        ``review_note``.
    """
    # 원본 텍스트: stem + options joined (options may be None for quiz entries)
    original_opts = original_entry.options or []
    original_text = " ".join([original_entry.stem] + original_opts)

    # 변형 텍스트: item.text + options
    varied_text = " ".join([item.text] + list(item.options))

    jaccard = token_jaccard(original_text, varied_text)

    review_note = item.review_note or ""
    notes: list[str] = []

    if jaccard >= _JACCARD_UPPER:
        notes.append(
            f"[quiz_variation_check] jaccard={jaccard:.3f} >= {_JACCARD_UPPER}: "
            "변형이 충분하지 않습니다 — 발문·보기를 더 다르게 재작성하세요 "
            f"(source_ref={item.source_ref!r})"
        )
    elif jaccard <= _JACCARD_LOWER:
        # J == 0.0: wholly disjoint — concept preservation cannot be verified
        notes.append(
            f"[quiz_variation_check] jaccard={jaccard:.3f} == 0: "
            "변형 문항과 원본 문항 사이에 공통 토큰이 없습니다 — "
            "동일 교재 근거 및 정답 판정 포인트 유지 여부를 교수 검토 필요 "
            f"(source_ref={item.source_ref!r})"
        )

    if notes:
        extra = "\n".join(notes)
        review_note = f"{review_note}\n{extra}" if review_note else extra

    updates: dict[str, object] = {}
    if review_note != (item.review_note or ""):
        updates["review_note"] = review_note

    return item.model_copy(update=updates) if updates else item



# ---------------------------------------------------------------------------
# T048 — Explanation / intent length verification
# ---------------------------------------------------------------------------

# wrong_explanation / leap_explanation 목표 범위 (코드포인트)
_WRONG_LEAP_MIN = 270
_WRONG_LEAP_MAX = 330

# intent 목표 범위 (코드포인트)
_INTENT_MIN = 40
_INTENT_MAX = 60


def check_explanation_lengths(item: ExamItemDraft) -> ExamItemDraft:
    """Verify wrong_explanation, leap_explanation, and intent lengths.

    Checks:
    1. ``wrong_explanation`` must be 270–330 codepoints.
    2. ``leap_explanation`` must be 270–330 codepoints.
    3. ``intent`` must be 40–60 codepoints.

    Out-of-range violations are recorded in ``review_note`` (never raises).
    The item is returned as-is when all fields are in range.

    Args:
        item: The exam item to length-check.

    Returns:
        A new ``ExamItemDraft`` with any length violations appended to
        ``review_note``.  Returns the original object (identity) if no
        violations are found.
    """
    notes: list[str] = []

    wrong_len = len(item.wrong_explanation)
    if not (_WRONG_LEAP_MIN <= wrong_len <= _WRONG_LEAP_MAX):
        notes.append(
            f"[length_check] wrong_explanation 길이 위반: "
            f"{wrong_len}자 (목표 {_WRONG_LEAP_MIN}~{_WRONG_LEAP_MAX}자)"
        )

    leap_len = len(item.leap_explanation)
    if not (_WRONG_LEAP_MIN <= leap_len <= _WRONG_LEAP_MAX):
        notes.append(
            f"[length_check] leap_explanation 길이 위반: "
            f"{leap_len}자 (목표 {_WRONG_LEAP_MIN}~{_WRONG_LEAP_MAX}자)"
        )

    intent_len = len(item.intent)
    if not (_INTENT_MIN <= intent_len <= _INTENT_MAX):
        notes.append(
            f"[length_check] intent 길이 위반: "
            f"{intent_len}자 (목표 {_INTENT_MIN}~{_INTENT_MAX}자)"
        )

    if not notes:
        return item

    review_note = item.review_note or ""
    extra = "\n".join(notes)
    review_note = f"{review_note}\n{extra}" if review_note else extra
    return item.model_copy(update={"review_note": review_note})


# ---------------------------------------------------------------------------
# T048 — Duplicate detection by key_concept
# ---------------------------------------------------------------------------


def detect_duplicates(items: list[ExamItemDraft]) -> list[ExamItemDraft]:
    """Flag near-duplicate items by ``key_concept``.

    Items sharing the same non-None ``key_concept`` are considered potential
    duplicates.  The *first* occurrence is kept (``duplicate_flag`` unchanged);
    all subsequent items with the same concept are flagged
    (``duplicate_flag = True``).

    Design decisions:
    - ``key_concept=None`` items are NEVER grouped as duplicates (no signal).
    - Items already carrying ``duplicate_flag=True`` (from a prior run or
      manual annotation) are left as-is and not cleared.
    - Deterministic: stable input order → stable output flags.

    Args:
        items: List of exam items (order is preserved).

    Returns:
        New list with the same length as ``items``, where duplicate items
        have ``duplicate_flag=True`` set.
    """
    seen: set[str] = set()
    result: list[ExamItemDraft] = []

    for item in items:
        kc = item.key_concept
        if kc is not None and kc in seen:
            # 중복 — duplicate_flag 를 True 로 설정
            if not item.duplicate_flag:
                item = item.model_copy(update={"duplicate_flag": True})
        elif kc is not None:
            seen.add(kc)
        # key_concept=None 또는 첫 출현: 플래그 유지 (이미 True 이면 그대로)
        result.append(item)

    return result


# ---------------------------------------------------------------------------
# T050 — Answer-key balance: reorder answer positions so each of 1–5 falls
#         in 15–25% and no run of more than 2 consecutive identical answer
#         numbers (i.e. no three-in-a-row).
# ---------------------------------------------------------------------------

# 정답 번호 균형 목표 범위 (비율)
_BALANCE_MIN_RATIO = 0.15
_BALANCE_MAX_RATIO = 0.25

# 부동소수점 경계 오차 보정용 epsilon (lo=ceil(0.15·n), hi=floor(0.25·n) 계산 시)
_BALANCE_EPS = 1e-9


def _swap_answer_to_position(item: ExamItemDraft, new_pos: int) -> ExamItemDraft:
    """Swap the correct answer option to ``new_pos`` (1-based) within an item.

    Performs a two-way swap between the current answer position and ``new_pos``:
    - ``options[answer_no-1]`` ↔ ``options[new_pos-1]``
    - ``distractor_rationale[answer_no-1]`` ↔ ``distractor_rationale[new_pos-1]``
    - ``answer_no`` is updated to ``new_pos``

    The correct answer *content* is unchanged — only its position moves.
    Pre-condition: ``1 <= new_pos <= 5`` and ``new_pos != item.answer_no``.

    Args:
        item: The exam item to rebalance.
        new_pos: The target 1-based position for the correct answer.

    Returns:
        A new ``ExamItemDraft`` with the swap applied.
    """
    opts = list(item.options)
    rats = list(item.distractor_rationale)
    old_idx = item.answer_no - 1
    new_idx = new_pos - 1

    # Swap content
    opts[old_idx], opts[new_idx] = opts[new_idx], opts[old_idx]
    rats[old_idx], rats[new_idx] = rats[new_idx], rats[old_idx]

    return item.model_copy(
        update={
            "options": opts,
            "distractor_rationale": rats,
            "answer_no": new_pos,
        }
    )


def _balance_bounds(n: int) -> tuple[int, int]:
    """Return (lo, hi) — the min/max allowed count per answer number for N=n.

    ``lo = ceil(0.15·n)``, ``hi = floor(0.25·n)`` with epsilon guards so exact
    boundaries (e.g. 0.15·40 = 6.0) are inclusive rather than tripped by float
    representation error.
    """
    lo = math.ceil(_BALANCE_MIN_RATIO * n - _BALANCE_EPS)
    hi = math.floor(_BALANCE_MAX_RATIO * n + _BALANCE_EPS)
    return lo, hi


def _position_in_run(seq: list[int], pos: int) -> bool:
    """True iff ``seq[pos]`` participates in any run of 3 identical values.

    Checks the three windows that include ``pos``: ``[pos-2,pos]``,
    ``[pos-1,pos+1]``, ``[pos,pos+2]`` (clamped to bounds).
    """
    n = len(seq)
    v = seq[pos]
    for start in (pos - 2, pos - 1, pos):
        a, b, c = start, start + 1, start + 2
        if a >= 0 and c < n and seq[a] == seq[b] == seq[c] == v:
            return True
    return False


def _balance_distribution(seq: list[int], lo: int, hi: int) -> None:
    """Move answer numbers from the most over- to the most under-represented.

    Mutates ``seq`` in place.  Each step reassigns the first occurrence of the
    globally most-represented number to the globally least-represented number,
    monotonically shrinking the spread until every count lands in ``[lo, hi]``.

    Triggers on BOTH over-representation (count > hi) AND under-representation
    (count < lo) — the latter was the US5 Critical gap: a number could sit
    below 15% while nothing exceeded 25% and the old greedy never noticed.
    """
    n = len(seq)
    max_iter = n * 6  # generous convergence guard (spread shrinks each step)
    for _ in range(max_iter):
        counts = {num: seq.count(num) for num in range(1, 6)}
        # Most over-represented (tie → lowest number); most under (tie → lowest).
        over = max(range(1, 6), key=lambda num: (counts[num], -num))
        under = min(range(1, 6), key=lambda num: (counts[num], num))
        if counts[over] <= hi and counts[under] >= lo:
            return  # every number within [lo, hi]
        if over == under:
            return  # all equal — cannot improve
        # Reassign the first item carrying `over` to `under`.
        idx = seq.index(over)
        seq[idx] = under


def _break_runs(seq: list[int]) -> None:
    """Eliminate runs of 3+ identical values via count-preserving swaps.

    Mutates ``seq`` in place.  Swapping two positions exchanges their values,
    so per-number counts (and thus the 15–25% distribution fixed earlier) are
    preserved.  Deterministic: always fixes the lowest-index run with the
    lowest-index valid swap partner.  Degrades gracefully (returns) if a run
    cannot be broken — never raises, never loops forever.
    """
    n = len(seq)
    if n < 3:
        return
    max_iter = n * n
    for _ in range(max_iter):
        run_idx = next(
            (i for i in range(2, n) if seq[i] == seq[i - 1] == seq[i - 2]),
            None,
        )
        if run_idx is None:
            return  # no runs remain
        i = run_idx
        swapped = False
        for j in range(n):
            if seq[j] == seq[i]:
                continue
            seq[i], seq[j] = seq[j], seq[i]
            if not _position_in_run(seq, i) and not _position_in_run(seq, j):
                swapped = True
                break
            seq[i], seq[j] = seq[j], seq[i]  # revert — swap did not help
        if not swapped:
            return  # cannot break this run with any swap — degrade gracefully


def balance_answer_keys(items: list[ExamItemDraft]) -> list[ExamItemDraft]:
    """Rebalance answer_no positions so the distribution is 15–25% and runs ≤ 2.

    Two-phase, fully deterministic (no randomness), operating on a working array
    of the items' answer numbers:

    1. **Distribution** (``_balance_distribution``): repeatedly move the most
       over-represented answer number to the most under-represented until every
       number's count lands in ``[lo, hi]`` where ``lo = ceil(0.15·N)`` and
       ``hi = floor(0.25·N)``.  This corrects BOTH over-representation (>25%)
       AND under-representation (<15%); the latter was the US5 Critical gap.
    2. **Run-breaking** (``_break_runs``): eliminate any run of three identical
       consecutive answers via count-preserving swaps, so the distribution from
       phase 1 is not disturbed.

    The final answer-number array is applied per item via
    ``_swap_answer_to_position`` — moving each item's *correct option* to its
    target slot, so the correct answer content is never altered.

    Guarantees:
    - Input length preserved; each item's correct answer content unchanged.
    - Deterministic: identical input → identical output.
    - Idempotent: an already-conforming list is returned unchanged (both phases
      no-op when there is no violation), so ``balance(balance(x)) == balance(x)``.
    - For N in the feasible band (``5·lo ≤ N ≤ 5·hi``) both invariants hold.
      For very small / infeasible N the algorithm does its best and never
      crashes.

    Args:
        items: List of exam items to rebalance.

    Returns:
        New list of ``ExamItemDraft`` objects with rebalanced answer positions.
    """
    if not items:
        return []

    n = len(items)
    seq = [item.answer_no for item in items]

    lo, hi = _balance_bounds(n)
    # Distribution is only achievable when 5·lo ≤ N ≤ 5·hi (each number can sit
    # in [lo, hi] and still sum to N).  Outside that band (e.g. N < 4) we skip
    # the distribution phase — there is no valid target — but still break runs.
    if lo <= hi and 5 * lo <= n <= 5 * hi:
        _balance_distribution(seq, lo, hi)
    _break_runs(seq)

    result: list[ExamItemDraft] = []
    for item, target in zip(items, seq, strict=True):
        if item.answer_no != target:
            result.append(_swap_answer_to_position(item, target))
        else:
            result.append(item)
    return result


__all__ = [
    "check_format",
    "check_formative",
    "token_jaccard",
    "check_quiz_variation",
    "check_explanation_lengths",
    "detect_duplicates",
    "balance_answer_keys",
]
