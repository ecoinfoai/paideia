"""T054 — LLM insight orchestration for retro-mester (US6).

``build_insight(facts, *, llm_mode, require_llm, cache)`` is the single
public entry point for the insight layer.

Mode dispatch:
- ``off``           → ``template_insight(facts)``, ``llm_used=False``.
- ``subscription``  → cache lookup; on miss call ``client.generate``; on
                      success cache + return (text, True); on failure →
                      if ``require_llm`` raise ``LLMRequiredError`` (exit 5),
                      else fall back to template.
- ``api``           → same as subscription but uses the Anthropic SDK path.

Invariants:
- NEVER hard-stops the pipeline unless ``require_llm=True``.
- ``off`` path never imports ``anthropic``.
- The deterministic core (Silver parquet, xlsx, non-LLM report sections,
  yaml) is not touched here — only the ``llm_block`` string varies (SC-009).
"""

from __future__ import annotations

from retro_mester.llm.cache import InputHashCache
from retro_mester.llm.fallback import template_insight


class LLMRequiredError(RuntimeError):
    """Raised when ``require_llm=True`` and the backend is unreachable.

    The pipeline catches this and returns exit code 5.
    """


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(facts: dict) -> str:
    """Build the Korean LLM prompt from structured retro facts.

    Args:
        facts: Dict with ``top_changes``, ``alignment_flags``,
            ``uncovered_ratio``, ``forward_summary``.

    Returns:
        Prompt string in Korean for the insight LLM call.
    """
    top_changes = facts.get("top_changes", [])
    alignment_flags = facts.get("alignment_flags", [])
    uncovered_ratio = facts.get("uncovered_ratio", 0.0)
    forward_summary = facts.get("forward_summary", "")

    changes_block = ""
    for i, rec in enumerate(top_changes[:5], 1):
        changes_block += (
            f"{i}. 단원: {rec.get('chapter', '')}, 집단: {rec.get('segment', '')}, "
            f"원인: {rec.get('cause_hypothesis', '')}, "
            f"처방: {rec.get('prescription_key', '')}\n"
        )

    flags_str = ", ".join(alignment_flags) if alignment_flags else "없음"
    uncovered_pct = uncovered_ratio * 100

    prompt = (
        "당신은 대학교 학기 회고 분석 전문가입니다. "
        "아래 데이터를 바탕으로 교수자에게 실질적인 한국어 인사이트를 제공하세요.\n\n"
        f"[변경 권고 (상위 {len(top_changes)}건)]\n"
        f"{changes_block}\n"
        f"[인지수준 정렬 플래그]: {flags_str}\n"
        f"[미처리 빈틈 비율]: {uncovered_pct:.1f}%\n"
        f"[차년도 방향 요약]: {forward_summary}\n\n"
        "위 데이터를 분석하여 200자 내외의 핵심 인사이트를 한국어로 작성하세요. "
        "번호 매기기나 불릿 없이 자연스러운 단락으로 서술하세요. "
        "학생 ID나 개인 정보를 포함하지 마세요."
    )
    return prompt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_insight(
    facts: dict,
    *,
    llm_mode: str,
    require_llm: bool,
    cache: InputHashCache | None,
) -> tuple[str, bool]:
    """Build the insight text for the retro-mester report.

    Args:
        facts: Structured facts dict with ``top_changes``,
            ``alignment_flags``, ``uncovered_ratio``, ``forward_summary``.
        llm_mode: One of ``"off"``, ``"subscription"``, ``"api"``.
        require_llm: If ``True`` and LLM fails, raise ``LLMRequiredError``
            (pipeline maps to exit code 5) instead of falling back.
        cache: Optional ``InputHashCache`` instance.  ``None`` → no caching.

    Returns:
        ``(insight_text, llm_used)`` where ``llm_used`` is ``True`` iff a
        live LLM response was used (cache hit counts as True).

    Raises:
        LLMRequiredError: When ``require_llm=True`` and the backend fails.
    """
    if llm_mode == "off":
        return template_insight(facts), False

    # Build prompt and check cache first.
    prompt = _build_prompt(facts)

    if cache is not None:
        cached_text = cache.get(prompt, facts)
        if cached_text is not None:
            return cached_text, True

    # Try the LLM backend (lazy import — ``off`` path never reaches here).
    from retro_mester.llm import client  # noqa: PLC0415

    text, failure_kind = client.generate(prompt, mode=llm_mode)

    if text is not None:
        # Success — store in cache and return.
        if cache is not None:
            cache.put(prompt, facts, text)
        return text, True

    # Backend failed.
    if require_llm:
        raise LLMRequiredError(
            f"LLM backend failed (mode={llm_mode!r}, failure={failure_kind!r}) "
            "and --require-llm is set."
        )

    # Graceful degradation → template fallback.
    return template_insight(facts), False


__all__ = ["build_insight", "LLMRequiredError"]
