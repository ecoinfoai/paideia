"""Integration tests for the v0.1.1 long-form CSV/YAML exports [T035].

Per spec FR-014/FR-015 + contracts/exports.md, the Phase E exporter must
produce four operator-facing files in the gold directory:

- ``factor_scores_long.csv`` — UTF-8 with BOM, LF line endings, sorted
  by ``student_id`` ascending, one row per cohort responder.
- ``factor_scores_long.yaml`` — UTF-8 (no BOM), ``students:`` top-level
  list of dicts, same data as the CSV.
- ``axis_summary.csv`` — discriminator-driven (row_kind ∈ {quantitative,
  auxiliary_distribution, freetext_summary}), unrelated columns blank,
  fixed column order.
- ``axis_summary.yaml`` — same data, re-folded by row_kind into separate
  sub-trees (quantitative_axes / auxiliary_distributions /
  freetext_summaries).

Determinism (FR-035): two consecutive writes against the same input MUST
produce byte-identical files.

These tests build the inputs in-process (no parquet reads) so the exporter
unit can be exercised independently of the Phase A-D pipeline.

Spec: 003-needs-map-v0-1-1/tasks.md T035; contracts/exports.md.
"""

from __future__ import annotations

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


def _make_long_row(student_id: str, *, missing_axis: str | None = None) -> dict[str, Any]:
    """Build one ``FactorScoresLongRow``-shaped payload for the writer."""
    payload: dict[str, Any] = {
        "student_id": student_id,
        "semester": "2026-1",
        "course_slug": "anatomy",
        "on_roster": True,
        "section": "A",
        "responded": True,
    }
    for axis in _AXES:
        if axis == missing_axis:
            payload[f"{axis}_raw"] = None
            payload[f"{axis}_z"] = None
            payload[f"{axis}_missing"] = True
        else:
            payload[f"{axis}_raw"] = 4.5
            payload[f"{axis}_z"] = 0.1
            payload[f"{axis}_missing"] = False
    payload.update(
        {
            "prior_readiness_q5": "중간",
            "prior_readiness_q6": None,
            "time_pattern_q21": "오전",
            "time_pattern_q22": "도서관;카페",
            "time_pattern_q23": None,
            "interest_topics_q9": "신경계;근육계",
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


def _make_axis_summary_quant_row(axis_key: str) -> dict[str, Any]:
    return {
        "row_kind": "quantitative",
        "axis_key": axis_key,
        "n": 192,
        "n_items": 5,
        "mean_raw": 4.2,
        "std_raw": 0.85,
        "p25": 3.6,
        "p50": 4.2,
        "p75": 4.8,
        "cronbach_alpha": 0.83,
        "reliability_label": "high",
    }


def _make_axis_summary_aux_row(
    axis_key: str, source_col: str, option: str, count: int
) -> dict[str, Any]:
    return {
        "row_kind": "auxiliary_distribution",
        "axis_key": axis_key,
        "source_col": source_col,
        "option": option,
        "count": count,
        "percentage": (count / 180) * 100,
        "n_responded": 180,
        "n_cohort": 194,
    }


def _make_axis_summary_freetext_row(axis_key: str) -> dict[str, Any]:
    return {
        "row_kind": "freetext_summary",
        "axis_key": axis_key,
        "n_responses": 162,
        "n_categorized": 158,
        "dictionary_match_rate": 0.9753,
        "mean_negativity": 0.4421,
        "top_emotion_distribution": {"걱정/불안": 47, "기대/설렘": 33},
    }


# ---------------------------------------------------------------------------
# factor_scores_long.{csv,yaml}
# ---------------------------------------------------------------------------


def test_factor_scores_long_csv_has_utf8_bom_and_lf(tmp_path: Path) -> None:
    """CSV MUST start with the UTF-8 BOM (0xEF 0xBB 0xBF) and use LF newlines."""
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [
        FactorScoresLongRow(**_make_long_row("2026194001")),
        FactorScoresLongRow(**_make_long_row("2026194000")),
    ]
    csv_path, _yaml_path = write_factor_scores_long(rows, tmp_path)
    raw = csv_path.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", f"missing UTF-8 BOM, got bytes {raw[:3]!r}"
    assert b"\r\n" not in raw, "expected LF-only newlines, found CRLF"


def test_factor_scores_long_csv_sorted_by_student_id(tmp_path: Path) -> None:
    """CSV body rows MUST be sorted by ``student_id`` ascending."""
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [
        FactorScoresLongRow(**_make_long_row("2026194042")),
        FactorScoresLongRow(**_make_long_row("2026194001")),
        FactorScoresLongRow(**_make_long_row("2026194100")),
    ]
    csv_path, _ = write_factor_scores_long(rows, tmp_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    lines = [line for line in text.splitlines() if line]
    # First non-header line starts with the lowest student_id.
    body_first_field = [line.split(",")[0] for line in lines[1:]]
    assert (
        body_first_field
        == sorted(body_first_field)
        == [
            "2026194001",
            "2026194042",
            "2026194100",
        ]
    )


def test_factor_scores_long_yaml_round_trip(tmp_path: Path) -> None:
    """YAML round-trips via yaml.safe_load with the same student count."""
    import yaml
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [
        FactorScoresLongRow(**_make_long_row(sid))
        for sid in ("2026194000", "2026194001", "2026194002")
    ]
    _, yaml_path = write_factor_scores_long(rows, tmp_path)
    loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert "students" in loaded
    assert len(loaded["students"]) == 3
    assert {s["student_id"] for s in loaded["students"]} == {
        "2026194000",
        "2026194001",
        "2026194002",
    }


def test_factor_scores_long_byte_identical_two_writes(tmp_path: Path) -> None:
    """Two writes against the same input MUST produce byte-equal CSV + YAML (FR-035)."""
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [FactorScoresLongRow(**_make_long_row(sid)) for sid in ("2026194000", "2026194001")]

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    csv_a, yaml_a = write_factor_scores_long(rows, out_a)
    csv_b, yaml_b = write_factor_scores_long(rows, out_b)
    assert csv_a.read_bytes() == csv_b.read_bytes()
    assert yaml_a.read_bytes() == yaml_b.read_bytes()


def test_factor_scores_long_missing_axis_renders_empty_cell(tmp_path: Path) -> None:
    """Missing axis (raw=None) MUST render as an empty CSV cell, not 'None'."""
    from needs_map.report.exports import write_factor_scores_long
    from paideia_shared.schemas import FactorScoresLongRow

    rows = [FactorScoresLongRow(**_make_long_row("2026194001", missing_axis="motivation"))]
    csv_path, _ = write_factor_scores_long(rows, tmp_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    # The motivation_raw cell must be empty, not "None"; pandas to_csv with
    # default na_rep='' satisfies this.
    assert "None" not in text
    assert "nan" not in text.lower()


# ---------------------------------------------------------------------------
# axis_summary.{csv,yaml}
# ---------------------------------------------------------------------------


def test_axis_summary_csv_contains_three_row_kinds(tmp_path: Path) -> None:
    """axis_summary.csv MUST carry the 3 discriminator values (quantitative,
    auxiliary_distribution, freetext_summary)."""
    from needs_map.report.exports import write_axis_summary
    from paideia_shared.schemas import AxisSummaryRow

    rows = [AxisSummaryRow(**_make_axis_summary_quant_row(axis)) for axis in _AXES]
    rows.extend(
        [
            AxisSummaryRow(**_make_axis_summary_aux_row("prior_readiness", "q5", "중간", 87)),
            AxisSummaryRow(**_make_axis_summary_aux_row("prior_readiness", "q5", "낮음", 30)),
        ]
    )
    rows.extend(
        AxisSummaryRow(**_make_axis_summary_freetext_row(area))
        for area in ("anxiety_freetext", "experience_freetext")
    )
    csv_path, _ = write_axis_summary(rows, tmp_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "quantitative" in text
    assert "auxiliary_distribution" in text
    assert "freetext_summary" in text


def test_axis_summary_aux_row_carries_response_rate_base(tmp_path: Path) -> None:
    """Every auxiliary_distribution row MUST expose n_responded + n_cohort."""
    from needs_map.report.exports import write_axis_summary
    from paideia_shared.schemas import AxisSummaryRow

    rows = [
        AxisSummaryRow(**_make_axis_summary_quant_row("motivation")),
        AxisSummaryRow(**_make_axis_summary_aux_row("interest_topics", "q9", "신경계", 64)),
    ]
    csv_path, _ = write_axis_summary(rows, tmp_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0]
    assert "n_responded" in header
    assert "n_cohort" in header
    # Find the auxiliary line and verify both columns are populated.
    # pandas.to_csv promotes int columns mixed with NaN to float, so "180"
    # may render as "180.0"; accept both representations.
    for line in text.splitlines()[1:]:
        if "auxiliary_distribution" in line:
            cells = line.split(",")
            assert "180" in cells or "180.0" in cells, f"expected n_responded=180 in row: {cells}"
            assert "194" in cells or "194.0" in cells, f"expected n_cohort=194 in row: {cells}"


def test_axis_summary_yaml_groups_by_row_kind(tmp_path: Path) -> None:
    """YAML MUST re-fold rows under quantitative_axes / auxiliary_distributions /
    freetext_summaries top-level keys."""
    import yaml
    from needs_map.report.exports import write_axis_summary
    from paideia_shared.schemas import AxisSummaryRow

    rows = [
        AxisSummaryRow(**_make_axis_summary_quant_row("motivation")),
        AxisSummaryRow(**_make_axis_summary_aux_row("prior_readiness", "q5", "중간", 87)),
        AxisSummaryRow(**_make_axis_summary_freetext_row("anxiety_freetext")),
    ]
    _, yaml_path = write_axis_summary(rows, tmp_path)
    loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert "quantitative_axes" in loaded
    assert "auxiliary_distributions" in loaded
    assert "freetext_summaries" in loaded
    assert any(item["axis_key"] == "motivation" for item in loaded["quantitative_axes"])


def test_axis_summary_byte_identical_two_writes(tmp_path: Path) -> None:
    """axis_summary.{csv,yaml} MUST be byte-equal across two writes (FR-035)."""
    from needs_map.report.exports import write_axis_summary
    from paideia_shared.schemas import AxisSummaryRow

    rows = [AxisSummaryRow(**_make_axis_summary_quant_row(axis)) for axis in _AXES[:2]]
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    csv_a, yaml_a = write_axis_summary(rows, out_a)
    csv_b, yaml_b = write_axis_summary(rows, out_b)
    assert csv_a.read_bytes() == csv_b.read_bytes()
    assert yaml_a.read_bytes() == yaml_b.read_bytes()


# ---------------------------------------------------------------------------
# build_axis_summary_rows aggregation helper (T037)
# ---------------------------------------------------------------------------


def test_build_axis_summary_rows_constructs_three_kinds() -> None:
    """``build_axis_summary_rows`` returns rows of all 3 kinds when given full inputs."""
    from needs_map.report.aggregation import build_axis_summary_rows

    rows = build_axis_summary_rows(
        scale_reliability=[
            {
                "axis_key": "motivation",
                "n_items": 8,
                "cronbach_alpha": 0.85,
                "label": "computed",
                "operational_warning": False,
                "reliability_label": "high",
            }
        ],
        factor_scores_long=[
            _make_long_row("2026194001"),
            _make_long_row("2026194002"),
        ],
        auxiliary_columns={
            "prior_readiness": {
                "q5": {"중간": 1, "낮음": 1},
            }
        },
        freetext_summaries={
            "anxiety_freetext": {
                "n_responses": 2,
                "n_categorized": 1,
                "dictionary_match_rate": 0.5,
                "mean_negativity": 0.4,
                "top_emotion_distribution": {"걱정/불안": 1},
            }
        },
        n_cohort=2,
    )
    kinds = {r.row_kind for r in rows}
    assert kinds == {"quantitative", "auxiliary_distribution", "freetext_summary"}


def test_build_axis_summary_rows_aux_uses_response_rate_base() -> None:
    """Aux rows: percentage = count / n_responded × 100, NOT count / n_cohort × 100 (FR-010)."""
    from needs_map.report.aggregation import build_axis_summary_rows

    rows = build_axis_summary_rows(
        scale_reliability=[],
        factor_scores_long=[
            _make_long_row("2026194001"),
            _make_long_row("2026194002"),
            _make_long_row("2026194003"),
        ],
        auxiliary_columns={
            "prior_readiness": {
                "q5": {"중간": 1, "낮음": 1},
                # 2 responders out of 3 cohort members
            }
        },
        freetext_summaries={},
        n_cohort=3,
    )
    aux_rows = [r for r in rows if r.row_kind == "auxiliary_distribution"]
    assert len(aux_rows) == 2
    for r in aux_rows:
        assert r.n_responded == 2
        assert r.n_cohort == 3
        assert pytest.approx(r.percentage, abs=0.01) == 50.0
