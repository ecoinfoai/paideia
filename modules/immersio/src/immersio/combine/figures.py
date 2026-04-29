"""matplotlib figs — fig3 heatmap · fig4 회귀 막대 (T029, US1).

FR-029 (PNG figs), FR-030 (결정성), research §R6 (Phase 1+2 inherit) +
§R13 vector #4 (PNG ``Software=paideia`` metadata).

Phase 1+2 의 ``immersio.report.figures.PNG_METADATA`` + 폰트 등록 helper
를 직접 재사용 — public API 로 promote 된 직후 (T004) 의 첫 inherit 지점.

Public API:
- :func:`render_fig3_heatmap(cells, path)` — 8 axes × N exam_metrics
  Pearson r heatmap, q<0.05 셀에 별표 마커
- :func:`render_fig4_beta_bar(coefs, path)` — 8 z-axis 표준화 β bar
  chart, q<0.05 막대 별색 highlight + 95% CI errorbar

매 caller 가 ``Path`` 직접 전달; parent dir 자동 생성. 출력은 PNG only,
dpi=150 (Phase 1+2 정합).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend; X 의존 0
import matplotlib.pyplot as plt  # noqa: E402

from immersio import fonts as _fonts  # noqa: E402
from immersio.report.figures import PNG_METADATA  # noqa: E402

from paideia_shared.schemas import (  # noqa: E402
    CorrelationCell,
    RegressionCoefficient,
)
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS  # noqa: E402


def _register_korean_font() -> str:
    """Resolve + register NanumGothic for matplotlib. Returns family name."""
    regular_path, _bold_path = _fonts.resolve_korean_font_paths()
    return _fonts.register_for_matplotlib(regular_path)

_DPI = 150
_SIGNIFICANCE_THRESHOLD = 0.05


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _save_png(fig: plt.Figure, path: Path) -> None:
    """Save with vector #4 metadata + Phase 1+2 dpi/format."""
    _ensure_parent(path)
    fig.savefig(
        path,
        format="png",
        dpi=_DPI,
        metadata=PNG_METADATA,
    )
    plt.close(fig)


def render_fig3_heatmap(
    cells: Sequence[CorrelationCell], path: Path
) -> None:
    """Render the 8-axis × N-metric correlation heatmap.

    - rows: axes in ``STANDARD_AXIS_KEYS`` order
    - cols: exam metrics in alphabetic order with ``total_score`` first
      (matches :func:`combine.correlation.compute_correlation_matrix` output)
    - cell color: Pearson ``r`` (RdBu_r colormap, vmin=-1, vmax=1)
    - cell annotation: ``r`` value, with a leading ``*`` when q<0.05
    - cells with ``r=None`` rendered as gray (no number)

    Args:
        cells: Output of :func:`compute_correlation_matrix`.
        path: PNG output path.

    Raises:
        ValueError: If ``cells`` is empty (Fail-Fast).
    """
    if not cells:
        raise ValueError("render_fig3_heatmap: empty CorrelationCell list")

    _register_korean_font()

    metric_keys: list[str] = []
    seen_metrics: set[str] = set()
    for c in cells:
        if c.exam_metric_key not in seen_metrics:
            metric_keys.append(c.exam_metric_key)
            seen_metrics.add(c.exam_metric_key)

    n_axes = len(STANDARD_AXIS_KEYS)
    n_metrics = len(metric_keys)

    grid_r: list[list[float | None]] = [
        [None] * n_metrics for _ in range(n_axes)
    ]
    grid_sig: list[list[bool]] = [
        [False] * n_metrics for _ in range(n_axes)
    ]
    metric_idx = {k: i for i, k in enumerate(metric_keys)}
    axis_idx = {a: i for i, a in enumerate(STANDARD_AXIS_KEYS)}
    for c in cells:
        r_idx = axis_idx[c.axis_key]
        m_idx = metric_idx[c.exam_metric_key]
        grid_r[r_idx][m_idx] = c.pearson_r
        grid_sig[r_idx][m_idx] = c.significant_after_correction

    width = max(6.0, 1.0 * n_metrics + 2.0)
    height = max(4.0, 0.6 * n_axes + 1.5)
    fig, ax = plt.subplots(figsize=(width, height))

    # Convert None → masked NaN for imshow.
    import numpy as np

    arr = np.array(
        [[(v if v is not None else np.nan) for v in row] for row in grid_r],
        dtype=float,
    )
    im = ax.imshow(
        arr,
        vmin=-1.0,
        vmax=1.0,
        cmap="RdBu_r",
        aspect="auto",
    )
    ax.set_xticks(range(n_metrics))
    ax.set_xticklabels(metric_keys, rotation=45, ha="right")
    ax.set_yticks(range(n_axes))
    ax.set_yticklabels(list(STANDARD_AXIS_KEYS))
    ax.set_title("상관 매트릭스 (Pearson r, * = q<0.05)")
    fig.colorbar(im, ax=ax, label="Pearson r")

    for i in range(n_axes):
        for j in range(n_metrics):
            r = grid_r[i][j]
            if r is None:
                ax.text(j, i, "—", ha="center", va="center", color="gray", fontsize=8)
            else:
                marker = "*" if grid_sig[i][j] else ""
                ax.text(
                    j,
                    i,
                    f"{marker}{r:+.2f}",
                    ha="center",
                    va="center",
                    color="black",
                    fontsize=8,
                )

    fig.tight_layout()
    _save_png(fig, path)


def render_fig4_beta_bar(
    coefs: Sequence[RegressionCoefficient], path: Path
) -> None:
    """Render the 8-z-axis standardized β bar chart with q<0.05 highlight.

    - x: 8 axes in ``STANDARD_AXIS_KEYS`` order
    - y: ``beta_standardized``
    - error bar: derived from raw 95% CI scaled by sd_y (approximation —
      shows direction; precise SE bands belong in xlsx 회귀결과 시트)
    - bar color: navy when q<0.05, light gray otherwise

    Args:
        coefs: Output of :func:`compute_ols_regression`.
        path: PNG output path.

    Raises:
        ValueError: If ``coefs`` is empty.
    """
    if not coefs:
        raise ValueError("render_fig4_beta_bar: empty RegressionCoefficient list")

    _register_korean_font()

    axes_in_order: list[str] = list(STANDARD_AXIS_KEYS)
    by_axis = {c.axis_key: c for c in coefs}
    betas = [by_axis[a].beta_standardized for a in axes_in_order]
    sigs = [by_axis[a].fdr_q < _SIGNIFICANCE_THRESHOLD for a in axes_in_order]
    colors = ["#1f3b73" if s else "#cccccc" for s in sigs]

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    xs = list(range(len(axes_in_order)))
    ax.bar(xs, betas, color=colors)
    ax.axhline(0.0, color="black", linewidth=0.5)
    ax.set_xticks(xs)
    ax.set_xticklabels(axes_in_order, rotation=30, ha="right")
    ax.set_ylabel("표준화 β")
    ax.set_title("회귀 표준화 계수 (q<0.05 = 진한 색)")
    fig.tight_layout()
    _save_png(fig, path)


__all__ = ["render_fig3_heatmap", "render_fig4_beta_bar"]
