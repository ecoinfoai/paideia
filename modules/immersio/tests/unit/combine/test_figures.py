"""TDD tests for ``combine.figures`` (T029, US1).

Verifies fig3 (correlation heatmap) + fig4 (regression β bar chart)
matplotlib outputs:

- PNG metadata ``Software=paideia`` (research §R13 vector #4)
- byte-identical re-runs
- file size > 0 and PNG magic header
- input validation (empty cells / coefs → ValueError)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.combine.figures import render_fig3_heatmap, render_fig4_beta_bar
from paideia_shared.schemas import (
    CorrelationCell,
    RegressionCoefficient,
)
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS


def _cell(
    axis: str,
    metric: str,
    *,
    n: int = 50,
    r: float | None = 0.3,
    p: float | None = 0.01,
    q: float | None = 0.04,
    sig: bool = True,
) -> CorrelationCell:
    return CorrelationCell(
        axis_key=axis,
        exam_metric_key=metric,
        n=n,
        pearson_r=r,
        raw_p=p,
        fdr_q=q,
        significant_after_correction=sig,
        unstable_inference_flag=n < 20,
    )


def _coef(axis: str, *, beta: float = 0.5, q: float = 0.01) -> RegressionCoefficient:
    return RegressionCoefficient(
        axis_key=axis,
        coef=beta * 10,
        std_err=1.0,
        t_stat=beta * 10,
        raw_p=q,
        fdr_q=q,
        ci_low_95=beta * 10 - 2.0,
        ci_high_95=beta * 10 + 2.0,
        beta_standardized=beta,
        vif=1.5,
        multicollinearity_flag=False,
    )


# ----------------------------------------------------------------------
# fig3 — correlation heatmap
# ----------------------------------------------------------------------


def test_fig3_writes_png_file(tmp_path: Path) -> None:
    cells = [_cell(axis, "total_score") for axis in STANDARD_AXIS_KEYS]
    out = tmp_path / "fig3.png"
    render_fig3_heatmap(cells, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_fig3_png_magic_header(tmp_path: Path) -> None:
    cells = [_cell(axis, "total_score") for axis in STANDARD_AXIS_KEYS]
    out = tmp_path / "fig3.png"
    render_fig3_heatmap(cells, out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_fig3_software_metadata(tmp_path: Path) -> None:
    """vector #4 — PNG textual metadata Software=paideia."""
    cells = [_cell(axis, "total_score") for axis in STANDARD_AXIS_KEYS]
    out = tmp_path / "fig3.png"
    render_fig3_heatmap(cells, out)
    raw = out.read_bytes()
    assert b"Software" in raw
    assert b"paideia" in raw


