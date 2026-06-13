"""T029 — Format verification: option/explanation length, duplicates, answer dist.

quiz_gen (T027) freezes provisional ``option_length_ok`` /
``explanation_length_ok`` flags.  This stage is the AUTHORITY for those soft
flags (FR-008/009/010/011): it (re)computes and sets them via ``model_copy``,
REMOVES anchor-duplicate candidates by their answer textbook anchor
``(chunk_id, line)`` (v0.1.1; the retired v0.1.0 ``key_concept`` grouping is
gone), and RECORDS the answer_no distribution for the manifest.

Answer-key balance (v0.1.1)
---------------------------
As of v0.1.1 (spec 010, R5 decision reversal) maieutica DOES rebalance answer
keys: ``balance_answer_keys`` ports examen's proven answer-position algorithm
into this module (deliberate, temporary code duplication — NOT a shared-kernel
import; see plan Complexity Tracking) and adapts it to ``QuizItemCandidate``
(parallel ``options`` ↔ ``option_evidence`` swap).  ``answer_no_distribution``
still only *records* the distribution for the manifest.

All functions are non-raising — violations are flagged on the returned
candidate, never crash the pipeline.  Frozen model → ``model_copy`` only.
"""

from __future__ import annotations

import math

from paideia_shared.schemas import QuizItemCandidate

# Option length window (codepoints, incl. spaces / number prefix) — FR-010.
_OPTION_MIN_LEN = 30
_OPTION_MAX_LEN = 50

# Explanation length ceiling (codepoints, incl. spaces) — FR-011.
_EXPLANATION_MAX_LEN = 200


def _compute_option_length_ok(options: list[str]) -> bool:
    """Return True iff every option is 30–50 codepoints (incl. spaces).

    Args:
        options: The option strings (each includes its number prefix).

    Returns:
        ``True`` iff ``options`` is non-empty and each option's codepoint
        length is within ``[30, 50]``.
    """
    if not options:
        return False
    return all(_OPTION_MIN_LEN <= len(opt) <= _OPTION_MAX_LEN for opt in options)


def _compute_explanation_length_ok(wrong_explanation: str, leap_text: str) -> bool:
    """Return True iff wrong_explanation and leap_text are each <=200 codepoints.

    Args:
        wrong_explanation: The wrong-answer explanation.
        leap_text: The leap explanation body.

    Returns:
        ``True`` iff both strings are at most ``200`` codepoints (incl. spaces).
    """
    return (
        len(wrong_explanation) <= _EXPLANATION_MAX_LEN
        and len(leap_text) <= _EXPLANATION_MAX_LEN
    )


def check_format(item: QuizItemCandidate) -> QuizItemCandidate:
    """Authoritatively (re)compute ``option_length_ok`` / ``explanation_length_ok``.

    Overrides whatever provisional values quiz_gen stored (the verify stage owns
    these soft flags) and returns a NEW frozen candidate via ``model_copy``.

    Args:
        item: The quiz candidate to format-check.

    Returns:
        A NEW ``QuizItemCandidate`` with recalculated ``option_length_ok`` and
        ``explanation_length_ok``.
    """
    option_length_ok = _compute_option_length_ok(list(item.options))
    explanation_length_ok = _compute_explanation_length_ok(
        item.wrong_explanation, item.leap.text
    )
    return item.model_copy(
        update={
            "option_length_ok": option_length_ok,
            "explanation_length_ok": explanation_length_ok,
        }
    )


def is_confirmed_anchor(item: QuizItemCandidate) -> bool:
    """Return ``True`` iff the item has a confirmed textbook anchor.

    A confirmed anchor is the single authority shared by ``detect_duplicates``
    (anchor-dup keying) and the pipeline's 미확인-exclusion filter (SC-005/G3):
    the evidence must exist, be ``확인``, and carry both ``chunk_id`` and ``line``.
    Both call sites import this predicate so the definition can never diverge.

    Args:
        item: The quiz candidate to test.

    Returns:
        ``True`` if ``textbook_evidence`` is a confirmed (status ``확인``) anchor
        with both ``chunk_id`` and ``line`` set.
    """
    ev = item.textbook_evidence
    return (
        ev is not None
        and ev.status == "확인"
        and ev.chunk_id is not None
        and ev.line is not None
    )


