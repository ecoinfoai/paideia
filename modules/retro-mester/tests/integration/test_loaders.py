"""Integration tests for retro-mester foundational loaders (T013–T016).

RED: these tests are written before the loader implementations exist.
Each test builds minimal fixture files in a tmp_path, exercises the loader,
and asserts boundary contracts.

Fixture parquet files are built with pandas; no determinism flags needed
(fixtures, not production artefacts).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from retro_mester.load.errors import InputError


# ---------------------------------------------------------------------------
# Helpers: minimal valid row dicts
# ---------------------------------------------------------------------------


def _combined_row(
    student_id: str = "2026000001",
    semester: str = "2026-1",
    course_slug: str = "anatomy",
    exam_taken: bool = True,
    total_score: float | None = 80.0,
    score_percent: float | None = 80.0,
    section_percentile: float | None = 75.0,
    cohort_percentile: float | None = 70.0,
    z_score: float | None = 0.5,
    chapter_correct_rates: dict | None = None,
) -> dict:
    """Return a minimal dict that survives CombinedAnalysisRow validation."""
    if chapter_correct_rates is None:
        chapter_correct_rates = {"1장. 해부학 서론": 0.8}

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
        "exam_taken": exam_taken,
        "total_score": total_score if exam_taken else None,
        "score_percent": score_percent if exam_taken else None,
        "section_percentile": section_percentile if exam_taken else None,
        "cohort_percentile": cohort_percentile if exam_taken else None,
        "z_score": z_score if exam_taken else None,
        # dict columns — stored as JSON strings in parquet
        "chapter_correct_rates": json.dumps(chapter_correct_rates),
        "source_correct_rates": json.dumps({"형성평가": 0.75}),
        "difficulty_correct_rates": json.dumps({"1": 0.9, "2": 0.7, "3": 0.5}),
        "expected_difficulty_correct_rates": json.dumps({"쉬움": 0.9, "보통": 0.7, "어려움": 0.5}),
        "item_type_correct_rates": json.dumps({"지식축적": 0.8, "이해": 0.7}),
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
        # Group 6 — auxiliary
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
        # Group 7 — metadata
        "진단응답": False,
        "시험응시": exam_taken,
        "needs_map_schema_version": "0.1.1",
        "immersio_phase2_schema_version": "0.1.0",
    }
    # axes — all missing (no diagnostic response)
    for axis in axes:
        row[f"{axis}_raw"] = None
        row[f"{axis}_z"] = None
        row[f"{axis}_missing"] = True
    return row


def _item_statistics_row(
    item_no: int = 1,
    semester: str = "2026-1",
    course_slug: str = "anatomy",
    chapter: str = "1장. 해부학 서론",
) -> dict:
    """Return a minimal dict that survives ItemStatistics validation."""
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
        "n_correct": 14,
        "n_omit": 0,
        "correct_rate": 0.70,
        "omit_rate": 0.00,
        "discrimination_index": 0.30,
        "point_biserial": 0.45,
        "top_distractor_no": 2,
        "top_distractor_rate": 0.15,
        "is_top_distractor_adjacent": True,
        "option_distribution": json.dumps({1: 0.10, 2: 0.15, 3: 0.70, 4: 0.05, 5: 0.00}),
        "distractor_label": "특이사항 없음",
    }


def _write_combined_parquet(path: Path, rows: list[dict]) -> None:
    """Write rows as combined analysis parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_items_parquet(path: Path, rows: list[dict]) -> None:
    """Write rows as item statistics parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_examen_manifest(path: Path, blueprint: dict, curriculum_entries: dict) -> None:
    """Write minimal manifest_examen.json with blueprint + curriculum_entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "blueprint": blueprint,
        "curriculum_entries": curriculum_entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _minimal_blueprint(semester: str = "2026-1", course_slug: str = "anatomy") -> dict:
    """Return a minimal ExamenBlueprint model_dump dict."""
    return {
        "semester": semester,
        "course_slug": course_slug,
        "exam_name": "2026-1학기 기말고사",
        "total_items": 40,
        "chapters": ["1장. 해부학 서론"],
        "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
        "source_mix": {"formative": 18, "quiz": 12, "textbook": 10},
        "quiz_target": 12,
        "answer_key_balance": True,
    }


def _minimal_curriculum(semester: str = "2026-1", course_slug: str = "anatomy") -> dict:
    """Return a minimal CurriculumMap model_dump dict."""
    return {
        "semester": semester,
        "course_slug": course_slug,
        "entries": [
            {
                "week": 1,
                "chapter": "1장. 해부학 서론",
                "chapter_no": 1,
                "subtopic": None,
                "sections": ["1.1 인체의 조직"],
            }
        ],
    }


