"""T025 — Silver writer tests (RED phase).

Tests for ``retro_mester.output.silver.write_silver``.
- Writes both parquet files.
- Row counts round-trip.
- Dict/list columns are JSON-encoded strings in the parquet payload.
- Two writes of identical data produce byte-identical files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from paideia_shared.schemas import InsufficientEvidenceUnit
from paideia_shared.schemas.change_recommendation import ChangeRecommendation
from paideia_shared.schemas.unit_gap import UnitGap
from retro_mester.output.silver import write_silver


def _make_insufficient() -> list[InsufficientEvidenceUnit]:
    """Return two InsufficientEvidenceUnit instances (out of sort order)."""
    return [
        InsufficientEvidenceUnit(
            semester="2026-1",
            course_slug="anatomy",
            chapter="9장 신경",
            segment="만학도",
            evidence_n=0,
            reason="근거부족-자료없음",
        ),
        InsufficientEvidenceUnit(
            semester="2026-1",
            course_slug="anatomy",
            chapter="9장 신경",
            segment="학령기",
            evidence_n=0,
            reason="근거부족-자료없음",
        ),
    ]

# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------


def _make_unit_gaps() -> list[UnitGap]:
    """Return two minimal UnitGap instances."""
    common = dict(
        semester="2026-1",
        course_slug="anatomy",
        segment_mean_rate=0.60,
        n_below=5,
        pct_segment=0.25,
        pct_cohort=0.10,
        is_structural=True,
        cohort_failing_item_types=["지식", "이해"],
        cause="내용난이도",
        cause_signals={"mean_diff": -0.15, "pass_rate": 0.60},
        validity="건전",
        unit_importance="상",
        weight=3.0,
        evidence_n=20,
    )
    return [
        UnitGap(**common, chapter="1장 세포", segment="학령기", impact_score=5.0 * 3.0),
        UnitGap(**common, chapter="2장 조직", segment="만학도", impact_score=5.0 * 3.0),
    ]


def _make_recs() -> list[ChangeRecommendation]:
    """Return two ChangeRecommendation instances (one covered, one not)."""
    base = dict(
        semester="2026-1",
        course_slug="anatomy",
        target_cognitive_level="이해",
        cause_hypothesis="내용난이도",
        covered_n=5,
        covered_pct_segment=0.25,
        covered_pct_cohort=0.10,
        unit_importance="상",
        weight=3.0,
        effort_level="중",
        priority_quadrant="빠른승리",
        prescription_key="scaffold_concepts",
        cluster_vocab=None,
        validity="건전",
        impact_score=5.0 * 3.0,
    )
    return [
        ChangeRecommendation(
            **base,
            rank=1,
            chapter="1장 세포",
            segment="학령기",
            is_covered=True,
        ),
        ChangeRecommendation(
            **base,
            rank=None,
            chapter="2장 조직",
            segment="만학도",
            is_covered=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteSilver:
    def test_both_files_created(self, tmp_path: Path) -> None:
        """write_silver creates 빈틈표.parquet and 변경권고.parquet."""
        write_silver(_make_unit_gaps(), _make_recs(), [], tmp_path)
        assert (tmp_path / "빈틈표.parquet").exists()
        assert (tmp_path / "변경권고.parquet").exists()

    def test_gap_row_count(self, tmp_path: Path) -> None:
        """빈틈표.parquet round-trips the correct row count."""
        gaps = _make_unit_gaps()
        write_silver(gaps, _make_recs(), [], tmp_path)
        df = pd.read_parquet(tmp_path / "빈틈표.parquet")
        assert len(df) == len(gaps)

    def test_rec_row_count(self, tmp_path: Path) -> None:
        """변경권고.parquet round-trips the correct row count."""
        recs = _make_recs()
        write_silver(_make_unit_gaps(), recs, [], tmp_path)
        df = pd.read_parquet(tmp_path / "변경권고.parquet")
        assert len(df) == len(recs)

    def test_cause_signals_json_encoded(self, tmp_path: Path) -> None:
        """cause_signals column (dict) is stored as a JSON string."""
        write_silver(_make_unit_gaps(), _make_recs(), [], tmp_path)
        df = pd.read_parquet(tmp_path / "빈틈표.parquet")
        raw = df["cause_signals"].iloc[0]
        # Must be a string parseable as JSON dict
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_cohort_failing_item_types_json_encoded(self, tmp_path: Path) -> None:
        """cohort_failing_item_types column (list) is stored as a JSON string."""
        write_silver(_make_unit_gaps(), _make_recs(), [], tmp_path)
        df = pd.read_parquet(tmp_path / "빈틈표.parquet")
        raw = df["cohort_failing_item_types"].iloc[0]
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_byte_identical_on_two_writes(self, tmp_path: Path) -> None:
        """Two consecutive writes of the same data yield byte-identical files."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        gaps = _make_unit_gaps()
        recs = _make_recs()
        write_silver(gaps, recs, [], dir_a)
        write_silver(gaps, recs, [], dir_b)

        for name in ("빈틈표.parquet", "변경권고.parquet"):
            bytes_a = (dir_a / name).read_bytes()
            bytes_b = (dir_b / name).read_bytes()
            assert bytes_a == bytes_b, f"{name}: byte-identical assertion failed"

    def test_stable_sort_order(self, tmp_path: Path) -> None:
        """Rows are sorted by chapter then segment so output is deterministic."""
        # Provide gaps out of order
        common = dict(
            semester="2026-1",
            course_slug="anatomy",
            segment_mean_rate=0.60,
            n_below=5,
            pct_segment=0.25,
            pct_cohort=0.10,
            is_structural=True,
            cohort_failing_item_types=[],
            cause="미상",
            cause_signals={},
            validity="건전",
            unit_importance="하",
            weight=1.0,
            evidence_n=20,
            impact_score=5.0,
        )
        gaps = [
            UnitGap(**common, chapter="2장 조직", segment="학령기"),
            UnitGap(**common, chapter="1장 세포", segment="만학도"),
        ]
        write_silver(gaps, [], [], tmp_path)
        df = pd.read_parquet(tmp_path / "빈틈표.parquet")
        assert df["chapter"].tolist() == ["1장 세포", "2장 조직"]


