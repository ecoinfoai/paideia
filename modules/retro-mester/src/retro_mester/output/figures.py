"""T047 — PNG figure generation for retro-mester (US4).

Produces:
- ``fig_align_cliff.png``: Chapter × item_type grouped bar chart showing
  cognitive-profile correct rates with the cliff threshold line.
- ``fig_align_map.png``: Chapter × alignment_flag horizontal bar chart
  (learned_rate with flag colour encoding).

Determinism:
- Matplotlib Agg backend (headless, no X dependency).
- dpi=150 (matches immersio/examen convention).
- ``Software=paideia`` PNG metadata (pinned to ``PINNED_DATE``).
- Fixed font metrics via NanumGothic registration.
- No datetime calls in render path.

Self-contained: does not import from immersio.  Font resolution reuses
``retro_mester.output.fonts``.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend — no X dependency
import matplotlib.pyplot as plt  # noqa: E402
from paideia_shared.schemas.alignment_finding import AlignmentFinding

from retro_mester.output.fonts import (
    KoreanFontUnavailableError,
    resolve_korean_font_paths,
)

# ---------------------------------------------------------------------------
# Determinism constants
# ---------------------------------------------------------------------------

# Pinned creation date embedded in PNG metadata — makes PNGs byte-identical
# across runs (no wall-clock datetime in the metadata path).
_PINNED_DATE = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)

_PNG_METADATA: dict[str, str] = {
    "Software": "paideia",
    "CreationTime": _PINNED_DATE.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "Comment": "retro-mester alignment figure",
}

_DPI: int = 150

# Colour map for alignment flags (deterministic)
_FLAG_COLOURS: dict[str, str] = {
    "정렬됨": "#4CAF50",
    "인지수준절벽": "#F44336",
    "과소교수-과다평가": "#FF9800",
    "과다교수-과소평가": "#2196F3",
    "기대-실제괴리": "#9C27B0",
}
_DEFAULT_FLAG_COLOUR = "#9E9E9E"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _try_register_korean_font() -> str | None:
    """Register NanumGothic for matplotlib; return family name or None.

    Returns:
        Font family name string on success, or ``None`` if NanumGothic
        is unavailable (silently degrades to matplotlib default sans-serif).
    """
    try:
        regular_path, _ = resolve_korean_font_paths()
    except KoreanFontUnavailableError:
        return None

    try:
        from matplotlib import font_manager as fm

        fe = fm.FontEntry(fname=str(regular_path), name="NanumGothic")
        fm.fontManager.ttflist.append(fe)
        return "NanumGothic"
    except Exception:
        return None


def _save_png(fig: plt.Figure, path: Path) -> None:
    """Save ``fig`` as PNG with pinned metadata, then close it.

    Args:
        fig: matplotlib Figure to save.
        path: Destination path; parent directory must exist.
    """
    fig.savefig(
        path,
        format="png",
        dpi=_DPI,
        metadata=_PNG_METADATA,
        bbox_inches="tight",
    )
    plt.close(fig)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Public render functions
# ---------------------------------------------------------------------------


def render_cliff_bar(
    findings: list[AlignmentFinding],
    path: Path,
) -> None:
    """Render a grouped bar chart of cognitive_profile rates per chapter.

    One group per chapter; each bar in the group is one item_type.
    Chapters without cognitive_profile data are skipped.

    Deterministic: fixed font, dpi, metadata — two calls with identical
    ``findings`` produce byte-identical PNG files.

    Args:
        findings: List of AlignmentFinding (from build_alignment).
        path: Destination PNG path.
    """
    import numpy as np

    _ensure_parent(path)
    font_family = _try_register_korean_font()
    rc_params: dict = {}
    if font_family:
        rc_params["font.family"] = font_family

    # Collect all item_types in a deterministic order (sorted)
    all_types: list[str] = sorted(
        {itype for f in findings for itype in f.cognitive_profile}
    )
    chapters = [f.chapter for f in findings if f.cognitive_profile]

    if not chapters or not all_types:
        # Nothing to plot — write a minimal 1×1 blank PNG to satisfy existence check
        with plt.rc_context(rc_params):
            fig, ax = plt.subplots(figsize=(4, 2))
            ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center", transform=ax.transAxes)
            ax.set_visible(True)
            _save_png(fig, path)
        return

    n_chapters = len(chapters)
    n_types = len(all_types)
    x = np.arange(n_chapters)
    bar_width = 0.8 / max(n_types, 1)

    with plt.rc_context(rc_params):
        fig, ax = plt.subplots(figsize=(max(6, n_chapters * 1.5), 4))

        for i, itype in enumerate(all_types):
            rates = [
                f.cognitive_profile.get(itype, 0.0)
                for f in findings
                if f.cognitive_profile
            ]
            offset = (i - n_types / 2 + 0.5) * bar_width
            ax.bar(x + offset, rates, bar_width * 0.9, label=itype)

        ax.set_xticks(x)
        ax.set_xticklabels(chapters, rotation=30, ha="right", fontsize=8)
        ax.set_ylim(0, 1.0)
        ax.set_ylabel("정답률")
        ax.set_title("인지수준별 정답률 — 단원 비교")
        ax.legend(loc="upper right", fontsize=8)
        ax.axhline(0.6, color="red", linestyle="--", linewidth=0.8, label="기준선(0.6)")
        fig.tight_layout()
        _save_png(fig, path)


def render_alignment_map(
    findings: list[AlignmentFinding],
    path: Path,
) -> None:
    """Render a horizontal bar chart of learned_rate per chapter, coloured by flag.

    Chapters sorted alphabetically (deterministic).

    Args:
        findings: List of AlignmentFinding.
        path: Destination PNG path.
    """
    _ensure_parent(path)
    font_family = _try_register_korean_font()
    rc_params: dict = {}
    if font_family:
        rc_params["font.family"] = font_family

    sorted_findings = sorted(findings, key=lambda f: f.chapter)
    chapters = [f.chapter for f in sorted_findings]
    rates = [f.learned_rate for f in sorted_findings]
    colours = [_FLAG_COLOURS.get(f.flag, _DEFAULT_FLAG_COLOUR) for f in sorted_findings]

    if not chapters:
        with plt.rc_context(rc_params):
            fig, ax = plt.subplots(figsize=(4, 2))
            ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center", transform=ax.transAxes)
            _save_png(fig, path)
        return

    n = len(chapters)
    with plt.rc_context(rc_params):
        fig, ax = plt.subplots(figsize=(6, max(2, n * 0.5 + 1)))

        import numpy as np

        y_pos = np.arange(n)
        ax.barh(y_pos, rates, color=colours, height=0.6)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(chapters, fontsize=8)
        ax.set_xlim(0, 1.0)
        ax.set_xlabel("코호트 평균 정답률")
        ax.set_title("단원별 정렬 현황")
        ax.axvline(0.6, color="red", linestyle="--", linewidth=0.8)

        # Legend for flags present
        flags_present = sorted({f.flag for f in sorted_findings})
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor=_FLAG_COLOURS.get(flag, _DEFAULT_FLAG_COLOUR), label=flag)
            for flag in flags_present
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=7)

        fig.tight_layout()
        _save_png(fig, path)


def render_all_figures(
    findings: list[AlignmentFinding],
    figs_dir: Path,
) -> list[Path]:
    """Render all alignment figures and return list of paths written.

    Args:
        findings: List of AlignmentFinding from build_alignment.
        figs_dir: Directory to write PNGs into (created if absent).

    Returns:
        List of Path objects for the written PNG files, in deterministic order.
    """
    figs_dir.mkdir(parents=True, exist_ok=True)

    cliff_path = figs_dir / "fig_align_cliff.png"
    map_path = figs_dir / "fig_align_map.png"

    render_cliff_bar(findings, cliff_path)
    render_alignment_map(findings, map_path)

    return [cliff_path, map_path]


__all__ = [
    "render_cliff_bar",
    "render_alignment_map",
    "render_all_figures",
]
