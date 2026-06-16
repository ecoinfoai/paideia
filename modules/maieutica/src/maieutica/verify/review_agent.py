"""T052 — Auto 2nd-pass review agent (US5, FR-018, R8).

``review_candidates(quiz_items, formative_items, *, backend=None)
    -> tuple[list[QuizItemCandidate], list[FormativeItemCandidate]]``

Two-layer design (Constitution I — deterministic first, LLM optional):

Layer 1 — Deterministic rule checks (always run, no LLM)
---------------------------------------------------------
Aggregates signals already present on each candidate into ``review_note``.
Checks performed (quiz):

- ``option_length_ok is False``  → option length issue note.
- ``explanation_length_ok is False``  → explanation length issue note.
- ``duplicate_flag is True``  → 중복 의심 note.
- ``textbook_evidence.status == "미확인"``  → 교재근거 미확인 note.
- ``leap.textbook_evidence.status == "미확인"``  → 도약근거 미확인 note
  (LEAP BACKSTOP — FR-012 / US2 review comment: verify_groundedness grounds
  the leap only by key_concept, not by scanning leap.text; this pass is the
  backstop for an external-fact leap whose concept happened to be in-range).

Checks performed (formative):
- ``textbook_evidence.status == "미확인"``  → 교재근거 미확인 note.

Clean items keep ``review_note == ""``.

Layer 2 — Optional LLM adversarial pass
-----------------------------------------
Only executed when ``backend`` is provided AND reachable.  Uses a deliberately
different ("이 문항의 결함을 찾아라") adversarial prompt so the cache key is
distinct from generation.  Can flag multi-answer / 교재밖 사실.

If ``backend`` is ``None`` or raises ``BackendUnreachableError``, the layer is
silently skipped — the rule-check results are returned as-is (Constitution I:
degrade to rules-only, no hard stop).

Model mutation
--------------
All models are frozen (Pydantic ``frozen=True``).  Every update uses
``model_copy(update={...})``.  Items with no violations are returned
identity-preserved (no copy).
"""

from __future__ import annotations

from paideia_shared.schemas import FormativeItemCandidate, QuizItemCandidate

from maieutica.generate.backend import BackendUnreachableError, LLMBackend

# ---------------------------------------------------------------------------
# Adversarial LLM review prompt template (layer 2)
# ---------------------------------------------------------------------------

_REVIEW_PROMPT_TEMPLATE = """\
당신은 대학교 퀴즈 문항 품질 검토 전문가입니다.
아래 문항을 검토하고, 발견된 결함만 간결하게 기술하세요.
문제가 없으면 빈 문자열을 반환하세요.

검토 기준:
- 정답 모호: 보기 중 정답이 2개 이상이거나 불명확한 경우
- 보기 중복: 보기 내용이 서로 너무 유사한 경우
- 교재밖 사실: 교재 범위를 벗어난 외부 지식이 포함된 경우

문항:
{item_text}
"""

_REVIEW_TAG = "[review_agent]"


# ---------------------------------------------------------------------------
# Internal helpers — rule checks
# ---------------------------------------------------------------------------


def _check_quiz_rules(item: QuizItemCandidate) -> str:
    """Run deterministic rule checks on one quiz item.

    Args:
        item: The quiz candidate to check.

    Returns:
        A newline-joined string of all rule violations found, or ``""`` if
        the item passes all checks.
    """
    notes: list[str] = []

    if not item.option_length_ok:
        notes.append("option length issue: options outside 30-50 char window")

    if not item.explanation_length_ok:
        notes.append("explanation length issue: wrong_explanation or leap.text exceeds 200 chars")

    if item.duplicate_flag:
        notes.append("중복 의심: 동일 key_concept 중복 후보")

    if item.textbook_evidence is not None and item.textbook_evidence.status == "미확인":
        notes.append("교재근거 미확인: 답안 근거가 교재에서 확인되지 않음")

    if item.leap.textbook_evidence is None:
        # A leap with no grounding info at all is a flaw — verify_groundedness
        # should have attached evidence; its absence means the leap was never
        # anchored (FR-012 backstop).
        notes.append("도약근거 없음: leap 설명에 교재 근거 정보가 전혀 없음")
    elif item.leap.textbook_evidence.status == "미확인":
        notes.append("도약근거 미확인: leap 설명 근거가 교재에서 확인되지 않음")

    return "\n".join(notes)


def _check_formative_rules(item: FormativeItemCandidate) -> str:
    """Run deterministic rule checks on one formative item.

    Args:
        item: The formative candidate to check.

    Returns:
        A newline-joined string of all rule violations found, or ``""`` if
        the item passes all checks.
    """
    notes: list[str] = []

    if item.textbook_evidence is not None and item.textbook_evidence.status == "미확인":
        notes.append("교재근거 미확인: 형성평가 근거가 교재에서 확인되지 않음")

    return "\n".join(notes)


# ---------------------------------------------------------------------------
# Internal helpers — LLM adversarial pass (layer 2)
# ---------------------------------------------------------------------------


def _build_quiz_review_prompt(item: QuizItemCandidate) -> str:
    """Construct the adversarial review prompt for a single quiz item.

    Args:
        item: The quiz candidate to review.

    Returns:
        Formatted prompt string for the backend.
    """
    options_text = "\n".join(f"  {opt}" for opt in item.options)
    evidence_text = (
        item.textbook_evidence.found_text
        if item.textbook_evidence and item.textbook_evidence.found_text
        else "없음"
    )
    leap_text = item.leap.text
    item_text = (
        f"번호: {item.item_no}\n"
        f"문제: {item.text}\n"
        f"보기:\n{options_text}\n"
        f"정답: {item.answer_no}번\n"
        f"도약: {leap_text}\n"
        f"근거: {evidence_text}\n"
    )
    return _REVIEW_PROMPT_TEMPLATE.format(item_text=item_text)


