"""Unit tests for Gold student-PII export owner-only permissions (T009+T017).

``factor_scores_long.{csv,yaml}`` contain per-student re-identifiable data
(student_id, 8-axis raw/z scores, cluster, freetext categories/sentiment).
Both artifacts must land with mode 0o600 regardless of the process umask
(security hardening 016).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def _make_long_row(student_id: str) -> dict[str, Any]:
    """Build a minimal valid FactorScoresLongRow payload."""
    payload: dict[str, Any] = {
        "student_id": student_id,
        "semester": "2026-1",
        "course_slug": "anatomy",
        "on_roster": True,
        "section": "A",
        "responded": True,
    }
    for axis in _AXES:
        payload[f"{axis}_raw"] = 4.5
        payload[f"{axis}_z"] = 0.1
        payload[f"{axis}_missing"] = False
    payload.update(
        {
            "prior_readiness_q5": "중간",
            "prior_readiness_q6": None,
            "time_pattern_q21": "오전",
            "time_pattern_q22": "도서관",
            "time_pattern_q23": None,
            "interest_topics_q9": "신경계",
            "interest_topics_q10": None,
            "interest_topics_q11": None,
            "categorical_intent_q12": "의대",
            "categorical_intent_q13": None,
            "cluster_id": 1,
            "cluster_label": "탐색형",
            "cluster_distance": 0.234,
            "freetext_q61_categories": "걱정",
            "freetext_q61_negativity": 0.62,
            "freetext_q61_top_emotion": "불안",
            "freetext_q62_categories": None,
            "freetext_q62_negativity": None,
            "freetext_q62_top_emotion": None,
        }
    )
    return payload


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses chmod 0o600 protection")
def test_factor_scores_long_csv_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """factor_scores_long.csv must be owner-only (0o600) — no group/other bits."""
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [FactorScoresLongRow(**_make_long_row("2026194001"))]
    csv_path, _ = write_factor_scores_long(rows, tmp_path)
    assert_owner_only(csv_path)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses chmod 0o600 protection")
def test_factor_scores_long_yaml_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """factor_scores_long.yaml must be owner-only (0o600) — no group/other bits."""
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [FactorScoresLongRow(**_make_long_row("2026194001"))]
    _, yaml_path = write_factor_scores_long(rows, tmp_path)
    assert_owner_only(yaml_path)