def detect_duplicates(items: list[QuizItemCandidate]) -> list[QuizItemCandidate]:
    """Remove anchor-duplicate candidates by answer textbook anchor (FR-008).

    Duplicates are judged by the answer's textbook anchor
    ``(textbook_evidence.chunk_id, textbook_evidence.line)`` — NOT by
    ``key_concept`` (the retired v0.1.0 chapter-name grouping; contract D1/D4).
    Two candidates with the same anchor key target the same textbook sentence =
    the same question focus = duplicates.

    Among candidates sharing an anchor key the FIRST occurrence (input order) is
    kept and the rest are REMOVED (dropped), so the returned set has zero
    anchor-duplicates (D2).  The pipeline derives any shortfall from the length
    difference; this function only removes (D3 is reported elsewhere).

    Design:
    - An anchor key is formed ONLY for a CONFIRMED anchor:
      ``textbook_evidence is not None`` AND ``status == "확인"`` AND both
      ``chunk_id`` and ``line`` set.
    - Candidates WITHOUT a confirmed anchor (evidence ``None``, ``미확인``, or a
      missing ``chunk_id``/``line``) are NEVER grouped or removed here — they
      pass through unchanged.  Excluding ``미확인`` candidates is a separate stage
      (T029), not dedup's job.
    - Items in the SAME subsection (same ``chunk_id``) but a DIFFERENT ``line``
      are NOT duplicates (different sentence = different focus) — both kept.
    - The ``duplicate_flag`` schema field is retained (D4) but no longer set by
      this function; removal supersedes flagging.
    - Deterministic: stable input order → identical kept set and order.

    Args:
        items: Quiz candidates (input order is the dedup tie-break).

    Returns:
        A new list with anchor-duplicates removed (first occurrence kept); may be
        shorter than ``items``.  Kept candidates are returned unmodified.
    """
    seen: set[tuple[str, int]] = set()
    result: list[QuizItemCandidate] = []
    for item in items:
        evidence = item.textbook_evidence
        if is_confirmed_anchor(item):
            # `is_confirmed_anchor` guarantees chunk_id/line are not None here.
            key = (evidence.chunk_id, evidence.line)  # type: ignore[union-attr]
            if key in seen:
                continue  # anchor-duplicate → drop (first occurrence kept)
            seen.add(key)
        result.append(item)
    return result


def answer_no_distribution(items: list[QuizItemCandidate]) -> dict[int, int]:
    """Record the answer_no distribution for the manifest (no rebalancing).

    This function only *records* the distribution and never alters any
    candidate; the actual rebalancing is done separately by
    :func:`balance_answer_keys` (v0.1.1, R5).  It reads ``answer_no`` and is
    typically called on the already-balanced set for the manifest summary.

    Args:
        items: Quiz candidates whose ``answer_no`` values are counted.

    Returns:
        A dict mapping each answer position ``1..5`` to its count (positions
        with no candidate map to ``0``).
    """
    distribution = dict.fromkeys(range(1, 6), 0)
    for item in items:
        distribution[item.answer_no] += 1
    return distribution


# ---------------------------------------------------------------------------
# Answer-key balance (examen port; spec 010 T023) — reorder answer positions so
# each of 1–5 falls in 15–25% and no run of more than 2 consecutive identical
# answer numbers (i.e. no three-in-a-row).
#
# Ported VERBATIM from ``examen.verify.format_checks`` (deliberate temporary
# duplication, NOT a shared-kernel import — plan Complexity Tracking).  The ONLY
# adaptation: examen's per-option ``distractor_rationale`` becomes maieutica's
# ``option_evidence``, swapped in parallel with ``options``.  The algorithm
# itself operates on the integer ``answer_no`` array and is item-type-agnostic.
# ---------------------------------------------------------------------------

# 보기·근거의 위치를 나타내는 동그라미 번호 접두사 (①..⑤ = U+2460..U+2464).
_CIRCLED_DIGITS = "①②③④⑤"

# 정답 번호 균형 목표 범위 (비율)
_BALANCE_MIN_RATIO = 0.15
_BALANCE_MAX_RATIO = 0.25