class TestWriteSilverInsufficient:
    """T010: 근거부족단원.parquet — insufficient units must not vanish."""

    def test_insufficient_parquet_created(self, tmp_path: Path) -> None:
        """write_silver writes 근거부족단원.parquet."""
        write_silver(_make_unit_gaps(), _make_recs(), _make_insufficient(), tmp_path)
        assert (tmp_path / "근거부족단원.parquet").exists()

    def test_insufficient_rows_present(self, tmp_path: Path) -> None:
        """근거부족단원.parquet carries one row per insufficient unit."""
        insuf = _make_insufficient()
        write_silver(_make_unit_gaps(), _make_recs(), insuf, tmp_path)
        df = pd.read_parquet(tmp_path / "근거부족단원.parquet")
        assert len(df) == len(insuf)
        assert set(df["reason"]) == {"근거부족-자료없음"}

    def test_insufficient_stable_sort(self, tmp_path: Path) -> None:
        """Rows sorted by (chapter, segment) for determinism."""
        write_silver(_make_unit_gaps(), _make_recs(), _make_insufficient(), tmp_path)
        df = pd.read_parquet(tmp_path / "근거부족단원.parquet")
        assert df["segment"].tolist() == ["만학도", "학령기"]

    def test_empty_insufficient_schema_consistent(self, tmp_path: Path) -> None:
        """Empty insufficient list → empty-but-schema-consistent parquet."""
        write_silver(_make_unit_gaps(), _make_recs(), [], tmp_path)
        df = pd.read_parquet(tmp_path / "근거부족단원.parquet")
        assert len(df) == 0
        assert set(InsufficientEvidenceUnit.model_fields.keys()).issubset(set(df.columns))

    def test_byte_identical(self, tmp_path: Path) -> None:
        """Two writes of the same insufficient list are byte-identical."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        insuf = _make_insufficient()
        write_silver(_make_unit_gaps(), _make_recs(), insuf, dir_a)
        write_silver(_make_unit_gaps(), _make_recs(), insuf, dir_b)
        assert (dir_a / "근거부족단원.parquet").read_bytes() == (
            dir_b / "근거부족단원.parquet"
        ).read_bytes()
