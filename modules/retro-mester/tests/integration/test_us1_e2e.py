"""T030 — US1 end-to-end integration tests for the retro-mester pipeline.

RED phase: written before pipeline.py exists.  All tests must FAIL until
``retro_mester.pipeline.run_retro`` is implemented.

Tests build a minimal but complete fixture tree under ``tmp_path/data/`` and
call ``run_retro(..., data_root=tmp_path / "data")``.

Fixture layout:
  data/silver/immersio/{key}/진단×시험결합.parquet
  data/silver/immersio/{key}/문항통계.parquet
  data/bronze/retro-mester/{key}/retro_config.yaml
  data/bronze/retro-mester/{key}/blueprint.yaml
  data/bronze/retro-mester/{key}/curriculum_map.yaml
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Fixture helpers (shared with test_us1_determinism.py via inline duplication
# — no conftest import so each test module is self-contained)
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEMESTER}-{_COURSE}"

_CHAPTER_A = "1장. 해부학 서론"
_CHAPTER_B = "2장. 세포와 조직"


def _combined_row(
    student_id: str,
    chapter_rates: dict[str, float] | None = None,
    *,
    semester: str = _SEMESTER,
    course_slug: str = _COURSE,
) -> dict:
    """Return a minimal CombinedAnalysisRow-compatible dict."""
    if chapter_rates is None:
        chapter_rates = {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}

    axes = [
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    ]
    row: dict = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": semester,
        "course_slug": course_slug,
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
    for axis in axes:
        row[f"{axis}_raw"] = None
        row[f"{axis}_z"] = None
        row[f"{axis}_missing"] = True
    return row


def _item_row(
    item_no: int,
    chapter: str = _CHAPTER_A,
    *,
    semester: str = _SEMESTER,
    course_slug: str = _COURSE,
) -> dict:
    """Return a minimal ItemStatistics-compatible dict."""
    return {
        "item_no": item_no,
        "semester": semester,
        "course_slug": course_slug,
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


def _blueprint(semester: str = _SEMESTER, course_slug: str = _COURSE) -> dict:
    return {
        "semester": semester,
        "course_slug": course_slug,
        "exam_name": "2026-1학기 기말고사",
        "total_items": 40,
        "chapters": [_CHAPTER_A, _CHAPTER_B],
        "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
        "source_mix": {"formative": 18, "quiz": 12, "textbook": 10},
        "quiz_target": 12,
        "answer_key_balance": True,
    }


def _curriculum(semester: str = _SEMESTER, course_slug: str = _COURSE) -> dict:
    return {
        "semester": semester,
        "course_slug": course_slug,
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


def _retro_config(semester: str = _SEMESTER, course_slug: str = _COURSE) -> dict:
    return {
        "semester": semester,
        "course_slug": course_slug,
        "group_roster": {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "만학도",
            "2026000004": "만학도",
        },
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


def _build_fixture_tree(data_root: Path) -> None:
    """Write the complete fixture file tree under ``data_root``."""
    key = _KEY

    # Silver immersio
    silver_dir = data_root / "silver" / "immersio" / key
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Four students: all below gap_threshold (0.6) so we get gaps to rank
    combined_rows = [
        _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
        _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
        _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
        _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
    ]
    pd.DataFrame(combined_rows).to_parquet(silver_dir / "진단×시험결합.parquet", index=False)

    item_rows = [
        _item_row(1, _CHAPTER_A),
        _item_row(2, _CHAPTER_B),
    ]
    pd.DataFrame(item_rows).to_parquet(silver_dir / "문항통계.parquet", index=False)

    # Bronze retro-mester
    bronze_dir = data_root / "bronze" / "retro-mester" / key
    bronze_dir.mkdir(parents=True, exist_ok=True)

    (bronze_dir / "retro_config.yaml").write_text(
        yaml.dump(_retro_config(), allow_unicode=True), encoding="utf-8"
    )
    (bronze_dir / "blueprint.yaml").write_text(
        yaml.dump(_blueprint(), allow_unicode=True), encoding="utf-8"
    )
    (bronze_dir / "curriculum_map.yaml").write_text(
        yaml.dump(_curriculum(), allow_unicode=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Happy-path E2E test
# ---------------------------------------------------------------------------


class TestUS1E2E:
    """T030: full pipeline wiring, US1 (no LLM)."""

    def test_exit_zero_and_all_outputs_present(self, tmp_path: Path) -> None:
        """run_retro exits 0 and produces all expected Gold+Silver artefacts."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )

        assert code == 0, f"Expected exit 0, got {code}"

        # Gold outputs
        gold = data_root / "gold" / "retro-mester" / _KEY
        assert (gold / "CQI회고보고서.md").exists(), "Missing CQI회고보고서.md"
        assert (gold / "CQI회고보고서.pdf").exists(), "Missing CQI회고보고서.pdf"
        assert (gold / "회고분석.xlsx").exists(), "Missing 회고분석.xlsx"
        assert (gold / "manifest_retro.json").exists(), "Missing manifest_retro.json"

        # Silver outputs
        silver = data_root / "silver" / "retro-mester" / _KEY
        assert (silver / "빈틈표.parquet").exists(), "Missing 빈틈표.parquet"
        assert (silver / "변경권고.parquet").exists(), "Missing 변경권고.parquet"

    def test_md_contains_ranked_changes_and_uncovered_ratio(self, tmp_path: Path) -> None:
        """The generated MD report has a ranked changes table and uncovered ratio."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))

        md_path = data_root / "gold" / "retro-mester" / _KEY / "CQI회고보고서.md"
        md_text = md_path.read_text(encoding="utf-8")

        # The report must contain the ranked-changes table header
        assert "변경 권고 요약" in md_text, "Missing section header"
        # And the uncovered-ratio summary line
        assert "못 덮은 빈틈 비율" in md_text, "Missing uncovered ratio line"

    def test_no_student_id_in_md(self, tmp_path: Path) -> None:
        """No student ID appears in the MD report (privacy guard)."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))

        md_path = data_root / "gold" / "retro-mester" / _KEY / "CQI회고보고서.md"
        md_text = md_path.read_text(encoding="utf-8")

        # Student IDs embedded in fixture
        for sid in ["2026000001", "2026000002", "2026000003", "2026000004"]:
            assert sid not in md_text, f"Student ID {sid} must NOT appear in MD"

    def test_manifest_structure(self, tmp_path: Path) -> None:
        """manifest_retro.json has required top-level keys and valid JSON."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))

        manifest_path = data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        required_keys = {
            "module_version",
            "schema_version",
            "semester",
            "course_slug",
            "inputs",
            "thresholds",
            "counts",
            "degrade",
            "generated_at_utc",
        }
        for k in required_keys:
            assert k in manifest, f"Missing manifest key: {k}"

        # US1 — llm_used must be False
        assert manifest["degrade"]["llm_used"] is False

    def test_missing_combined_parquet_exits_2(self, tmp_path: Path) -> None:
        """Missing 진단×시험결합.parquet → InputError → exit code 2."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        # Remove the combined parquet to trigger InputError
        combined = data_root / "silver" / "immersio" / _KEY / "진단×시험결합.parquet"
        combined.unlink()

        code = run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))

        assert code == 2, f"Expected exit 2 for missing input, got {code}"

    def test_missing_config_exits_2(self, tmp_path: Path) -> None:
        """Missing retro_config.yaml → InputError → exit code 2."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        config_path = data_root / "bronze" / "retro-mester" / _KEY / "retro_config.yaml"
        config_path.unlink()

        code = run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))

        assert code == 2, f"Expected exit 2 for missing config, got {code}"
