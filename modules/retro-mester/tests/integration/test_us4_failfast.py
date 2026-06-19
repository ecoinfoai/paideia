"""US4 (T022) — semester/course 3-way fail-fast guard integration tests.

The pipeline must reject inputs where the data's (semester, course_slug),
the CLI request (semester, course), and the config's (semester, course_slug)
do not all agree, or where the data parquet mixes more than one cohort.

A rejected run returns exit 2 (InputError) and writes NO output files.

RED phase: written before the guard exists in pipeline.py.
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

_STUDENT_IDS = {
    "2026000001": "학령기",
    "2026000002": "학령기",
    "2026000003": "만학도",
    "2026000004": "만학도",
}

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
    chapter_rates: dict[str, float],
    *,
    semester: str = _SEMESTER,
    course_slug: str = _COURSE,
    cluster_label: str | None = None,
) -> dict:
    has_cluster = cluster_label is not None
    row: dict = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": semester,
        "course_slug": course_slug,
        "cluster_id": 1 if has_cluster else None,
        "cluster_label": cluster_label,
        "cluster_distance": 0.1 if has_cluster else None,
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


def _item_row(item_no: int, chapter: str, correct_rate: float = 0.3) -> dict:
    return {
        "item_no": item_no,
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "chapter": chapter,
        "week": None,
        "item_type": "이해",
        "difficulty_level": 3,
        "expected_difficulty": "어려움",
        "source": "형성평가",
        "correct_answer": 3,
        "n_responders": 20,
        "n_correct": max(0, round(correct_rate * 20)),
        "n_omit": 0,
        "correct_rate": correct_rate,
        "omit_rate": 0.00,
        "discrimination_index": 0.25,
        "point_biserial": 0.35,
        "top_distractor_no": 2,
        "top_distractor_rate": 0.20,
        "is_top_distractor_adjacent": True,
        "option_distribution": json.dumps({1: 0.1, 2: 0.2, 3: 0.3, 4: 0.2, 5: 0.2}),
        "distractor_label": "특이사항 없음",
    }


def _build_fixture_tree(
    data_root: Path,
    *,
    data_semester: str = _SEMESTER,
    data_course: str = _COURSE,
    config_semester: str = _SEMESTER,
    config_course: str = _COURSE,
    mixed_cohort: bool = False,
) -> None:
    """Write a fixture tree under ``data_root``.

    The CLI request always uses ``_SEMESTER``/``_COURSE``; the data rows use
    ``data_semester``/``data_course`` and the ``retro_config.yaml`` uses
    ``config_semester``/``config_course`` so each guard branch can be
    exercised by varying only one source.
    """
    silver = data_root / "silver" / "immersio" / _KEY
    silver.mkdir(parents=True, exist_ok=True)

    rows = [
        _combined_row(
            "2026000001",
            {_CHAPTER_A: 0.35, _CHAPTER_B: 0.40},
            semester=data_semester,
            course_slug=data_course,
            cluster_label="전략적",
        ),
        _combined_row(
            "2026000002",
            {_CHAPTER_A: 0.40, _CHAPTER_B: 0.45},
            semester=data_semester,
            course_slug=data_course,
            cluster_label="전략적",
        ),
        _combined_row(
            "2026000003",
            {_CHAPTER_A: 0.30, _CHAPTER_B: 0.70},
            semester=data_semester,
            course_slug=data_course,
            cluster_label="습관중심",
        ),
        _combined_row(
            "2026000004",
            {_CHAPTER_A: 0.25, _CHAPTER_B: 0.75},
            semester=data_semester,
            course_slug=data_course,
            cluster_label="습관중심",
        ),
    ]
    if mixed_cohort:
        # Inject a second cohort's semester on one row.
        rows[-1] = _combined_row(
            "2026000004",
            {_CHAPTER_A: 0.25, _CHAPTER_B: 0.75},
            semester="2025-1",
            course_slug=data_course,
            cluster_label="습관중심",
        )
    pd.DataFrame(rows).to_parquet(silver / "진단×시험결합.parquet", index=False)

    item_rows = [
        _item_row(1, _CHAPTER_A, correct_rate=0.3),
        _item_row(2, _CHAPTER_B, correct_rate=0.35),
    ]
    pd.DataFrame(item_rows).to_parquet(silver / "문항통계.parquet", index=False)

    bronze = data_root / "bronze" / "retro-mester" / _KEY
    bronze.mkdir(parents=True, exist_ok=True)

    retro_cfg = {
        "semester": config_semester,
        "course_slug": config_course,
        "group_roster": _STUDENT_IDS,
        "unit_importance": {_CHAPTER_A: "상", _CHAPTER_B: "중"},
        "gap_threshold": 0.6,
        "baseline_segment": "만학도",
        "low_discrimination_threshold": 0.2,
        "cognitive_cliff_drop": 0.15,
        "effort_ratings": {_CHAPTER_A: "상", _CHAPTER_B: "중"},
    }
    blueprint = {
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
    curriculum = {
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
    (bronze / "retro_config.yaml").write_text(
        yaml.dump(retro_cfg, allow_unicode=True), encoding="utf-8"
    )
    (bronze / "blueprint.yaml").write_text(
        yaml.dump(blueprint, allow_unicode=True), encoding="utf-8"
    )
    (bronze / "curriculum_map.yaml").write_text(
        yaml.dump(curriculum, allow_unicode=True), encoding="utf-8"
    )


def _gold_silver(data_root: Path) -> tuple[Path, Path]:
    gold = data_root / "gold" / "retro-mester" / _KEY
    silver = data_root / "silver" / "retro-mester" / _KEY
    return gold, silver


def _assert_no_outputs(data_root: Path) -> None:
    """Assert that the retro-mester gold/silver output dirs were not produced."""
    gold, silver = _gold_silver(data_root)
    for d in (gold, silver):
        assert not d.exists() or not any(d.iterdir()), f"unexpected output under {d}"


class TestThreeWayGuard:
    """T022: 3-way (request × config × data) semester/course agreement."""

    def test_config_semester_mismatch_exits_2_no_output(self, tmp_path: Path) -> None:
        """Config semester != request → exit 2 (config branch) and no output."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root, config_semester="2025-2")

        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )
        assert code == 2
        _assert_no_outputs(data_root)

    def test_data_semester_mismatch_exits_2_no_output(self, tmp_path: Path) -> None:
        """Data semester != request/config → exit 2 and no output files."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root, data_semester="2025-2")

        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )
        assert code == 2
        _assert_no_outputs(data_root)

    def test_data_course_mismatch_exits_2_no_output(self, tmp_path: Path) -> None:
        """Data course != request/config → exit 2 and no output files."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root, data_course="physiology")

        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )
        assert code == 2
        _assert_no_outputs(data_root)

    def test_mixed_cohort_data_exits_2_no_output(self, tmp_path: Path) -> None:
        """Data rows spanning >1 semester → exit 2 and no output files."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root, mixed_cohort=True)

        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )
        assert code == 2
        _assert_no_outputs(data_root)

    def test_matching_request_passes(self, tmp_path: Path) -> None:
        """Matching request/config/data still runs to success (regression)."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )
        assert code == 0
        gold, _silver = _gold_silver(data_root)
        assert (gold / "CQI회고보고서.md").exists()
