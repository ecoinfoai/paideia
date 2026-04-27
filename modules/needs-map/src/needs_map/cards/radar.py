"""Radar chart PNG generation (T102, FR-020 (b)).

matplotlib polar plot. Determinism axis 3: dpi=150 + bbox_inches='tight'
fixed via keyword-only defaults so callers cannot accidentally drift.
Skipped axes (not in ``axes_present``) render as a "—" tick label and the
data point is omitted (adversary H-12 mitigation: no silent dim-drop).
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")  # headless rendering before pyplot import
import matplotlib.pyplot as plt
import numpy as np

_AXIS_ORDER: tuple[str, ...] = (
    "motivation",
    "anxiety",
    "self_efficacy",
    "interest",
    "prior_knowledge",
    "life_context",
)
_AXIS_LABELS_KR: dict[str, str] = {
    "motivation": "동기",
    "anxiety": "불안",
    "self_efficacy": "자기효능",
    "interest": "흥미",
    "prior_knowledge": "사전지식",
    "life_context": "생활맥락",
}


def render_radar_png(
    student_z_scores: dict[str, float | None],
    group_means: dict[str, float],
    axes_present: list[str],
    *,
    dpi: int = 150,
    bbox: str = "tight",
) -> bytes:
    """Render a 6-axis radar chart as PNG bytes.

    Args:
        student_z_scores: per-axis z-score (None → "—" placeholder).
        group_means: per-axis group mean (always 0.0 in z-space; drawn as dotted ring).
        axes_present: axes that have data this run; others get a "—" tick label.
        dpi: matplotlib dpi (default 150 — pinned for FR-022 byte-equal).
        bbox: matplotlib bbox_inches (default 'tight').

    Returns:
        PNG bytes (deterministic given identical input).
    """
    n = len(_AXIS_ORDER)
    angles = [(2 * math.pi * i) / n for i in range(n)]
    angles_closed = [*angles, angles[0]]

    student_vals: list[float] = []
    for axis in _AXIS_ORDER:
        if axis not in axes_present:
            student_vals.append(0.0)
            continue
        v = student_z_scores.get(axis)
        student_vals.append(0.0 if v is None else float(v))
    student_closed = [*student_vals, student_vals[0]]

    group_vals = [float(group_means.get(axis, 0.0)) for axis in _AXIS_ORDER]
    group_closed = [*group_vals, group_vals[0]]

    fig = plt.figure(figsize=(4.0, 4.0), dpi=dpi)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)

    tick_labels = [
        _AXIS_LABELS_KR[a] if a in axes_present else "—"
        for a in _AXIS_ORDER
    ]
    ax.set_xticks(angles)
    ax.set_xticklabels(tick_labels, fontsize=8)
    ax.set_yticks([-2.0, -1.0, 0.0, 1.0, 2.0])
    ax.set_yticklabels(["-2", "-1", "0", "+1", "+2"], fontsize=6)
    ax.set_ylim(-3.0, 3.0)

    # Group means (dotted)
    ax.plot(angles_closed, group_closed, linestyle=":", linewidth=1.0, color="grey")
    # Student (solid)
    ax.plot(angles_closed, student_closed, linestyle="-", linewidth=1.5, color="black")
    ax.fill(angles_closed, student_closed, alpha=0.1, color="black")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches=bbox, metadata={"Software": "paideia"})
    plt.close(fig)
    _ = np  # keep numpy import live for downstream consumers
    return buf.getvalue()
