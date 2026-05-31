"""T053 — Adversarial review agent: re-review items and record findings.

``review_items(items, backend, cache) -> list[ExamItemDraft]``

Performs a SEPARATE adversarial re-review pass distinct from generation.
Each item is submitted to the backend with a review prompt asking the reviewer
to identify problems (정답 모호, 보기 중복, 근거 약함, 외부지식 의심, etc.).

Findings (if any) are APPENDED to the item's ``review_note`` field, tagged
with ``[review_agent]`` so they are distinguishable from format-check notes.

Design
------
- Uses ``InputHashCache`` for determinism: same item content → same review
  response (cache key derived from the item's serialisation + "review" role).
- The cache key intentionally includes ``"role": "review"`` to separate review
  requests from generation requests that share the same slot_id.
- An empty backend response (stripped to ``""``) means the reviewer found
  no issues; the item's ``review_note`` is unchanged.
- Non-empty responses are appended verbatim to ``review_note`` (prefixed with
  ``[review_agent]`` if not already prefixed).
- Never raises on finding content — all findings are recorded, never fatal.

Separation from generation
---------------------------
Generation uses the backend to *produce* items; review uses it to *critique*
them.  Different prompt → different cache key → no cross-contamination.
The ``examen verify`` CLI step invokes review (after build); the build step
itself does NOT call review_items.

Korean comments are allowed; English docstrings/errors required.
"""

from __future__ import annotations

from paideia_shared.schemas import ExamItemDraft

from examen.generate.backend import GenerationRequest, InputHashCache, LLMBackend

# 검토 프롬프트 템플릿 — 실제 LLM 배포 시 사용. FakeBackend 는 무시한다.
_REVIEW_PROMPT_TEMPLATE = """\
당신은 대학교 기말고사 문항 품질 검토 전문가입니다.
아래 문항을 검토하고, 발견된 문제점만 간결하게 기술하세요.
문제가 없으면 빈 문자열을 반환하세요.

검토 기준:
- 정답 모호: 보기 중 정답이 2개 이상이거나 정답이 불명확한 경우
- 보기 중복: 보기 내용이 서로 너무 유사한 경우
- 근거 약함: 교재 근거가 불명확하거나 외부지식에 의존하는 경우
- 외부지식 의심: 교재 범위를 벗어난 내용이 포함된 경우

문항:
{item_text}
"""

# review_note 태그 — 이 접두사로 검토 에이전트 소견을 구분한다
_REVIEW_TAG = "[review_agent]"


def _build_review_prompt(item: ExamItemDraft) -> str:
    """Construct the review prompt for a single item.

    Args:
        item: The exam item to review.

    Returns:
        Formatted prompt string for the backend.
    """
    options_text = "\n".join(f"  {opt}" for opt in item.options)
    evidence_text = (
        item.textbook_evidence.found_text
        if item.textbook_evidence and item.textbook_evidence.found_text
        else "없음"
    )
    item_text = (
        f"번호: {item.item_no}\n"
        f"문제: {item.text}\n"
        f"보기:\n{options_text}\n"
        f"정답: {item.answer_no}번\n"
        f"근거: {evidence_text}\n"
    )
    return _REVIEW_PROMPT_TEMPLATE.format(item_text=item_text)


def review_items(
    items: list[ExamItemDraft],
    *,
    backend: LLMBackend,
    cache: InputHashCache,
) -> list[ExamItemDraft]:
    """Run adversarial review on each item, appending findings to review_note.

    This is a separate pass from generation.  It is called by ``examen verify``
    after the build pipeline has produced items.  It uses the same
    ``InputHashCache`` and ``LLMBackend`` interfaces, keyed with a distinct
    "review" role to avoid cache collisions with generation requests.

    For each item:
    1. Build a review prompt including the item's text, options, and answer_no.
    2. Compute a deterministic cache key (item content + review role).
    3. Call ``cache.generate(request)`` — hits cache on re-runs.
    4. If the response is non-empty, append to ``item.review_note`` (tagged
       with ``[review_agent]``).  If empty → item unchanged.

    Args:
        items: List of exam items to review.
        backend: LLM backend (FakeBackend in tests, real backend in production).
        cache: ``InputHashCache`` wrapping the backend for determinism.

    Returns:
        New list of ``ExamItemDraft`` objects with any review findings appended
        to ``review_note``.  Items with no finding are returned as-is (identity
        preserved where possible).
    """
    result: list[ExamItemDraft] = []

    for item in items:
        prompt = _build_review_prompt(item)

        # 캐시 키 분리: slot_id 에 "review-" 접두사 + item_no 를 포함해
        # 생성 요청과 겹치지 않게 한다.
        request = GenerationRequest(
            slot_id=f"review-item{item.item_no}",
            prompt=prompt,
            context_refs=[],
            metadata={
                "role": "review",
                "item_no": item.item_no,
                "source": item.source,
                "chapter": item.chapter,
            },
        )

        response = cache.generate(request)
        finding = response.raw_text.strip()

        if not finding:
            # 검토 에이전트가 문제를 발견하지 못함 → item 변경 없음
            result.append(item)
            continue

        # 기존 review_note 에 추가 (덮어쓰지 않음)
        # finding 이 이미 [review_agent] 태그를 가지면 그대로, 없으면 태그를 붙인다.
        if not finding.startswith(_REVIEW_TAG):
            finding = f"{_REVIEW_TAG} {finding}"

        existing = item.review_note or ""
        new_note = f"{existing}\n{finding}" if existing else finding

        result.append(item.model_copy(update={"review_note": new_note}))

    return result


__all__ = ["review_items"]
