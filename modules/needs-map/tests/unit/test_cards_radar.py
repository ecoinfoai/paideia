"""Unit tests for 8-axis radar PNG generation [T067-extension; T091 baseline].

Migrated from 6-axis v0.1.0 vocabulary (motivation/anxiety/self_efficacy/
interest/prior_knowledge/life_context) to v0.1.1 8-axis vocabulary
(digital_efficacy/motivation/time_availability/material_preference/
study_strategy/study_environment/social_learning/feedback_seeking) and
the new keyword-only signature (`student_id_short` + `cohort_n`) per
spec 003-needs-map-v0-1-1 T041-T043.
"""

from __future__ import annotations

import hashlib

_AXES_8 = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def test_radar_returns_bytes() -> None:
    from needs_map.cards.radar import render_radar_png

    student_raw = dict.fromkeys(_AXES_8, 4.0)
    student_raw["motivation"] = 5.5
    student_raw["study_strategy"] = 3.2
    cohort_raw = dict.fromkeys(_AXES_8, 4.0)
    png = render_radar_png(
        student_raw,
        cohort_raw,
        student_id_short="2026****01",
        cohort_n=8,
    )
    assert isinstance(png, bytes)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")  # PNG signature


def test_radar_deterministic_across_two_renders() -> None:
    """Same input → identical PNG bytes (FR-022 / FR-035)."""
    from needs_map.cards.radar import render_radar_png

    student_raw = dict.fromkeys(_AXES_8, 4.5)
    cohort_raw = dict.fromkeys(_AXES_8, 4.0)
    a = render_radar_png(
        student_raw,
        cohort_raw,
        student_id_short="2026****01",
        cohort_n=8,
    )
    b = render_radar_png(
        student_raw,
        cohort_raw,
        student_id_short="2026****01",
        cohort_n=8,
    )
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_radar_skipped_axis_does_not_break() -> None:
    """``None``-valued axes render as gaps on the polygon (NaN passthrough)."""
    from needs_map.cards.radar import render_radar_png

    # Two axes have data; the other six are missing — radar still renders.
    student_raw: dict[str, float | None] = dict.fromkeys(_AXES_8, None)
    student_raw["motivation"] = 5.0
    student_raw["study_strategy"] = 3.5
    cohort_raw: dict[str, float | None] = dict.fromkeys(_AXES_8, 4.0)
    png = render_radar_png(
        student_raw,
        cohort_raw,
        student_id_short="2026****01",
        cohort_n=8,
    )
    assert isinstance(png, bytes)
    assert len(png) > 100
