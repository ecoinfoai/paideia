"""T027 — Unit tests for ``retro_mester.output.figures``.

Covers legend correctness for render_cliff_bar: the baseline reference
line (axhline label "기준선(0.6)") must appear in the legend.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas.alignment_finding import AlignmentFinding


def _make_findings() -> list[AlignmentFinding]:
    """Return two minimal AlignmentFinding stubs with cognitive_profile data."""
    return [
        AlignmentFinding(
            semester="2026-1",
            course_slug="anatomy",
            chapter="1장 세포",
            taught_weeks=3,
            tested_items=10,
            learned_rate=0.72,
            cognitive_profile={"지식": 0.70, "이해": 0.75},
            flag="정렬됨",
            note="정렬 양호",
        ),
        AlignmentFinding(
            semester="2026-1",
            course_slug="anatomy",
            chapter="2장 조직",
            taught_weeks=2,
            tested_items=8,
            learned_rate=0.45,
            cognitive_profile={"지식": 0.40, "이해": 0.50},
            flag="인지수준절벽",
            note="절벽 감지",
        ),
    ]


class TestRenderCliffBarLegend:
    """T027 — baseline label must be included in the cliff bar legend."""

    def test_baseline_label_in_legend(self, tmp_path: Path) -> None:
        """'기준선(0.6)' must appear in the axes legend after render_cliff_bar.

        The axhline call sets label='기준선(0.6)'.  If ax.legend() is
        called BEFORE the axhline, the label is not captured.  This test
        verifies that the legend is built AFTER the axhline so the baseline
        reference line is visible in the chart legend.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import retro_mester.output.figures as fig_mod
        from retro_mester.output.figures import render_cliff_bar

        # Monkey-patch _save_png to capture the figure's axes before it is
        # closed, without preventing the file from being written.
        captured: list = []
        original_save = fig_mod._save_png

        def _capture(fig: plt.Figure, path: Path) -> None:
            captured.append(fig.axes[0] if fig.axes else None)
            original_save(fig, path)

        fig_mod._save_png = _capture
        try:
            out = tmp_path / "figs" / "cliff.png"
            render_cliff_bar(_make_findings(), out)
        finally:
            fig_mod._save_png = original_save

        assert captured, "No axes captured — _save_png was not called"
        ax = captured[0]
        assert ax is not None
        legend = ax.get_legend()
        assert legend is not None, "No legend object on axes"
        legend_texts = [t.get_text() for t in legend.get_texts()]
        assert "기준선(0.6)" in legend_texts, (
            f"'기준선(0.6)' not found in rendered legend: {legend_texts!r}. "
            "ax.legend() must be called AFTER ax.axhline(label='기준선(0.6)')."
        )
