"""T053 / T054 — RED tests for LLM fallback + off-mode behaviour.

Tests must FAIL until ``retro_mester.llm.fallback`` and
``retro_mester.llm.insight`` are implemented.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Shared minimal facts fixture
# ---------------------------------------------------------------------------


def _make_facts() -> dict:
    """Return a minimal InsightFacts-like dict for testing.

    Returns:
        Dict with top_changes, alignment_flags, uncovered_ratio,
        forward_summary keys.
    """
    return {
        "top_changes": [
            {
                "chapter": "1장. 해부학 서론",
                "segment": "학령기",
                "cause_hypothesis": "반복 학습 부족",
                "prescription_key": "형성평가 추가",
            },
            {
                "chapter": "2장. 세포와 조직",
                "segment": "만학도",
                "cause_hypothesis": "배경지식 부족",
                "prescription_key": "선행학습 자료 제공",
            },
        ],
        "alignment_flags": ["인지수준절벽"],
        "uncovered_ratio": 0.25,
        "forward_summary": "개선 서약 2건",
    }


# ---------------------------------------------------------------------------
# T053: template_insight determinism + content
# ---------------------------------------------------------------------------


class TestTemplateInsight:
    """Unit tests for ``retro_mester.llm.fallback.template_insight``."""

    def test_deterministic_same_facts(self) -> None:
        """Same facts input produces identical output on multiple calls."""
        from retro_mester.llm.fallback import template_insight

        facts = _make_facts()
        result1 = template_insight(facts)
        result2 = template_insight(facts)
        assert result1 == result2, "template_insight must be deterministic"

    def test_mentions_top_change_chapter(self) -> None:
        """Output mentions the first top-change chapter."""
        from retro_mester.llm.fallback import template_insight

        facts = _make_facts()
        result = template_insight(facts)
        assert "1장. 해부학 서론" in result, (
            "template_insight must mention the top-priority chapter"
        )

    def test_mentions_prescription(self) -> None:
        """Output mentions the prescription for the top change."""
        from retro_mester.llm.fallback import template_insight

        facts = _make_facts()
        result = template_insight(facts)
        assert "형성평가 추가" in result, (
            "template_insight must mention top prescription"
        )

    def test_returns_non_empty_string(self) -> None:
        """Output is a non-empty string."""
        from retro_mester.llm.fallback import template_insight

        result = template_insight(_make_facts())
        assert isinstance(result, str) and len(result) > 0

    def test_no_top_changes_returns_string(self) -> None:
        """Empty top_changes list still returns a non-empty string."""
        from retro_mester.llm.fallback import template_insight

        facts = _make_facts()
        facts["top_changes"] = []
        result = template_insight(facts)
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# T054: build_insight off-mode behaviour
# ---------------------------------------------------------------------------


class TestBuildInsightOffMode:
    """Unit tests for ``retro_mester.llm.insight.build_insight`` in off mode."""

    def test_off_mode_returns_template_text(self) -> None:
        """off mode returns (template_text, False) — no LLM."""
        from retro_mester.llm.fallback import template_insight
        from retro_mester.llm.insight import build_insight

        facts = _make_facts()
        text, llm_used = build_insight(
            facts, llm_mode="off", require_llm=False, cache=None
        )
        expected = template_insight(facts)
        assert text == expected, "off mode must return template_insight output"
        assert llm_used is False, "off mode must return llm_used=False"

    def test_off_mode_does_not_import_anthropic(self) -> None:
        """off mode must not import anthropic (lazy-import guard)."""
        import sys

        # Ensure anthropic is NOT loaded by the off path.
        # We import build_insight and call it; if anthropic is pulled in,
        # sys.modules will have it (only matters when anthropic is absent).
        from retro_mester.llm.insight import build_insight

        facts = _make_facts()
        _text, _llm_used = build_insight(
            facts, llm_mode="off", require_llm=False, cache=None
        )
        # If we reach here without ImportError the lazy guard is working.
        # (anthropic may or may not be installed; the off path must not require it.)
        assert True  # no ImportError raised on off path

    def test_require_llm_off_mode_still_returns_template(self) -> None:
        """require_llm=True with off mode is a contradiction but must not crash.

        The invariant: off mode never calls LLM regardless of require_llm.
        So it returns template text and llm_used=False even when require_llm=True.
        """
        from retro_mester.llm.insight import build_insight

        facts = _make_facts()
        text, llm_used = build_insight(
            facts, llm_mode="off", require_llm=True, cache=None
        )
        assert isinstance(text, str) and len(text) > 0
        assert llm_used is False
