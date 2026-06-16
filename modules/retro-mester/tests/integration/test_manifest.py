"""T060 — manifest_retro.json completeness integration tests.

Verifies:
- manifest.degrade carries: llm_used, prior_year_present, granularity_note
- manifest.counts carries: students, segments, gaps, recommendations,
  covered, uncovered_ratio, unclassified_students
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


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _combined_row(
    student_id: str,
    chapter_rates: dict[str, float] | None = None,
) -> dict:
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


def _item_row(item_no: int, chapter: str = _CHAPTER_A) -> dict:
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
        "discrimination_index": 0.25,
        "point_biserial": 0.35,
        "top_distractor_no": 2,
        "top_distractor_rate": 0.20,
        "is_top_distractor_adjacent": True,
        "option_distribution": json.dumps({1: 0.1, 2: 0.2, 3: 0.5, 4: 0.1, 5: 0.1}),
        "distractor_label": "특이사항 없음",
    }


def _build_and_run(
    data_root: Path,
    prior_yaml_path: str | None = None,
    group_roster: dict | None = None,
) -> dict:
    """Build fixture, run pipeline, return parsed manifest dict."""
    silver_im = data_root / "silver" / "immersio" / _KEY
    silver_im.mkdir(parents=True, exist_ok=True)

    if group_roster is None:
        group_roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "만학도",
            "2026000004": "만학도",
        }

    combined = [
        _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
        _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
        _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
        _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
    ]
    pd.DataFrame(combined).to_parquet(silver_im / "진단×시험결합.parquet", index=False)
    pd.DataFrame([_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]).to_parquet(
        silver_im / "문항통계.parquet", index=False
    )

    bronze = data_root / "bronze" / "retro-mester" / _KEY
    bronze.mkdir(parents=True, exist_ok=True)
    cfg = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "group_roster": group_roster,
        "unit_importance": {_CHAPTER_A: "상", _CHAPTER_B: "중"},
        "gap_threshold": 0.6,
        "baseline_segment": "만학도",
        "low_discrimination_threshold": 0.2,
        "cognitive_cliff_drop": 0.15,
        "effort_ratings": {_CHAPTER_A: "상", _CHAPTER_B: "중"},
    }
    (bronze / "retro_config.yaml").write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    (bronze / "blueprint.yaml").write_text(
        yaml.dump(
            {
                "semester": _SEMESTER,
                "course_slug": _COURSE,
                "exam_name": "기말고사",
                "total_items": 40,
                "chapters": [_CHAPTER_A, _CHAPTER_B],
                "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
                "source_mix": {"formative": 18, "quiz": 12, "textbook": 10},
                "quiz_target": 12,
                "answer_key_balance": True,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (bronze / "curriculum_map.yaml").write_text(
        yaml.dump(
            {
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
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    from retro_mester.pipeline import run_retro

    code = run_retro(
        semester=_SEMESTER,
        course=_COURSE,
        data_root=str(data_root),
        llm_mode="off",
        prior_yaml_path=prior_yaml_path,
    )
    assert code == 0, f"Pipeline failed: exit {code}"

    return json.loads(
        (data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json").read_text(
            encoding="utf-8"
        )
    )


# ---------------------------------------------------------------------------
# T060: degrade fields
# ---------------------------------------------------------------------------


class TestManifestDegrade:
    """manifest.degrade must carry llm_used, prior_year_present, granularity_note."""

    def test_degrade_has_llm_used(self, tmp_path: Path) -> None:
        """manifest.degrade['llm_used'] is present and False for llm_mode='off'."""
        manifest = _build_and_run(tmp_path / "data")
        assert "llm_used" in manifest["degrade"], "degrade missing llm_used"
        assert manifest["degrade"]["llm_used"] is False

    def test_degrade_has_prior_year_present_false(self, tmp_path: Path) -> None:
        """manifest.degrade['prior_year_present'] is False when no prior yaml."""
        manifest = _build_and_run(tmp_path / "data")
        assert "prior_year_present" in manifest["degrade"], "degrade missing prior_year_present"
        assert manifest["degrade"]["prior_year_present"] is False

    def test_degrade_has_granularity_note(self, tmp_path: Path) -> None:
        """manifest.degrade['granularity_note'] describes the 3-way cross limitation."""
        manifest = _build_and_run(tmp_path / "data")
        assert "granularity_note" in manifest["degrade"], "degrade missing granularity_note"
        note = manifest["degrade"]["granularity_note"]
        assert isinstance(note, str) and len(note) > 10, (
            f"granularity_note is too short or empty: {note!r}"
        )
        # Should mention the 3-way cross or 교차
        assert "교차" in note or "3원" in note or "item_type" in note, (
            f"granularity_note does not reference 3-way cross: {note!r}"
        )


# ---------------------------------------------------------------------------
# T060: counts fields
# ---------------------------------------------------------------------------


class TestManifestCounts:
    """manifest.counts must carry all required metrics."""

    _REQUIRED_COUNTS = [
        "students",
        "segments",
        "gaps",
        "recommendations",
        "covered",
        "uncovered_ratio",
        "unclassified_students",
    ]

    def test_all_required_count_keys_present(self, tmp_path: Path) -> None:
        """All required keys exist in manifest.counts."""
        manifest = _build_and_run(tmp_path / "data")
        counts = manifest["counts"]
        for key in self._REQUIRED_COUNTS:
            assert key in counts, f"manifest.counts missing key: {key}"

    def test_students_count_matches_fixture(self, tmp_path: Path) -> None:
        """manifest.counts['students'] equals the number of rows in the fixture."""
        manifest = _build_and_run(tmp_path / "data")
        assert manifest["counts"]["students"] == 4.0

    def test_segments_count_matches_roster(self, tmp_path: Path) -> None:
        """manifest.counts['segments'] equals the number of distinct segment buckets."""
        manifest = _build_and_run(tmp_path / "data")
        # Fixture has 학령기 and 만학도 — both appear → 2 segments
        assert manifest["counts"]["segments"] == 2.0

    def test_unclassified_students_zero_when_all_in_roster(self, tmp_path: Path) -> None:
        """manifest.counts['unclassified_students'] is 0 when all students in roster."""
        manifest = _build_and_run(tmp_path / "data")
        assert manifest["counts"]["unclassified_students"] == 0.0

    def test_unclassified_students_nonzero_when_missing_from_roster(self, tmp_path: Path) -> None:
        """manifest.counts['unclassified_students'] > 0 when a student is not in roster."""
        # Omit student 2026000004 from the roster
        roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "만학도",
            # 2026000004 deliberately not in roster
        }
        manifest = _build_and_run(tmp_path / "data", group_roster=roster)
        assert manifest["counts"]["unclassified_students"] == 1.0, (
            "Expected 1 unclassified student (2026000004 not in roster)"
        )

    def test_covered_lte_recommendations(self, tmp_path: Path) -> None:
        """manifest.counts['covered'] <= manifest.counts['recommendations']."""
        manifest = _build_and_run(tmp_path / "data")
        assert manifest["counts"]["covered"] <= manifest["counts"]["recommendations"]

    def test_uncovered_ratio_is_numeric(self, tmp_path: Path) -> None:
        """manifest.counts['uncovered_ratio'] is a number (float or None)."""
        manifest = _build_and_run(tmp_path / "data")
        ratio = manifest["counts"]["uncovered_ratio"]
        assert ratio is None or isinstance(ratio, (int, float)), (
            f"uncovered_ratio must be numeric or null, got {type(ratio)}"
        )
