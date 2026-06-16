"""T061 — Performance smoke test for retro-mester pipeline.

A realistic-scale fixture (~120 students, ~12 chapters) must complete
run_retro in well under 10 seconds.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import yaml

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEMESTER}-{_COURSE}"

_N_STUDENTS = 120
_N_CHAPTERS = 12

_CHAPTERS = [f"{i}장. 해부학{i:02d}" for i in range(1, _N_CHAPTERS + 1)]

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

_PERF_THRESHOLD_SECONDS = 10.0


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _combined_row(student_id: str, chapter_rates: dict[str, float]) -> dict:
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
        "total_score": 65.0,
        "score_percent": 65.0,
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


def _item_row(item_no: int, chapter: str, disc: float = 0.25) -> dict:
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
        "discrimination_index": disc,
        "point_biserial": 0.35,
        "top_distractor_no": 2,
        "top_distractor_rate": 0.20,
        "is_top_distractor_adjacent": True,
        "option_distribution": json.dumps({1: 0.1, 2: 0.2, 3: 0.5, 4: 0.1, 5: 0.1}),
        "distractor_label": "특이사항 없음",
    }


def _build_large_fixture(data_root: Path) -> None:
    """Build a realistic-scale fixture (120 students × 12 chapters)."""
    silver_im = data_root / "silver" / "immersio" / _KEY
    silver_im.mkdir(parents=True, exist_ok=True)

    # 120 students: alternating 학령기 / 만학도, all below gap_threshold (0.6)
    combined_rows = []
    for i in range(_N_STUDENTS):
        sid = f"2026{i:06d}"
        # Alternate rates slightly around 0.4–0.55 so detection is uniform
        rates = dict.fromkeys(_CHAPTERS, 0.4 + i % 5 * 0.03)
        combined_rows.append(_combined_row(sid, rates))

    pd.DataFrame(combined_rows).to_parquet(silver_im / "진단×시험결합.parquet", index=False)

    # 2 items per chapter = 24 items
    item_rows = []
    for idx, ch in enumerate(_CHAPTERS):
        item_rows.append(_item_row(idx * 2 + 1, ch, disc=0.25))
        item_rows.append(_item_row(idx * 2 + 2, ch, disc=0.30))

    pd.DataFrame(item_rows).to_parquet(silver_im / "문항통계.parquet", index=False)

    # Bronze
    bronze = data_root / "bronze" / "retro-mester" / _KEY
    bronze.mkdir(parents=True, exist_ok=True)

    roster: dict[str, str] = {}
    for i in range(_N_STUDENTS):
        sid = f"2026{i:06d}"
        roster[sid] = "학령기" if i % 2 == 0 else "만학도"

    cfg = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "group_roster": roster,
        "unit_importance": dict.fromkeys(_CHAPTERS, "중"),
        "gap_threshold": 0.6,
        "baseline_segment": "만학도",
        "low_discrimination_threshold": 0.2,
        "cognitive_cliff_drop": 0.15,
        "effort_ratings": dict.fromkeys(_CHAPTERS, "중"),
    }
    (bronze / "retro_config.yaml").write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")

    blueprint = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "exam_name": "기말고사",
        "total_items": 40,
        "chapters": _CHAPTERS,
        "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
        "source_mix": {"formative": 18, "quiz": 12, "textbook": 10},
        "quiz_target": 12,
        "answer_key_balance": True,
    }
    (bronze / "blueprint.yaml").write_text(
        yaml.dump(blueprint, allow_unicode=True), encoding="utf-8"
    )

    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": i + 1,
                "chapter": ch,
                "chapter_no": i + 1,
                "subtopic": None,
                "sections": [f"{i + 1}.1 절"],
            }
            for i, ch in enumerate(_CHAPTERS)
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        yaml.dump(curriculum, allow_unicode=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Performance smoke test
# ---------------------------------------------------------------------------


class TestPerfSmoke:
    """T061: realistic-scale run must complete under 10 seconds."""

    def test_large_fixture_completes_under_threshold(self, tmp_path: Path) -> None:
        """120 students × 12 chapters finishes in < 10 s (llm_mode=off)."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_large_fixture(data_root)

        start = time.monotonic()
        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )
        elapsed = time.monotonic() - start

        assert code == 0, f"Pipeline failed: exit {code}"
        assert elapsed < _PERF_THRESHOLD_SECONDS, (
            f"Pipeline took {elapsed:.2f}s; must be < {_PERF_THRESHOLD_SECONDS}s "
            f"for {_N_STUDENTS} students × {_N_CHAPTERS} chapters"
        )

    def test_large_fixture_gold_outputs_present(self, tmp_path: Path) -> None:
        """All gold artefacts are produced for the large fixture."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_large_fixture(data_root)

        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )

        gold = data_root / "gold" / "retro-mester" / _KEY
        for artefact in [
            "CQI회고보고서.md",
            "회고분석.xlsx",
            "manifest_retro.json",
            "차년도방향.yaml",
        ]:
            assert (gold / artefact).exists(), f"Missing: {artefact}"