def _write_retro_config_yaml(path: Path, extra: dict | None = None) -> None:
    """Write a minimal valid retro_config.yaml."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "group_roster": {
            "2026000001": "학령기",
            "2026000002": "만학도",
        },
        "unit_importance": {
            "1장. 해부학 서론": "상",
        },
        "gap_threshold": 0.6,
        "baseline_segment": "만학도",
        "low_discrimination_threshold": 0.2,
        "cognitive_cliff_drop": 0.15,
        "effort_ratings": {
            "1장. 해부학 서론": "상",
        },
    }
    if extra:
        data.update(extra)
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# T013: load_combined
# ---------------------------------------------------------------------------


class TestLoadCombined:
    """T013: loads 진단×시험결합.parquet → list[CombinedAnalysisRow]."""

    def test_happy_path_round_trip(self, tmp_path: Path) -> None:
        """Two valid rows should be loaded and JSON-dict columns decoded."""
        from retro_mester.load.combined import load_combined

        parquet = tmp_path / "진단×시험결합.parquet"
        rows = [
            _combined_row("2026000001"),
            _combined_row("2026000002"),
        ]
        _write_combined_parquet(parquet, rows)

        result = load_combined(parquet)

        assert len(result) == 2
        assert result[0].student_id == "2026000001"
        # JSON-decoded dict column
        assert isinstance(result[0].chapter_correct_rates, dict)
        assert "1장. 해부학 서론" in result[0].chapter_correct_rates
        # difficulty_correct_rates keys must be int
        assert isinstance(next(iter(result[0].difficulty_correct_rates.keys())), int)

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """Missing parquet path raises InputError naming the path."""
        from retro_mester.load.combined import load_combined

        missing = tmp_path / "no-such.parquet"
        with pytest.raises(InputError) as exc_info:
            load_combined(missing)
        assert str(missing) in str(exc_info.value)

    def test_malformed_row_raises_input_error_with_index(self, tmp_path: Path) -> None:
        """A row with invalid data raises InputError with path + row index."""
        from retro_mester.load.combined import load_combined

        parquet = tmp_path / "진단×시험결합.parquet"
        bad = _combined_row("2026000001")
        # score_percent > 100 violates ge=0, le=100 constraint
        bad["score_percent"] = 999.0
        _write_combined_parquet(parquet, [bad])

        with pytest.raises(InputError) as exc_info:
            load_combined(parquet)
        msg = str(exc_info.value)
        assert str(parquet) in msg
        assert "0" in msg  # row index

    def test_option_distribution_keys_int(self, tmp_path: Path) -> None:
        """chapter_correct_rates is decoded from JSON string; keys are str (fine)."""
        from retro_mester.load.combined import load_combined

        parquet = tmp_path / "진단×시험결합.parquet"
        _write_combined_parquet(parquet, [_combined_row()])
        result = load_combined(parquet)
        # difficulty_correct_rates must have int keys
        dcr = result[0].difficulty_correct_rates
        for k in dcr:
            assert isinstance(k, int), f"expected int key, got {type(k)}: {k}"


# ---------------------------------------------------------------------------
# T014: load_items + chapter mismatch reconcile
# ---------------------------------------------------------------------------


class TestLoadItems:
    """T014: loads 문항통계.parquet → list[ItemStatistics] + chapter mismatch."""

    def test_happy_path_round_trip(self, tmp_path: Path) -> None:
        """One valid item row round-trips to ItemStatistics."""
        from retro_mester.load.items import load_items

        parquet = tmp_path / "문항통계.parquet"
        _write_items_parquet(parquet, [_item_statistics_row()])

        result, report = load_items(parquet)

        assert len(result) == 1
        assert result[0].item_no == 1
        # option_distribution is decoded from JSON to dict[int, float]
        assert isinstance(result[0].option_distribution, dict)
        assert all(isinstance(k, int) for k in result[0].option_distribution)

    def test_chapter_mismatch_report(self, tmp_path: Path) -> None:
        """Chapters in items but not in combined are reported in mismatch report."""
        from retro_mester.load.items import load_items

        parquet = tmp_path / "문항통계.parquet"
        rows = [
            _item_statistics_row(chapter="1장. 해부학 서론"),
            _item_statistics_row(item_no=2, chapter="2장. 세포"),  # extra chapter
        ]
        _write_items_parquet(parquet, rows)

        combined_chapters = {"1장. 해부학 서론"}
        result, report = load_items(parquet, combined_chapters=combined_chapters)

        assert len(result) == 2
        # 2장. 세포 is in items but not in combined → mismatch
        assert "2장. 세포" in report["items_not_in_combined"]

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """Missing parquet path raises InputError."""
        from retro_mester.load.items import load_items

        with pytest.raises(InputError) as exc_info:
            load_items(tmp_path / "missing.parquet")
        assert str(tmp_path / "missing.parquet") in str(exc_info.value)

    def test_malformed_row_raises_input_error(self, tmp_path: Path) -> None:
        """Row with invalid n_correct > n_responders raises InputError with index."""
        from retro_mester.load.items import load_items

        parquet = tmp_path / "문항통계.parquet"
        bad = _item_statistics_row()
        bad["n_correct"] = 999  # > n_responders=20
        _write_items_parquet(parquet, [bad])

        with pytest.raises(InputError) as exc_info:
            load_items(parquet)
        msg = str(exc_info.value)
        assert str(parquet) in msg
        assert "0" in msg


# ---------------------------------------------------------------------------
# T015: load_examen_manifest
# ---------------------------------------------------------------------------


class TestLoadExamenManifest:
    """T015: loads manifest_examen.json → (ExamenBlueprint, CurriculumMap)."""

    def test_happy_path(self, tmp_path: Path) -> None:
        """Valid manifest returns (ExamenBlueprint, CurriculumMap) pair."""
        from retro_mester.load.examen import load_examen_manifest

        manifest_path = tmp_path / "manifest_examen.json"
        _write_examen_manifest(
            manifest_path,
            _minimal_blueprint(),
            _minimal_curriculum(),
        )

        blueprint, curriculum = load_examen_manifest(
            manifest_path,
            semester="2026-1",
            course_slug="anatomy",
        )

        assert blueprint.semester == "2026-1"
        assert blueprint.course_slug == "anatomy"
        assert len(blueprint.chapters) == 1
        assert curriculum.semester == "2026-1"
        assert len(curriculum.entries) == 1

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """Missing manifest raises InputError naming the path."""
        from retro_mester.load.examen import load_examen_manifest

        missing = tmp_path / "no-manifest.json"
        with pytest.raises(InputError) as exc_info:
            load_examen_manifest(missing, semester="2026-1", course_slug="anatomy")
        assert str(missing) in str(exc_info.value)

    def test_semester_mismatch_raises_input_error(self, tmp_path: Path) -> None:
        """Blueprint semester mismatch raises InputError."""
        from retro_mester.load.examen import load_examen_manifest

        manifest_path = tmp_path / "manifest_examen.json"
        _write_examen_manifest(
            manifest_path,
            _minimal_blueprint(semester="2025-2"),
            _minimal_curriculum(semester="2025-2"),
        )

        with pytest.raises(InputError) as exc_info:
            load_examen_manifest(
                manifest_path,
                semester="2026-1",
                course_slug="anatomy",
            )
        assert "2025-2" in str(exc_info.value) or "semester" in str(exc_info.value).lower()

    def test_course_slug_mismatch_raises_input_error(self, tmp_path: Path) -> None:
        """Blueprint course_slug mismatch raises InputError."""
        from retro_mester.load.examen import load_examen_manifest

        manifest_path = tmp_path / "manifest_examen.json"
        _write_examen_manifest(
            manifest_path,
            _minimal_blueprint(course_slug="physiology"),
            _minimal_curriculum(course_slug="physiology"),
        )

        with pytest.raises(InputError) as exc_info:
            load_examen_manifest(
                manifest_path,
                semester="2026-1",
                course_slug="anatomy",
            )
        assert "physiology" in str(exc_info.value) or "course_slug" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# T016: load_config + reconcile_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """T016: load_config → RetroMesterConfig; reconcile_config → ConfigReconcileReport."""

    def test_happy_path(self, tmp_path: Path) -> None:
        """Valid YAML parses to RetroMesterConfig."""
        from retro_mester.load.config import load_config

        cfg_path = tmp_path / "retro_config.yaml"
        _write_retro_config_yaml(cfg_path)

        cfg = load_config(cfg_path)

        assert cfg.semester == "2026-1"
        assert cfg.course_slug == "anatomy"
        assert len(cfg.group_roster) == 2

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """Missing config file raises InputError."""
        from retro_mester.load.config import load_config

        with pytest.raises(InputError) as exc_info:
            load_config(tmp_path / "no-config.yaml")
        assert "no-config.yaml" in str(exc_info.value)

    def test_invalid_yaml_raises_input_error(self, tmp_path: Path) -> None:
        """A malformed gap_threshold raises InputError."""
        from retro_mester.load.config import load_config

        cfg_path = tmp_path / "retro_config.yaml"
        _write_retro_config_yaml(cfg_path, extra={"gap_threshold": 2.0})  # > 1.0

        with pytest.raises(InputError):
            load_config(cfg_path)


class TestReconcileConfig:
    """T016 reconcile: extraneous keys → InputError; unclassified students → report."""

    def _make_config(self, tmp_path: Path) -> object:
        from retro_mester.load.config import load_config

        cfg_path = tmp_path / "retro_config.yaml"
        _write_retro_config_yaml(cfg_path)
        return load_config(cfg_path)

    def test_extraneous_unit_importance_key_raises_input_error(self, tmp_path: Path) -> None:
        """unit_importance key not in chapters set raises InputError."""
        from retro_mester.load.config import load_config, reconcile_config

        cfg_path = tmp_path / "retro_config.yaml"
        # unit_importance has "1장. 해부학 서론" but chapters excludes it
        _write_retro_config_yaml(cfg_path)
        cfg = load_config(cfg_path)

        chapters: set[str] = set()  # "1장. 해부학 서론" not in chapters
        student_ids: set[str] = {"2026000001", "2026000002"}

        with pytest.raises(InputError) as exc_info:
            reconcile_config(cfg, chapters, student_ids)
        assert "1장. 해부학 서론" in str(exc_info.value)

    def test_extraneous_effort_rating_chapter_raises_input_error(self, tmp_path: Path) -> None:
        """effort_ratings chapter key not in chapters set raises InputError."""
        from retro_mester.load.config import load_config, reconcile_config

        cfg_path = tmp_path / "retro_config.yaml"
        _write_retro_config_yaml(cfg_path)
        cfg = load_config(cfg_path)

        # unit_importance key matches, but effort_ratings key is extraneous
        chapters: set[str] = {"1장. 해부학 서론"}
        student_ids: set[str] = {"2026000001", "2026000002"}

        # effort_ratings has "1장. 해부학 서론" — must NOT raise if it IS in chapters
        # Now use a config with an extraneous effort_rating key
        from retro_mester.load.config import reconcile_config
        from paideia_shared.schemas import RetroMesterConfig

        cfg2 = RetroMesterConfig(
            semester="2026-1",
            course_slug="anatomy",
            group_roster={"2026000001": "학령기"},
            unit_importance={"1장. 해부학 서론": "상"},
            effort_ratings={"99장. 없는 챕터": "중"},  # extraneous
        )
        with pytest.raises(InputError) as exc_info:
            reconcile_config(cfg2, chapters, student_ids)
        assert "99장. 없는 챕터" in str(exc_info.value)

    def test_effort_ratings_segment_key_chapter_part_checked(self, tmp_path: Path) -> None:
        """effort_ratings key 'chapter|segment' — only chapter part is checked."""
        from paideia_shared.schemas import RetroMesterConfig
        from retro_mester.load.config import reconcile_config

        chapters: set[str] = {"1장. 해부학 서론"}
        student_ids: set[str] = set()

        cfg = RetroMesterConfig(
            semester="2026-1",
            course_slug="anatomy",
            group_roster={},
            unit_importance={"1장. 해부학 서론": "상"},
            effort_ratings={"1장. 해부학 서론|이해": "상"},  # chapter|segment form
        )
        # Should NOT raise — chapter part "1장. 해부학 서론" is in chapters
        report = reconcile_config(cfg, chapters, student_ids)
        assert report is not None

    def test_unclassified_students_collected_not_raised(self, tmp_path: Path) -> None:
        """group_roster students not in student_ids are collected, not raised."""
        from retro_mester.load.config import load_config, reconcile_config

        cfg_path = tmp_path / "retro_config.yaml"
        _write_retro_config_yaml(cfg_path)
        cfg = load_config(cfg_path)

        # student_ids excludes one roster student
        chapters = {"1장. 해부학 서론"}
        student_ids = {"2026000001"}  # 2026000002 is in roster but not here

        report = reconcile_config(cfg, chapters, student_ids)

        assert "unclassified_students" in report
        assert "2026000002" in report["unclassified_students"]

    def test_all_valid_returns_empty_unclassified(self, tmp_path: Path) -> None:
        """When all roster students are in student_ids, unclassified is empty."""
        from retro_mester.load.config import load_config, reconcile_config

        cfg_path = tmp_path / "retro_config.yaml"
        _write_retro_config_yaml(cfg_path)
        cfg = load_config(cfg_path)

        chapters = {"1장. 해부학 서론"}
        student_ids = {"2026000001", "2026000002"}

        report = reconcile_config(cfg, chapters, student_ids)

        assert report["unclassified_students"] == []
