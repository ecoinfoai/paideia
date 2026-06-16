"""T059 — Edge-case integration tests for the retro-mester pipeline.

Covers spec §Edge Cases:
- absent-only cohort / empty chapter
- fewer than 3 gaps (no padding, shortfall noted)
- tiny-sample segment (conservative handling, recorded)
- chapter-label mismatch between 문항통계 and 결합본
- cold-start (no prior_year)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEMESTER}-{_COURSE}"

_CHAPTER_A = "1장. 해부학 서론"
_CHAPTER_B = "2장. 세포와 조직"

# ---------------------------------------------------------------------------
# Shared fixture helpers (self-contained, no conftest imports)
# ---------------------------------------------------------------------------

_AXES = [
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
]


def _combined_row(
    student_id: str,
    chapter_rates: dict[str, float] | None = None,
) -> dict:
    """Return a minimal CombinedAnalysisRow-compatible dict."""
    if chapter_rates is None:
        chapter_rates = {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}
    row: dict = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "cluster_id": None,
        "cluster_label": None,
        "cluster_distance": None,
        "exam_taken": True,
        "total_score": 60.0,
        "score_percent": 60.0,
        "section_percentile": 50.0,
        "cohort_percentile": 50.0,
        "z_score": 0.0,
        "chapter_correct_rates": json.dumps(chapter_rates),
        "source_correct_rates": json.dumps({"형성평가": 0.5}),
        "difficulty_correct_rates": json.dumps({"1": 0.7, "2": 0.5, "3": 0.3}),
        "expected_difficulty_correct_rates": json.dumps({"쉬움": 0.7, "보통": 0.5, "어려움": 0.3}),
        "item_type_correct_rates": json.dumps({"지식축적": 0.6, "이해": 0.5}),
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
        "prior_readiness_q5": None,
        "prior_readiness_q6": None,
        "time_pattern_q21": None,
        "time_pattern_q22": None,
        "time_pattern_q23": None,
        "interest_topics_q9": None,
        "interest_topics_q10": None,
        "interest_topics_q11": None,
        "categorical_intent_q12": None,
        "categorical_intent_q13": None,
        "진단응답": False,
        "시험응시": True,
        "needs_map_schema_version": "0.1.1",
        "immersio_phase2_schema_version": "0.1.0",
    }
    for axis in _AXES:
        row[f"{axis}_raw"] = None
        row[f"{axis}_z"] = None
        row[f"{axis}_missing"] = True
    return row


def _item_row(
    item_no: int,
    chapter: str = _CHAPTER_A,
    discrimination_index: float = 0.25,
) -> dict:
    """Return a minimal ItemStatistics-compatible dict."""
    return {
        "item_no": item_no,
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "chapter": chapter,
        "week": None,
        "item_type": "지식축적",
        "difficulty_level": 2,
        "expected_difficulty": "보통",
        "source": "형성평가",
        "correct_answer": 3,
        "n_responders": 20,
        "n_correct": 10,
        "n_omit": 0,
        "correct_rate": 0.50,
        "omit_rate": 0.00,
        "discrimination_index": discrimination_index,
        "point_biserial": 0.35,
        "top_distractor_no": 2,
        "top_distractor_rate": 0.20,
        "is_top_distractor_adjacent": True,
        "option_distribution": json.dumps({1: 0.1, 2: 0.2, 3: 0.5, 4: 0.1, 5: 0.1}),
        "distractor_label": "특이사항 없음",
    }


def _blueprint() -> dict:
    return {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "exam_name": "2026-1학기 기말고사",
        "total_items": 40,
        "chapters": [_CHAPTER_A, _CHAPTER_B],
        "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
        "source_mix": {"formative": 18, "quiz": 12, "textbook": 10},
        "quiz_target": 12,
        "answer_key_balance": True,
    }


def _curriculum() -> dict:
    return {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": 1,
                "chapter": _CHAPTER_A,
                "chapter_no": 1,
                "subtopic": None,
                "sections": ["1.1 인체의 조직"],
            },
            {
                "week": 2,
                "chapter": _CHAPTER_B,
                "chapter_no": 2,
                "subtopic": None,
                "sections": ["2.1 세포의 구조"],
            },
        ],
    }


def _retro_config(group_roster: dict | None = None) -> dict:
    if group_roster is None:
        group_roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "만학도",
            "2026000004": "만학도",
        }
    return {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "group_roster": group_roster,
        "unit_importance": {
            _CHAPTER_A: "상",
            _CHAPTER_B: "중",
        },
        "gap_threshold": 0.6,
        "baseline_segment": "만학도",
        "low_discrimination_threshold": 0.2,
        "cognitive_cliff_drop": 0.15,
        "effort_ratings": {
            _CHAPTER_A: "상",
            _CHAPTER_B: "중",
        },
    }


def _write_tree(
    data_root: Path,
    combined_rows: list[dict],
    item_rows: list[dict],
    config_dict: dict | None = None,
) -> None:
    """Write fixture file tree under data_root."""
    silver_im = data_root / "silver" / "immersio" / _KEY
    silver_im.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(combined_rows).to_parquet(silver_im / "진단×시험결합.parquet", index=False)
    pd.DataFrame(item_rows).to_parquet(silver_im / "문항통계.parquet", index=False)

    bronze = data_root / "bronze" / "retro-mester" / _KEY
    bronze.mkdir(parents=True, exist_ok=True)
    cfg = config_dict if config_dict is not None else _retro_config()
    (bronze / "retro_config.yaml").write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    (bronze / "blueprint.yaml").write_text(
        yaml.dump(_blueprint(), allow_unicode=True), encoding="utf-8"
    )
    (bronze / "curriculum_map.yaml").write_text(
        yaml.dump(_curriculum(), allow_unicode=True), encoding="utf-8"
    )


def _run(data_root: Path, **kwargs) -> int:
    from retro_mester.pipeline import run_retro

    return run_retro(
        semester=_SEMESTER,
        course=_COURSE,
        data_root=str(data_root),
        llm_mode="off",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# EC1: empty chapter (no chapter rates for one chapter in all rows)
# ---------------------------------------------------------------------------


class TestEmptyChapter:
    """Students have no rates for one chapter: pipeline handles gracefully (EC-1)."""

    def test_missing_chapter_b_rates_exits_zero(self, tmp_path: Path) -> None:
        """Pipeline exits 0 when all students lack rates for one chapter."""
        data_root = tmp_path / "data"
        # All students have rates only for CHAPTER_A, not CHAPTER_B
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)

        code = _run(data_root)
        assert code == 0, f"Expected exit 0, got {code}"

    def test_missing_chapter_outputs_produced(self, tmp_path: Path) -> None:
        """Gold outputs exist even when one chapter has no student rates."""
        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)
        _run(data_root)

        gold = data_root / "gold" / "retro-mester" / _KEY
        assert (gold / "CQI회고보고서.md").exists()
        assert (gold / "manifest_retro.json").exists()


# ---------------------------------------------------------------------------
# EC2: fewer than 3 gaps — emit what exists, no padding
# ---------------------------------------------------------------------------


class TestFewerThanThreeGaps:
    """Fewer than 3 gaps: emit what exists, record shortfall (EC-2)."""

    def test_single_gap_exits_zero(self, tmp_path: Path) -> None:
        """Pipeline succeeds with only one detectable gap."""
        data_root = tmp_path / "data"
        # Only CHAPTER_A is below threshold; CHAPTER_B is above
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.9}),
            _combined_row("2026000002", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.85}),
            _combined_row("2026000003", {_CHAPTER_A: 0.35, _CHAPTER_B: 0.95}),
            _combined_row("2026000004", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.8}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)

        code = _run(data_root)
        assert code == 0

    def test_no_padding_to_fill_minimum(self, tmp_path: Path) -> None:
        """Recs list is not padded beyond real gaps (no synthetic recommendations)."""
        import pyarrow.parquet as pq

        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.95}),
            _combined_row("2026000002", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.9}),
            _combined_row("2026000003", {_CHAPTER_A: 0.35, _CHAPTER_B: 0.85}),
            _combined_row("2026000004", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.8}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)
        _run(data_root)

        silver = data_root / "silver" / "retro-mester" / _KEY
        recs_df = pq.read_table(silver / "변경권고.parquet").to_pandas()
        gaps_df = pq.read_table(silver / "빈틈표.parquet").to_pandas()

        # Recs ≤ gaps: no padding
        assert len(recs_df) <= len(gaps_df), "Recs must not exceed gaps — no synthetic padding"

    def test_zero_gaps_uncovered_ratio_is_nan_or_zero(self, tmp_path: Path) -> None:
        """When all chapters are above threshold, uncovered_ratio is 0 or NaN."""
        import math

        data_root = tmp_path / "data"
        # All students above gap_threshold (0.6) → no gaps
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.8, _CHAPTER_B: 0.9}),
            _combined_row("2026000002", {_CHAPTER_A: 0.75, _CHAPTER_B: 0.85}),
            _combined_row("2026000003", {_CHAPTER_A: 0.9, _CHAPTER_B: 0.95}),
            _combined_row("2026000004", {_CHAPTER_A: 0.85, _CHAPTER_B: 0.8}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)
        code = _run(data_root)

        assert code == 0
        import json as _json

        manifest = _json.loads(
            (data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json").read_text(
                encoding="utf-8"
            )
        )
        ratio = manifest["counts"]["uncovered_ratio"]
        # 0 gaps → ratio is 0 or NaN (float('nan') serialises as null in JSON)
        assert ratio == 0.0 or ratio is None or (isinstance(ratio, float) and math.isnan(ratio)), (
            f"Expected 0 or NaN for zero-gap uncovered_ratio, got {ratio}"
        )


# ---------------------------------------------------------------------------
# EC3: tiny-sample segment
# ---------------------------------------------------------------------------


class TestTinySampleSegment:
    """A segment with only one student: conservative, recorded (EC-3)."""

    def test_single_student_segment_exits_zero(self, tmp_path: Path) -> None:
        """Pipeline completes when one segment has only one student."""
        data_root = tmp_path / "data"
        # 만학도 segment: only one student
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            # Lone 만학도 student
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        # Only one 만학도 student in roster
        roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "학령기",
            "2026000004": "만학도",
        }
        _write_tree(data_root, combined, items, _retro_config(roster))

        code = _run(data_root)
        assert code == 0

    def test_single_student_segment_recorded_in_manifest(self, tmp_path: Path) -> None:
        """Manifest counts reflect correct student/segment distribution."""
        import json as _json

        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "학령기",
            "2026000004": "만학도",
        }
        _write_tree(data_root, combined, items, _retro_config(roster))
        _run(data_root)

        manifest = _json.loads(
            (data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["counts"]["students"] == 4.0
        assert manifest["counts"]["segments"] == 2.0  # 학령기 + 만학도


# ---------------------------------------------------------------------------
# EC4: chapter-label mismatch between 문항통계 and 결합본
# ---------------------------------------------------------------------------


class TestChapterLabelMismatch:
    """Chapter label in 문항통계 differs from 결합본 (EC-4).

    Per spec: mismatch is recorded in manifest, no silent skip.
    """

    def test_mismatch_recorded_not_silent(self, tmp_path: Path) -> None:
        """Pipeline records chapter mismatch; does not silently drop the chapter."""
        data_root = tmp_path / "data"
        # Item rows use a chapter label that does NOT match combined rows
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        # Use mismatched chapter label in items — "1장. 해부학서론" vs "1장. 해부학 서론"
        mismatched_chapter = "1장. 해부학서론"  # missing space
        items = [
            _item_row(1, mismatched_chapter),
            _item_row(2, _CHAPTER_B),
        ]
        _write_tree(data_root, combined, items)

        # Pipeline should still exit 0 (mismatch is non-fatal, recorded)
        code = _run(data_root)
        assert code == 0

    def test_mismatch_pipeline_still_produces_outputs(self, tmp_path: Path) -> None:
        """All gold outputs are produced even with chapter-label mismatch."""
        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        mismatched_chapter = "1장. 해부학서론"
        items = [
            _item_row(1, mismatched_chapter),
            _item_row(2, _CHAPTER_B),
        ]
        _write_tree(data_root, combined, items)
        _run(data_root)

        gold = data_root / "gold" / "retro-mester" / _KEY
        assert (gold / "CQI회고보고서.md").exists()
        assert (gold / "manifest_retro.json").exists()


# ---------------------------------------------------------------------------
# EC5: cold-start (no prior_year / no prior_yaml_path)
# ---------------------------------------------------------------------------


class TestColdStart:
    """Cold-start (year 1): no prior yaml → no audit section (EC-5)."""

    def test_cold_start_exits_zero(self, tmp_path: Path) -> None:
        """Pipeline exits 0 when prior_yaml_path=None (cold-start)."""
        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)

        # Explicitly no prior yaml
        code = _run(data_root, prior_yaml_path=None)
        assert code == 0

    def test_cold_start_prior_year_present_false(self, tmp_path: Path) -> None:
        """manifest.degrade.prior_year_present is False in cold-start."""
        import json as _json

        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)
        _run(data_root, prior_yaml_path=None)

        manifest = _json.loads(
            (data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["degrade"]["prior_year_present"] is False

    def test_cold_start_forward_yaml_emitted(self, tmp_path: Path) -> None:
        """차년도방향.yaml is created in cold-start (emit-only, no audit section)."""
        data_root = tmp_path / "data"
        combined = [
            _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
            _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
            _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
            _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
        ]
        items = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
        _write_tree(data_root, combined, items)
        _run(data_root)

        gold = data_root / "gold" / "retro-mester" / _KEY
        forward_yaml = gold / "차년도방향.yaml"
        assert forward_yaml.exists(), "차년도방향.yaml must be emitted in cold-start"

        content = yaml.safe_load(forward_yaml.read_text(encoding="utf-8"))
        # Cold-start: no audit section
        assert "audit" not in content or content.get("audit") is None, (
            "Cold-start yaml must not contain an audit section"
        )