def _apply_llm_review_quiz(
    items: list[QuizItemCandidate],
    backend: LLMBackend,
    *,
    degrade_on_unreachable: bool = True,
) -> list[QuizItemCandidate]:
    """Run LLM adversarial pass on quiz items; append findings to review_note.

    Each item is reviewed independently.  A non-empty LLM response is appended
    to the item's existing ``review_note`` (tagged ``[review_agent]``).

    Args:
        items: Quiz candidates (already have rule-check notes if applicable).
        backend: Reachable LLM backend.
        degrade_on_unreachable: When ``True`` (default, Constitution I), a
            ``BackendUnreachableError`` on any call causes all remaining items
            to be returned unchanged (degrade — no hard stop).  When ``False``
            (CLI api mode), the error propagates so the CLI can map it to exit
            4.

    Returns:
        New list of ``QuizItemCandidate`` with any LLM findings appended.

    Raises:
        BackendUnreachableError: Only when ``degrade_on_unreachable`` is
            ``False`` and the backend is unreachable.
    """
    from maieutica.generate.backend import GenerationRequest  # noqa: PLC0415

    # We cannot guarantee a cache_dir here (no data_root in scope), so we use
    # the backend directly for the adversarial pass.  Each call is keyed by the
    # item content + "review" role inside GenerationRequest — distinct from
    # generation requests.
    result: list[QuizItemCandidate] = []
    for item in items:
        prompt = _build_quiz_review_prompt(item)
        request = GenerationRequest(
            slot_id=f"review-quiz-item{item.item_no}",
            prompt=prompt,
            context_refs=[],
            metadata={
                "role": "adversarial-review",
                "item_no": item.item_no,
                "chapter_no": item.chapter_no,
            },
        )
        try:
            response = backend.generate(request)
        except BackendUnreachableError:
            if not degrade_on_unreachable:
                # CLI api mode: surface unreachability → app() trap → exit 4.
                raise
            # Degrade: skip LLM for this and all remaining items.
            result.append(item)
            result.extend(items[len(result) :])
            return result

        finding = response.raw_text.strip()
        if not finding:
            result.append(item)
            continue

        tagged = finding if finding.startswith(_REVIEW_TAG) else f"{_REVIEW_TAG} {finding}"
        existing = item.review_note or ""
        new_note = f"{existing}\n{tagged}" if existing else tagged
        result.append(item.model_copy(update={"review_note": new_note}))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def review_candidates(
    quiz_items: list[QuizItemCandidate],
    formative_items: list[FormativeItemCandidate],
    *,
    backend: LLMBackend | None = None,
    degrade_on_unreachable: bool = True,
) -> tuple[list[QuizItemCandidate], list[FormativeItemCandidate]]:
    """Run the 2nd-pass review on quiz and formative candidates.

    Two layers:

    1. **Deterministic rule checks** (always run, no LLM): aggregates signals
       already on each candidate into ``review_note``.  Clean items keep
       ``review_note == ""``.
    2. **Optional LLM adversarial pass** (layer 2): only runs when ``backend``
       is provided.  Appends ``[review_agent]``-tagged findings.  If
       ``backend`` is ``None``, layer 2 is skipped (rules-only).  If the
       backend raises ``BackendUnreachableError`` and
       ``degrade_on_unreachable`` is ``True`` (default), layer 2 is silently
       skipped and rule-check results are returned unchanged (Constitution I —
       degrade, no hard stop).

    All models are frozen → ``model_copy`` is used for every update.

    Args:
        quiz_items: Quiz candidates to review.
        formative_items: Formative candidates to review.
        backend: Optional LLM backend for the adversarial pass.  ``None``
            → rules-only (Constitution I degraded mode).
        degrade_on_unreachable: When ``True`` (default), an unreachable backend
            degrades layer 2 to rules-only.  When ``False`` (CLI api mode), the
            ``BackendUnreachableError`` propagates so the CLI can map it to exit
            4.

    Returns:
        ``(reviewed_quiz, reviewed_formative)`` — new lists with ``review_note``
        populated for items that have violations.  Clean items are
        identity-preserved (same object, no copy).

    Raises:
        BackendUnreachableError: Only when ``degrade_on_unreachable`` is
            ``False`` and the backend is unreachable.
    """
    # ----------------------------------------------------------------
    # Layer 1: deterministic rule checks
    # ----------------------------------------------------------------
    reviewed_quiz: list[QuizItemCandidate] = []
    for item in quiz_items:
        note = _check_quiz_rules(item)
        if note:
            reviewed_quiz.append(item.model_copy(update={"review_note": note}))
        else:
            reviewed_quiz.append(item)

    reviewed_formative: list[FormativeItemCandidate] = []
    for item in formative_items:
        note = _check_formative_rules(item)
        if note:
            reviewed_formative.append(item.model_copy(update={"review_note": note}))
        else:
            reviewed_formative.append(item)

    # ----------------------------------------------------------------
    # Layer 2: optional LLM adversarial pass (quiz items only)
    # ----------------------------------------------------------------
    # _apply_llm_review_quiz handles BackendUnreachableError internally when
    # degrade_on_unreachable is True (per item, returning the remaining items
    # unchanged), so the rule-check results always survive (Constitution I).
    # When False (CLI api mode), it re-raises so the CLI maps it to exit 4.
    if backend is not None:
        reviewed_quiz = _apply_llm_review_quiz(
            reviewed_quiz, backend, degrade_on_unreachable=degrade_on_unreachable
        )

    return reviewed_quiz, reviewed_formative


__all__ = ["review_candidates"]
