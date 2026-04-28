"""8-axis polar radar with cohort overlay [T041, FR-020 + FR-021 + FR-022].

matplotlib polar plot. v0.1.1 deltas:

- 8 angular positions (one per quantitative axis) via
  ``np.linspace(0, 2π, 9)[:-1]``. Tick labels are the 8 Korean axis
  names (도구 적응성 / 학습동기 / 학습시간 / 학습자료 / 학습전략 /
  학습환경 / 협업 / 피드백) — single source of truth via
  ``pipeline._AXIS_LABELS_KR``.
- Y-axis ticks render the *raw* 1–7 likert scale (no z-score
  centering). ylim is (0, 7) so the 1-7 ring is comfortably inside.
- Student polygon: solid black + alpha-fill on the raw values; a missing
  axis (None) is passed through as ``np.nan`` and matplotlib leaves a
  visible gap (FR-021 — no cohort substitution).
- Cohort polygon: dashed grey on ``cohort_means_raw`` (independent of
  student missing flags). Drawn before the student polygon so the
  student line lands on top.
- Legend: masked student id (e.g. ``2026****01``) + cohort n
  (``"전체 평균 n=194"``).

Determinism axis 3: dpi=150 + bbox_inches='tight' fixed via keyword-only
defaults so callers cannot accidentally drift (FR-035 byte-equal).
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")  # headless rendering before pyplot import
import matplotlib.pyplot as plt
import numpy as np

_AXIS_ORDER: tuple[str, ...] = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)
_AXIS_LABELS_KR: dict[str, str] = {
    "digital_efficacy": "도구 적응성",
    "motivation": "학습동기",
    "time_availability": "학습시간",
    "material_preference": "학습자료",
    "study_strategy": "학습전략",
    "study_environment": "학습환경",
    "social_learning": "협업",
    "feedback_seeking": "피드백",
}

_LIKERT_TICKS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)


def render_radar_png(
    student_raw_scores: dict[str, float | None],
    cohort_means_raw: dict[str, float | None],
    *,
    student_id_short: str,
    cohort_n: int,
    dpi: int = 150,
    bbox: str = "tight",
) -> bytes:
    """Render an 8-axis radar PNG with student polygon + cohort overlay.

    Args:
        student_raw_scores: Per-axis raw 1-7 likert mean. ``None`` value
            renders as a NaN-driven gap (no cohort substitution).
        cohort_means_raw: Per-axis cohort mean (raw 1-7). ``None`` axes
            render as a gap on the dashed cohort polygon.
        student_id_short: Masked student id for the legend (e.g.
            ``"2026****01"``).
        cohort_n: Cohort size, surfaced as ``"전체 평균 n=<cohort_n>"``.
        dpi: matplotlib dpi (default 150 — pinned for FR-035 byte-equal).
        bbox: matplotlib bbox_inches (default 'tight').

    Returns:
        PNG bytes (deterministic given identical input).
    """
    n = len(_AXIS_ORDER)
    # 8 angular positions, evenly spaced. ``linspace(0, 2π, n+1)[:-1]``
    # is the canonical pattern (matches the spec note in tasks.md T041).
    angles = list(np.linspace(0.0, 2.0 * math.pi, n + 1)[:-1])
    angles_closed = [*angles, angles[0]]

    student_vals = [
        np.nan if student_raw_scores.get(a) is None else float(student_raw_scores[a])  # type: ignore[arg-type]
        for a in _AXIS_ORDER
    ]
    cohort_vals = [
        np.nan if cohort_means_raw.get(a) is None else float(cohort_means_raw[a])  # type: ignore[arg-type]
        for a in _AXIS_ORDER
    ]
    student_closed = [*student_vals, student_vals[0]]
    cohort_closed = [*cohort_vals, cohort_vals[0]]

    fig = plt.figure(figsize=(4.0, 4.0), dpi=dpi)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)

    tick_labels = [_AXIS_LABELS_KR[a] for a in _AXIS_ORDER]
    ax.set_xticks(angles)
    ax.set_xticklabels(tick_labels, fontsize=8)
    ax.set_yticks(list(_LIKERT_TICKS))
    ax.set_yticklabels([str(t) for t in _LIKERT_TICKS], fontsize=6)
    ax.set_ylim(0.0, 7.0)

    # Cohort polygon first (solid blue) so student line sits on top.
    cohort_label = f"전체 평균 n={cohort_n}"
    ax.plot(
        angles_closed,
        cohort_closed,
        linestyle="-",
        linewidth=1.2,
        color="#1f77b4",
        label=cohort_label,
    )
    ax.plot(
        angles_closed,
        student_closed,
        linestyle="-",
        linewidth=1.5,
        color="#d62728",
        label=student_id_short,
    )
    ax.fill(angles_closed, student_closed, alpha=0.1, color="#d62728")

    # Place legend OUTSIDE the polar chart (right side) so it never overlaps
    # the polygon/labels — anchor at the right edge of the axes.
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.18, 1.05),
        fontsize=6,
        frameon=False,
    )

    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi, bbox_inches=bbox, metadata={"Software": "paideia"}
    )
    plt.close(fig)
    return buf.getvalue()
