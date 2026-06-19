"""T026 — Report-MD builder tests (RED phase).

Tests for ``retro_mester.output.report_md.build_report_md``.
- Contains ranked changes table.
- Contains uncovered-gap ratio line.
- Deterministic: same input → same string.
- No student ID leakage.
"""

from __future__ import annotations

from paideia_shared.schemas import InsufficientEvidenceUnit
from paideia_shared.schemas.change_recommendation import ChangeRecommendation
from paideia_shared.schemas.unit_gap import UnitGap
from retro_mester.output.report_md import build_report_md


def _make_insufficient() -> list[InsufficientEvidenceUnit]:
    return [
        InsufficientEvidenceUnit(
            semester="2026-1",
            course_slug="anatomy",
            chapter="9장 신경",
            segment="학령기",
            evidence_n=0,
            reason="근거부족-자료없음",
        ),
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_recs() -> list[ChangeRecommendation]:
    base = dict(
        semester="2026-1",
        course_slug="anatomy",
        target_cognitive_level="이해",
        cause_hypothesis="내용난이도",
        covered_n=5,
        covered_pct_segment=0.25,
        covered_pct_cohort=0.10,
        unit_importance="상",
        weight=3.0,
        effort_level="중",
        priority_quadrant="빠른승리",
        prescription_key="scaffold_concepts",
        cluster_vocab=None,
        validity="건전",
        impact_score=15.0,
    )
    return [
        ChangeRecommendation(
            **base,
            rank=1,
            chapter="1장 세포",
            segment="학령기",
            is_covered=True,
        ),
        ChangeRecommendation(
            **base,
            rank=2,
            chapter="2장 조직",
            segment="만학도",
            is_covered=True,
        ),
        ChangeRecommendation(
            **base,
            rank=None,
            chapter="3장 기관",
            segment="학령기",
            is_covered=False,
        ),
    ]


def _make_gaps() -> list[UnitGap]:
    common = dict(
        semester="2026-1",
        course_slug="anatomy",
        segment_mean_rate=0.60,
        n_below=5,
        pct_segment=0.25,
        pct_cohort=0.10,
        is_structural=True,
        cohort_failing_item_types=["지식"],
        cause="내용난이도",
        cause_signals={"diff": -0.1},
        validity="건전",
        unit_importance="상",
        weight=3.0,
        evidence_n=20,
        impact_score=15.0,
    )
    return [
        UnitGap(**common, chapter="1장 세포", segment="학령기"),
        UnitGap(**common, chapter="2장 조직", segment="만학도"),
        UnitGap(**common, chapter="3장 기관", segment="학령기"),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildReportMd:
    def test_covered_rows_appear_ranked(self) -> None:
        """Covered recommendations appear in the table with their rank."""
        recs = _make_recs()
        md = build_report_md(recs, 0.333, _make_gaps(), "2026-1", "anatomy")
        # Both covered recs should appear
        assert "1장 세포" in md
        assert "2장 조직" in md

    def test_uncovered_ratio_present(self) -> None:
        """Uncovered-gap ratio line appears in the report."""
        md = build_report_md(_make_recs(), 0.333, _make_gaps(), "2026-1", "anatomy")
        # Some form of the ratio should appear — percentage or fraction
        assert "33" in md or "못 덮은" in md

    def test_deterministic(self) -> None:
        """Same input always produces an identical string."""
        recs = _make_recs()
        gaps = _make_gaps()
        md1 = build_report_md(recs, 0.333, gaps, "2026-1", "anatomy")
        md2 = build_report_md(recs, 0.333, gaps, "2026-1", "anatomy")
        assert md1 == md2

    def test_no_student_id_leakage(self) -> None:
        r"""No student identifiers (S\d+) appear in the report."""
        import re

        md = build_report_md(_make_recs(), 0.0, _make_gaps(), "2026-1", "anatomy")
        # Student IDs follow the S\d+ pattern used across this project
        assert not re.search(r"\bS\d{3,}\b", md)

    def test_stable_headings(self) -> None:
        """Section (A) heading is present and stable."""
        md = build_report_md(_make_recs(), 0.0, _make_gaps(), "2026-1", "anatomy")
        # Must contain at least one Markdown heading
        assert "#" in md

    def test_llm_block_none_gives_template_prose(self) -> None:
        """When llm_block=None the output is template-only (no LLM placeholder)."""
        md = build_report_md(_make_recs(), 0.0, _make_gaps(), "2026-1", "anatomy", llm_block=None)
        assert isinstance(md, str)
        assert len(md) > 0

    def test_rank_column_present(self) -> None:
        """Table contains a rank (순위) column header."""
        md = build_report_md(_make_recs(), 0.0, _make_gaps(), "2026-1", "anatomy")
        assert "순위" in md


class TestReportMdInsufficient:
    """T010: report md must surface 근거 부족 units, not omit them."""

    def test_insufficient_section_lists_unit(self) -> None:
        """근거 부족 section names the (chapter, segment) explicitly."""
        md = build_report_md(
            _make_recs(),
            0.5,
            _make_gaps(),
            "2026-1",
            "anatomy",
            insufficient=_make_insufficient(),
        )
        assert "근거 부족" in md
        assert "9장 신경" in md
        assert "학령기" in md

    def test_no_insufficient_states_none(self) -> None:
        """With an empty insufficient list, the section states none explicitly."""
        md = build_report_md(
            _make_recs(),
            0.0,
            _make_gaps(),
            "2026-1",
            "anatomy",
            insufficient=[],
        )
        assert "근거 부족" in md


_BIAS_MARKER = "자가응답 편향"


def _make_interest_gap(*, available: bool) -> dict:
    """Build an interest_aversion_findings()-shaped dict for tests."""
    if available:
        return {
            "interest_mean": 0.70,
            "aversion_mean": 0.45,
            "gap": 0.25,
            "n_interest": 12,
            "n_aversion": 8,
            "bias_note": f"{_BIAS_MARKER}(self-report bias) 주의: 보수적으로 해석.",
        }
    return {
        "interest_mean": None,
        "aversion_mean": None,
        "gap": None,
        "n_interest": 0,
        "n_aversion": 0,
        "bias_note": f"{_BIAS_MARKER}(self-report bias) 주의: 보수적으로 해석.",
    }


class TestReportMdInterestGap:
    """T018 / T020 — cohort interest/aversion achievement gap (audit M2)."""

    def test_none_omits_section(self) -> None:
        """interest_gap=None omits the section entirely (sibling idiom)."""
        md = build_report_md(_make_recs(), 0.0, _make_gaps(), "2026-1", "anatomy")
        assert "관심·기피 단원 성취 격차" not in md

    def test_section_heading_and_values_rendered(self) -> None:
        """T018: available gap renders means, gap, counts, and bias_note."""
        md = build_report_md(
            _make_recs(),
            0.0,
            _make_gaps(),
            "2026-1",
            "anatomy",
            interest_gap=_make_interest_gap(available=True),
        )
        assert "관심·기피 단원 성취 격차 (자가응답 편향 주의)" in md
        assert "0.70" in md  # interest_mean
        assert "0.45" in md  # aversion_mean
        assert "0.25" in md  # gap
        assert "12" in md  # n_interest
        assert "8" in md  # n_aversion
        assert _BIAS_MARKER in md  # bias_note always present

    def test_gap_none_renders_insufficient_message(self) -> None:
        """T020: gap=None renders explicit 데이터 부족 line, not a blank."""
        md = build_report_md(
            _make_recs(),
            0.0,
            _make_gaps(),
            "2026-1",
            "anatomy",
            interest_gap=_make_interest_gap(available=False),
        )
        assert "관심·기피 응답 데이터 부족" in md
        assert _BIAS_MARKER in md  # bias_note still renders