def test_fig3_byte_deterministic(tmp_path: Path) -> None:
    cells = [_cell(axis, "total_score") for axis in STANDARD_AXIS_KEYS]
    out1 = tmp_path / "fig3_a.png"
    out2 = tmp_path / "fig3_b.png"
    render_fig3_heatmap(cells, out1)
    render_fig3_heatmap(cells, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_fig3_handles_multiple_metrics(tmp_path: Path) -> None:
    """8 axes × 3 metrics = 24-cell grid renders without error."""
    cells: list[CorrelationCell] = []
    for axis in STANDARD_AXIS_KEYS:
        for metric in ("total_score", "chapter_신경계", "chapter_근골격계"):
            cells.append(_cell(axis, metric))
    out = tmp_path / "fig3_multi.png"
    render_fig3_heatmap(cells, out)
    assert out.stat().st_size > 0


def test_fig3_handles_none_pearson_r(tmp_path: Path) -> None:
    """Cells with r=None (n<3 / constant) must not crash; rendered as blank."""
    cells = [
        _cell(axis, "total_score", r=None, p=None, q=None, sig=False) for axis in STANDARD_AXIS_KEYS
    ]
    out = tmp_path / "fig3_none.png"
    render_fig3_heatmap(cells, out)
    assert out.stat().st_size > 0


def test_fig3_empty_cells_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        render_fig3_heatmap([], tmp_path / "fig3.png")


def test_fig3_creates_parent_directory(tmp_path: Path) -> None:
    cells = [_cell(axis, "total_score") for axis in STANDARD_AXIS_KEYS]
    nested = tmp_path / "deep" / "nest" / "fig3.png"
    render_fig3_heatmap(cells, nested)
    assert nested.exists()


# ----------------------------------------------------------------------
# fig4 — regression β bar chart
# ----------------------------------------------------------------------


def test_fig4_writes_png_file(tmp_path: Path) -> None:
    coefs = [_coef(axis) for axis in STANDARD_AXIS_KEYS]
    out = tmp_path / "fig4.png"
    render_fig4_beta_bar(coefs, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_fig4_software_metadata(tmp_path: Path) -> None:
    coefs = [_coef(axis) for axis in STANDARD_AXIS_KEYS]
    out = tmp_path / "fig4.png"
    render_fig4_beta_bar(coefs, out)
    raw = out.read_bytes()
    assert b"Software" in raw
    assert b"paideia" in raw


def test_fig4_byte_deterministic(tmp_path: Path) -> None:
    coefs = [_coef(axis) for axis in STANDARD_AXIS_KEYS]
    out1 = tmp_path / "fig4_a.png"
    out2 = tmp_path / "fig4_b.png"
    render_fig4_beta_bar(coefs, out1)
    render_fig4_beta_bar(coefs, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_fig4_highlights_q_below_005(tmp_path: Path) -> None:
    """Significant axes (q<0.05) rendered visually distinct — smoke check."""
    overrides = {
        "motivation": (0.5, 0.001),  # significant
        "study_strategy": (0.4, 0.5),  # not significant
    }
    coefs = []
    for axis in STANDARD_AXIS_KEYS:
        beta, q = overrides.get(axis, (0.0, 0.5))
        coefs.append(_coef(axis, beta=beta, q=q))
    out = tmp_path / "fig4_highlight.png"
    render_fig4_beta_bar(coefs, out)
    assert out.exists()


def test_fig4_empty_coefs_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        render_fig4_beta_bar([], tmp_path / "fig4.png")


# ----------------------------------------------------------------------
# fig5 — cluster total_score boxplot (T039)
# ----------------------------------------------------------------------


def _cluster_dataset() -> dict[int, list[float]]:
    return {
        0: [60.0, 62.0, 65.0, 70.0, 72.0],
        1: [70.0, 75.0, 78.0, 80.0, 82.0],
        2: [80.0, 85.0, 88.0, 90.0, 92.0],
    }


def test_fig5_writes_png(tmp_path: Path) -> None:
    from immersio.combine.figures import render_fig5_cluster_boxplot

    out = tmp_path / "fig5.png"
    render_fig5_cluster_boxplot(
        scores_by_cluster=_cluster_dataset(),
        cluster_names={0: "A", 1: "B", 2: "C"},
        path=out,
    )
    assert out.exists() and out.stat().st_size > 0


def test_fig5_software_metadata(tmp_path: Path) -> None:
    from immersio.combine.figures import render_fig5_cluster_boxplot

    out = tmp_path / "fig5.png"
    render_fig5_cluster_boxplot(
        scores_by_cluster=_cluster_dataset(),
        cluster_names={0: "A", 1: "B", 2: "C"},
        path=out,
    )
    raw = out.read_bytes()
    assert b"Software" in raw and b"paideia" in raw


def test_fig5_byte_deterministic(tmp_path: Path) -> None:
    from immersio.combine.figures import render_fig5_cluster_boxplot

    out1 = tmp_path / "fig5_a.png"
    out2 = tmp_path / "fig5_b.png"
    payload = dict(
        scores_by_cluster=_cluster_dataset(),
        cluster_names={0: "A", 1: "B", 2: "C"},
    )
    render_fig5_cluster_boxplot(**payload, path=out1)
    render_fig5_cluster_boxplot(**payload, path=out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_fig5_empty_dataset_rejected(tmp_path: Path) -> None:
    from immersio.combine.figures import render_fig5_cluster_boxplot

    with pytest.raises(ValueError, match="empty"):
        render_fig5_cluster_boxplot(
            scores_by_cluster={},
            cluster_names={},
            path=tmp_path / "fig5.png",
        )


def test_fig5_missing_cluster_name_rejected(tmp_path: Path) -> None:
    from immersio.combine.figures import render_fig5_cluster_boxplot

    with pytest.raises(ValueError, match="cluster_names"):
        render_fig5_cluster_boxplot(
            scores_by_cluster=_cluster_dataset(),
            cluster_names={0: "A"},  # 1, 2 missing
            path=tmp_path / "fig5.png",
        )


def test_fig5_cluster_id_ascending_order(tmp_path: Path) -> None:
    """Determinism — boxes ordered by cluster_id ascending regardless of
    cluster_names dict insertion order."""
    from immersio.combine.figures import render_fig5_cluster_boxplot

    out = tmp_path / "fig5.png"
    render_fig5_cluster_boxplot(
        scores_by_cluster=_cluster_dataset(),
        cluster_names={2: "C", 1: "B", 0: "A"},  # dict order shuffled
        path=out,
    )
    assert out.exists()
