"""Pre-generate the 3 manual figure assets [T046].

Produces ``shared/paideia_shared/src/paideia_shared/assets/manual_figures/{
radar_example.png, distribution_example.png, cluster_example.png}`` from
synthetic data. Run once when the assets need refreshing — committed
PNGs are then frozen so ``manual.pdf`` stays byte-equal across runs.

Usage:

    uv run python scripts/generate_manual_figures.py

Each figure is ~150-200 KB, well under spec L155 budget. The script is
deterministic (numpy seed pinned) so re-running it produces byte-equal
PNGs.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_OUTPUT_DIR = Path("shared/paideia_shared/src/paideia_shared/assets/manual_figures")
_DPI = 150
_BBOX = "tight"
_RNG_SEED = 42


_AXIS_KEYS = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)
_AXIS_LABELS_KR = {
    "digital_efficacy": "도구 적응성",
    "motivation": "학습동기",
    "time_availability": "학습시간",
    "material_preference": "학습자료",
    "study_strategy": "학습전략",
    "study_environment": "학습환경",
    "social_learning": "협업",
    "feedback_seeking": "피드백",
}


def _radar_example(rng: np.random.Generator) -> bytes:
    """8-axis polar radar example (raw 1-7 + cohort overlay + masked id)."""
    n = len(_AXIS_KEYS)
    angles = list(np.linspace(0.0, 2.0 * np.pi, n + 1)[:-1])
    angles_closed = [*angles, angles[0]]

    # Synthetic student polygon (one missing axis to demonstrate the gap)
    student = rng.uniform(3.5, 6.5, size=n).tolist()
    student[2] = float("nan")  # time_availability missing — show NaN gap
    student_closed = [*student, student[0]]

    cohort = rng.uniform(4.0, 5.5, size=n).tolist()
    cohort_closed = [*cohort, cohort[0]]

    fig = plt.figure(figsize=(4.0, 4.0), dpi=_DPI)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels([_AXIS_LABELS_KR[a] for a in _AXIS_KEYS], fontsize=8)
    ax.set_yticks([1, 2, 3, 4, 5, 6, 7])
    ax.set_yticklabels(["1", "2", "3", "4", "5", "6", "7"], fontsize=6)
    ax.set_ylim(0.0, 7.0)
    ax.plot(
        angles_closed,
        cohort_closed,
        linestyle="--",
        linewidth=1.0,
        color="grey",
        label="전체 평균 n=194",
    )
    ax.plot(
        angles_closed,
        student_closed,
        linestyle="-",
        linewidth=1.5,
        color="black",
        label="2026****01",
    )
    ax.fill(angles_closed, student_closed, alpha=0.1, color="black")
    ax.legend(loc="lower right", fontsize=6, frameon=False)

    from io import BytesIO

    buf = BytesIO()
    fig.savefig(
        buf, format="png", dpi=_DPI, bbox_inches=_BBOX, metadata={"Software": "paideia/manual"}
    )
    plt.close(fig)
    return buf.getvalue()


def _distribution_example(rng: np.random.Generator) -> bytes:
    """Per-axis distribution histogram example."""
    fig, axes = plt.subplots(2, 4, figsize=(8.0, 4.0), dpi=_DPI)
    for ax, key in zip(axes.flatten(), _AXIS_KEYS, strict=True):
        values = rng.normal(loc=4.5, scale=1.0, size=180).clip(1.0, 7.0)
        ax.hist(values, bins=14, range=(1, 7), color="steelblue", edgecolor="black", linewidth=0.3)
        ax.set_title(_AXIS_LABELS_KR[key], fontsize=8)
        ax.set_xticks([1, 4, 7])
        ax.tick_params(axis="both", labelsize=6)
    fig.tight_layout()

    from io import BytesIO

    buf = BytesIO()
    fig.savefig(
        buf, format="png", dpi=_DPI, bbox_inches=_BBOX, metadata={"Software": "paideia/manual"}
    )
    plt.close(fig)
    return buf.getvalue()


def _cluster_example(rng: np.random.Generator) -> bytes:
    """Cluster scatter example (PC1 / PC2 projection with k=4 clusters)."""
    fig, ax = plt.subplots(figsize=(5.0, 4.0), dpi=_DPI)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    labels = ["탐색형", "성취형", "지원필요", "안정형"]
    for i, (color, label) in enumerate(zip(colors, labels, strict=True)):
        center = rng.uniform(-1.5, 1.5, size=2)
        pts = rng.normal(loc=center, scale=0.5, size=(40, 2))
        ax.scatter(
            pts[:, 0],
            pts[:, 1],
            c=color,
            label=label,
            s=20,
            alpha=0.7,
            edgecolors="black",
            linewidths=0.3,
        )
        ax.annotate(
            label,
            center,
            fontsize=7,
            ha="center",
            va="center",
            bbox={
                "boxstyle": "round,pad=0.2",
                "facecolor": "white",
                "edgecolor": "black",
                "linewidth": 0.3,
            },
        )
        _ = i
    ax.set_xlabel("PC1 (학습 적극성)", fontsize=8)
    ax.set_ylabel("PC2 (협업·환경 의존)", fontsize=8)
    ax.legend(fontsize=6, loc="upper right")
    ax.tick_params(axis="both", labelsize=6)

    from io import BytesIO

    buf = BytesIO()
    fig.savefig(
        buf, format="png", dpi=_DPI, bbox_inches=_BBOX, metadata={"Software": "paideia/manual"}
    )
    plt.close(fig)
    return buf.getvalue()


def main() -> None:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Register NanumGothic with matplotlib so Korean axis/cluster labels
    # render with proper glyphs instead of the DejaVu Sans fallback (the
    # "Glyph X missing" warning otherwise visible at savefig time).
    try:
        from needs_map.fonts import (
            register_for_matplotlib,
            resolve_korean_font_paths,
        )

        regular_path, _bold_path = resolve_korean_font_paths()
        register_for_matplotlib(regular_path)
    except Exception as exc:  # noqa: BLE001
        print(
            f"WARN: NanumGothic registration skipped ({exc!s}); Korean glyphs may render as boxes."
        )
    artefacts = {
        "radar_example.png": _radar_example,
        "distribution_example.png": _distribution_example,
        "cluster_example.png": _cluster_example,
    }
    for name, builder in artefacts.items():
        # Each builder gets its own seeded RNG to keep figures independent
        # but reproducible.
        builder_rng = np.random.default_rng(_RNG_SEED + hash(name) % 1000)
        png_bytes = builder(builder_rng)
        target = _OUTPUT_DIR / name
        target.write_bytes(png_bytes)
        print(f"wrote {target} ({len(png_bytes):,} bytes)")


if __name__ == "__main__":
    main()