# 부동소수점 경계 오차 보정용 epsilon (lo=ceil(0.15·n), hi=floor(0.25·n) 계산 시)
_BALANCE_EPS = 1e-9


def _renumber_circled_prefixes(seq: list[str]) -> list[str]:
    """Rewrite each string's leading circled-digit (①–⑤) to its 1-based position.

    Options and option_evidence may carry a position-denoting circled number as
    their first character.  A positional swap moves the whole string, so the
    prefix must be renumbered afterward — otherwise the visible numbering is
    scrambled (e.g. ``①②⑤④③``).  Strings whose first character is not a circled
    digit are returned unchanged (defensive — no assumption that a prefix exists;
    ``option_evidence`` typically has none, so this is a no-op there).

    Args:
        seq: Option or evidence strings in display order.

    Returns:
        A new list with each leading circled digit set to match its position.
    """
    out: list[str] = []
    for i, s in enumerate(seq):
        if s and s[0] in _CIRCLED_DIGITS and i < len(_CIRCLED_DIGITS):
            out.append(_CIRCLED_DIGITS[i] + s[1:])
        else:
            out.append(s)
    return out


def _swap_answer_to_position(item: QuizItemCandidate, new_pos: int) -> QuizItemCandidate:
    """Swap the correct answer option to ``new_pos`` (1-based) within an item.

    Performs a two-way swap between the current answer position and ``new_pos``:
    - ``options[answer_no-1]`` ↔ ``options[new_pos-1]``
    - ``option_evidence[answer_no-1]`` ↔ ``option_evidence[new_pos-1]`` (parallel
      swap — each option's evidence must move with its option to stay aligned)
    - ``answer_no`` is updated to ``new_pos``

    The correct answer *content* is unchanged — only its position moves.  The V4
    invariant (``answer_explanation_combined``) is untouched because the swap
    never alters ``wrong_explanation`` / ``leap``.
    Pre-condition: ``1 <= new_pos <= 5`` and ``new_pos != item.answer_no``.

    Args:
        item: The quiz candidate to rebalance.
        new_pos: The target 1-based position for the correct answer.

    Returns:
        A new ``QuizItemCandidate`` with the swap applied.
    """
    opts = list(item.options)
    evid = list(item.option_evidence)
    old_idx = item.answer_no - 1
    new_idx = new_pos - 1

    # Swap content
    opts[old_idx], opts[new_idx] = opts[new_idx], opts[old_idx]
    evid[old_idx], evid[new_idx] = evid[new_idx], evid[old_idx]

    # 동그라미 번호 접두사는 위치를 나타내므로 스왑 후 위치에 맞게 재번호한다
    # (보기 본문·근거는 함께 이동했으므로 정합성은 유지된다).
    opts = _renumber_circled_prefixes(opts)
    evid = _renumber_circled_prefixes(evid)

    return item.model_copy(
        update={
            "options": opts,
            "option_evidence": evid,
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


def balance_answer_keys(items: list[QuizItemCandidate]) -> list[QuizItemCandidate]:
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
    ``_swap_answer_to_position`` — moving each item's *correct option* (and its
    parallel ``option_evidence``) to its target slot, so the correct answer
    content is never altered.

    Guarantees:
    - Input length preserved; each item's correct answer content unchanged.
    - Deterministic: identical input → identical output.
    - Idempotent: an already-conforming list is returned unchanged (both phases
      no-op when there is no violation), so ``balance(balance(x)) == balance(x)``.
    - For N in the feasible band (``5·lo ≤ N ≤ 5·hi``) both invariants hold.
      For very small / infeasible N the algorithm does its best and never
      crashes.

    Args:
        items: List of quiz candidates to rebalance.

    Returns:
        New list of ``QuizItemCandidate`` objects with rebalanced answer positions.
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

    result: list[QuizItemCandidate] = []
    for item, target in zip(items, seq, strict=True):
        if item.answer_no != target:
            result.append(_swap_answer_to_position(item, target))
        else:
            result.append(item)
    return result


__all__ = [
    "answer_no_distribution",
    "balance_answer_keys",
    "check_format",
    "detect_duplicates",
    "is_confirmed_anchor",
]
