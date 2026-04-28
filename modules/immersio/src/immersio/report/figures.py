"""Score histogram + metadata grouped-bar figures (T043, FR-022, R-11).

Two PNG builders consumed by ``시험분석결과.xlsx`` chart anchors and by
``시험품질보고서.{md,pdf}`` body. Both share these determinism axes:

* ``matplotlib.use("Agg")`` headless backend (no GUI / X dependency).
* dpi 150 + ``bbox_inches='tight'`` so two renders stay byte-identical.
* PNG ``Software`` metadata pinned to ``"paideia"`` via
  ``Figure.savefig(metadata={...})`` — exempt from matplotlib's default
  build-time injection so two runs hash equal.
* NanumGothic registered via ``immersio.fonts.register_for_matplotlib``;
  CLI pre-flight raises ``KoreanFontUnavailableError`` (exit 6) when the
  font is missing — the figure builders trust resolution and do not
  fall back silently (Constitution V).

The wrappers thinly route ``analysis.histogram`` /
``analysis.metadata_stats`` outputs into matplotlib so US3 legacy_diff +
US1 boundary tests can share a single render path.
"""

from __future__ import annotations

import io
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from paideia_shared.schemas import HistogramBin, MetadataAggregate  # noqa: E402

from .. import fonts as _fonts  # noqa: E402

_PNG_METADATA: dict[str, str] = {"Software": "paideia"}
_DPI = 150


def _ensure_korean_font() -> str:
    """Resolve + register NanumGothic for matplotlib. Returns family name."""
    regular_path, _bold_path = _fonts.resolve_korean_font_paths()
    return _fonts.register_for_matplotlib(regular_path)


def _save(fig, output_path: Path) -> None:
    """Save ``fig`` to ``output_path`` with the deterministic kwargs."""
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise FileNotFoundError(
            f"render figure: parent directory missing: {output_path.parent}"
        )
    # Render to a buffer first so the on-disk write is one atomic
    # operation; this also lets two consecutive calls share the same
    # internal byte stream regardless of OS-level write timing.
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=_DPI,
        bbox_inches="tight",
        metadata=_PNG_METADATA,
    )
    plt.close(fig)
    output_path.write_bytes(buf.getvalue())


def render_fig1_score_histogram(
    *,
    bins: Sequence[HistogramBin],
    output_path: Path,
) -> None:
    """Render the score-histogram bar chart used by `1_히스토그램`/보고서.

    Args:
        bins: Output of ``compute_score_histogram``; ``bin_start``/
            ``bin_end``/``count`` are consumed.
        output_path: Target ``.png`` path. Parent directory must exist.

    Raises:
        ValueError: When ``bins`` is empty.
        KoreanFontUnavailableError: When NanumGothic cannot be resolved.
    """
    if not bins:
        raise ValueError("render_fig1_score_histogram: bins is empty")

    _ensure_korean_font()

    starts = [b.bin_start for b in bins]
    counts = [b.count for b in bins]
    widths = [(b.bin_end - b.bin_start) for b in bins]
    labels = [f"{int(b.bin_start)}~{int(b.bin_end)}" for b in bins]

    fig, ax = plt.subplots(figsize=(8, 4), dpi=_DPI)
    ax.bar(
        starts,
        counts,
        width=widths,
        align="edge",
        edgecolor="black",
        color="#888888",
    )
    ax.set_xticks([b.bin_start + (b.bin_end - b.bin_start) / 2 for b in bins])
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_xlabel("점수 구간")
    ax.set_ylabel("응시자 수")
    ax.set_title("전체 성적 히스토그램")
    fig.tight_layout()
    _save(fig, output_path)


def render_fig2_metadata_correct_rates(
    *,
    rows: Sequence[MetadataAggregate],
    output_path: Path,
) -> None:
    """Render the metadata grouped-bar chart used by `2_메타데이터통계`/보고서.

    Args:
        rows: Output of ``compute_metadata_aggregates``.
        output_path: Target ``.png`` path.

    Raises:
        ValueError: When ``rows`` is empty.
        KoreanFontUnavailableError: When NanumGothic cannot be resolved.
    """
    if not rows:
        raise ValueError("render_fig2_metadata_correct_rates: rows is empty")

    _ensure_korean_font()

    by_kind: dict[str, list[MetadataAggregate]] = defaultdict(list)
    for r in rows:
        by_kind[r.metadata_kind].append(r)

    kinds = sorted(by_kind.keys())
    fig, ax = plt.subplots(figsize=(10, 5), dpi=_DPI)

    bar_width = 0.18
    # Build a flat (kind, value, mean) sequence so the colour cycle stays
    # stable across runs (matplotlib's default rcParams are deterministic).
    x_positions: list[float] = []
    means: list[float] = []
    labels: list[str] = []
    cursor = 0.0
    for kind in kinds:
        for r in by_kind[kind]:
            x_positions.append(cursor)
            means.append(r.mean if r.mean is not None else 0.0)
            labels.append(f"{kind}\n{r.metadata_value}")
            cursor += bar_width
        cursor += bar_width  # gap between kind groups

    ax.bar(x_positions, means, width=bar_width, color="#5588BB", edgecolor="black")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("평균 점수")
    ax.set_title("메타데이터별 평균 점수")
    fig.tight_layout()
    _save(fig, output_path)


__all__ = [
    "render_fig1_score_histogram",
    "render_fig2_metadata_correct_rates",
]
