"""Unit tests for radar PNG generation (T091, FR-020 (b))."""

from __future__ import annotations

import hashlib


def test_radar_returns_bytes() -> None:
    from needs_map.cards.radar import render_radar_png

    student_z = {
        "motivation": 1.0,
        "anxiety": -0.5,
        "self_efficacy": 0.3,
        "interest": 0.8,
        "prior_knowledge": -0.2,
        "life_context": 0.0,
    }
    group_means = dict.fromkeys(student_z, 0.0)
    png = render_radar_png(
        student_z, group_means, axes_present=list(student_z.keys())
    )
    assert isinstance(png, bytes)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")  # PNG signature


def test_radar_deterministic_across_two_renders() -> None:
    """Same input → identical PNG bytes (FR-022)."""
    from needs_map.cards.radar import render_radar_png

    student_z = dict.fromkeys(("motivation", "anxiety", "self_efficacy", "interest", "prior_knowledge", "life_context"), 0.5)
    group_means = dict.fromkeys(student_z, 0.0)
    a = render_radar_png(student_z, group_means, axes_present=list(student_z.keys()))
    b = render_radar_png(student_z, group_means, axes_present=list(student_z.keys()))
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_radar_skipped_axis_does_not_break() -> None:
    """axes NOT in axes_present render as '—' placeholder (H-12 mitigation)."""
    from needs_map.cards.radar import render_radar_png

    student_z = {"motivation": 1.0, "anxiety": -0.5}
    group_means = {"motivation": 0.0, "anxiety": 0.0}
    png = render_radar_png(
        student_z, group_means, axes_present=["motivation", "anxiety"]
    )
    assert isinstance(png, bytes)
    assert len(png) > 100
