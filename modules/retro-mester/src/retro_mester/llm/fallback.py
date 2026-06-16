"""T053 — Deterministic Korean template fallback for LLM insight.

``template_insight(facts)`` generates a rule-based Korean narrative that
summarises the top changes and alignment signals from the structured facts
dict.  It is used as:
1. The ``off``-mode output (no LLM ever called).
2. The graceful-degradation fallback when an LLM backend is unreachable.

The output is fully deterministic — same ``facts`` input → same string on
every call, regardless of wall-clock time or environment.
"""

from __future__ import annotations


def template_insight(facts: dict) -> str:
    """Build a deterministic Korean narrative from structured retro facts.

    Args:
        facts: Dict with keys:
            - ``top_changes``: list of dicts with ``chapter``,
              ``segment``, ``cause_hypothesis``, ``prescription_key``.
            - ``alignment_flags``: list of flag strings.
            - ``uncovered_ratio``: float 0–1.
            - ``forward_summary``: str describing the forward ledger.

    Returns:
        Non-empty deterministic Korean string suitable for inclusion in the
        MD report insight block.
    """
    top_changes: list[dict] = facts.get("top_changes", [])
    alignment_flags: list[str] = facts.get("alignment_flags", [])
    uncovered_ratio: float = facts.get("uncovered_ratio", 0.0)
    forward_summary: str = facts.get("forward_summary", "")

    lines: list[str] = []

    lines.append("### 회고 핵심 인사이트 (템플릿 생성)")
    lines.append("")

    # --- Top-priority change ---
    if top_changes:
        top = top_changes[0]
        chapter = top.get("chapter", "")
        segment = top.get("segment", "")
        cause = top.get("cause_hypothesis", "")
        prescription = top.get("prescription_key", "")
        lines.append(
            f"이번 학기 가장 시급한 개선 과제는 **{chapter}**({segment}) 단원입니다. "
            f"주요 원인 가설은 '{cause}'이며, 권장 처방은 '{prescription}'입니다."
        )
        lines.append("")

        # Additional changes
        if len(top_changes) > 1:
            lines.append(f"총 {len(top_changes)}개 변경 권고 중 상위 우선순위 단원:")
            for rec in top_changes[:3]:
                ch = rec.get("chapter", "")
                seg = rec.get("segment", "")
                presc = rec.get("prescription_key", "")
                lines.append(f"- **{ch}** ({seg}): {presc}")
            lines.append("")
    else:
        lines.append("이번 학기 변경 권고 사항이 없습니다.")
        lines.append("")

    # --- Uncovered gap ratio ---
    uncovered_pct = uncovered_ratio * 100
    if uncovered_ratio > 0.3:
        lines.append(
            f"미처리 빈틈 비율이 {uncovered_pct:.1f}%로 높습니다. "
            "추가적인 교수·평가 자원 투입을 검토하시기 바랍니다."
        )
    else:
        lines.append(f"미처리 빈틈 비율은 {uncovered_pct:.1f}%로 양호한 수준입니다.")
    lines.append("")

    # --- Alignment flags ---
    if alignment_flags:
        flags_str = ", ".join(alignment_flags)
        lines.append(
            f"인지수준 정렬 검토: {flags_str} 플래그가 감지되었습니다. "
            "교수-평가 정렬 및 인지수준 절벽 단원에 대한 교수법 재설계를 권장합니다."
        )
        lines.append("")

    # --- Forward summary ---
    if forward_summary:
        lines.append(f"차년도 방향: {forward_summary}")
        lines.append("")

    lines.append("*본 분석은 규칙 기반 템플릿으로 생성되었습니다 (LLM 미사용).*")

    return "\n".join(lines)


__all__ = ["template_insight"]
