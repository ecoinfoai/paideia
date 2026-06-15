"""T056 — Integration tests for US6: optional LLM insight layer.

Tests must FAIL until T053–T055 are implemented.

Fixture layout (shared with test_us1_e2e.py — inlined for self-containment):
  data/silver/immersio/{key}/진단×시험결합.parquet
  data/silver/immersio/{key}/문항통계.parquet
  data/bronze/retro-mester/{key}/retro_config.yaml
  data/bronze/retro-mester/{key}/blueprint.yaml
  data/bronze/retro-mester/{key}/curriculum_map.yaml

All backend calls are monkeypatched — NO network is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import yaml


# ---------------------------------------------------------------------------
# Shared fixture helpers (inlined — self-contained test module)
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEMESTER}-{_COURSE}"
_CHAPTER_A = "1장. 해부학 서론"
_CHAPTER_B = "2장. 세포와 조직"


def _combined_row(
    student_id: str,
    chapter_rates: dict[str, float] | None = None,
) -> dict:
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
        "expected_difficulty_correct_rates": json.dumps(
            {"쉬움": 0.7, "보통": 0.5, "어려움": 0.3}
        ),
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


def _build_fixture_tree(data_root: Path) -> None:
    key = _KEY
    silver_dir = data_root / "silver" / "immersio" / key
    silver_dir.mkdir(parents=True, exist_ok=True)

    combined_rows = [
        _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
        _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
        _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
        _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
    ]
    pd.DataFrame(combined_rows).to_parquet(
        silver_dir / "진단×시험결합.parquet", index=False
    )
    item_rows = [_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]
    pd.DataFrame(item_rows).to_parquet(silver_dir / "문항통계.parquet", index=False)

    bronze_dir = data_root / "bronze" / "retro-mester" / key
    bronze_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "group_roster": {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "만학도",
            "2026000004": "만학도",
        },
        "unit_importance": {_CHAPTER_A: "상", _CHAPTER_B: "중"},
        "gap_threshold": 0.6,
        "baseline_segment": "만학도",
        "low_discrimination_threshold": 0.2,
        "cognitive_cliff_drop": 0.15,
        "effort_ratings": {_CHAPTER_A: "상", _CHAPTER_B: "중"},
    }
    (bronze_dir / "retro_config.yaml").write_text(
        yaml.dump(config, allow_unicode=True), encoding="utf-8"
    )

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
    (bronze_dir / "blueprint.yaml").write_text(
        yaml.dump(blueprint, allow_unicode=True), encoding="utf-8"
    )

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
    (bronze_dir / "curriculum_map.yaml").write_text(
        yaml.dump(curriculum, allow_unicode=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestUS6LLM:
    """T056: LLM insight layer integration tests — no network required."""

    # ------------------------------------------------------------------
    # SC1: off mode → exit 0, template insight, llm_used=false
    # ------------------------------------------------------------------

    def test_off_mode_exit_zero(self, tmp_path: Path) -> None:
        """--llm-mode off → pipeline exits 0."""
        from retro_mester.pipeline import run_retro

        _build_fixture_tree(tmp_path / "data")
        code = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(tmp_path / "data"),
            llm_mode="off",
        )
        assert code == 0, f"Expected exit 0 with --llm-mode off, got {code}"

    def test_off_mode_report_has_insight_block(self, tmp_path: Path) -> None:
        """--llm-mode off → MD report contains a (template) insight block."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)
        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )

        md_path = data_root / "gold" / "retro-mester" / _KEY / "CQI회고보고서.md"
        md_text = md_path.read_text(encoding="utf-8")
        # The insight block section header must be present
        assert "심층 분석" in md_text, "MD must contain insight section (B-LLM)"

    def test_off_mode_manifest_llm_used_false(self, tmp_path: Path) -> None:
        """--llm-mode off → manifest.degrade.llm_used == false."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)
        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )

        manifest_path = (
            data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["degrade"]["llm_used"] is False

    # ------------------------------------------------------------------
    # SC2: failing backend + require_llm=False → exit 0, fallback used
    # ------------------------------------------------------------------

    def test_failing_backend_no_require_llm_exit_zero(self, tmp_path: Path) -> None:
        """Stubbed FAILING backend + require_llm=False → exit 0 (graceful degradation)."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        with patch(
            "retro_mester.llm.client.generate",
            return_value=(None, "other"),
        ):
            code = run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=False,
            )
        assert code == 0, f"Expected exit 0 on failing backend with require_llm=False, got {code}"

    def test_failing_backend_no_require_llm_uses_fallback(
        self, tmp_path: Path
    ) -> None:
        """Stubbed FAILING backend + require_llm=False → fallback text, llm_used=false."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        with patch(
            "retro_mester.llm.client.generate",
            return_value=(None, "other"),
        ):
            run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=False,
            )

        manifest_path = (
            data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["degrade"]["llm_used"] is False, "llm_used must be false on fallback"

    # ------------------------------------------------------------------
    # SC3: failing backend + require_llm=True → exit 5
    # ------------------------------------------------------------------

    def test_failing_backend_with_require_llm_exits_5(self, tmp_path: Path) -> None:
        """Stubbed FAILING backend + require_llm=True → exit 5."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        with patch(
            "retro_mester.llm.client.generate",
            return_value=(None, "other"),
        ):
            code = run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=True,
            )
        assert code == 5, f"Expected exit 5 when LLM required but fails, got {code}"

    # ------------------------------------------------------------------
    # SC4: stubbed SUCCESS backend → insight in report, llm_used=true, cache hit on 2nd run
    # ------------------------------------------------------------------

    def test_success_backend_insight_in_report(self, tmp_path: Path) -> None:
        """Stubbed SUCCESS backend → insight block contains the LLM response."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        fixed_insight = "LLM_FIXED_INSIGHT_TEXT_FOR_TEST"

        with patch(
            "retro_mester.llm.client.generate",
            return_value=(fixed_insight, None),
        ):
            code = run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=False,
            )

        assert code == 0, f"Expected exit 0, got {code}"
        md_path = data_root / "gold" / "retro-mester" / _KEY / "CQI회고보고서.md"
        md_text = md_path.read_text(encoding="utf-8")
        assert fixed_insight in md_text, "MD must contain the LLM insight text"

    def test_success_backend_manifest_llm_used_true(self, tmp_path: Path) -> None:
        """Stubbed SUCCESS backend → manifest.degrade.llm_used == true."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        with patch(
            "retro_mester.llm.client.generate",
            return_value=("some insight", None),
        ):
            run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=False,
            )

        manifest_path = (
            data_root / "gold" / "retro-mester" / _KEY / "manifest_retro.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["degrade"]["llm_used"] is True

    def test_cache_hit_on_second_run(self, tmp_path: Path) -> None:
        """Second run with identical inputs hits the cache (same insight text, backend not called again)."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        call_count = 0
        fixed_insight = "CACHED_INSIGHT_TEXT"

        def stub_generate(prompt: str, *, mode: str) -> tuple[str | None, str | None]:
            nonlocal call_count
            call_count += 1
            return (fixed_insight, None)

        with patch("retro_mester.llm.client.generate", side_effect=stub_generate):
            # First run — cache miss → backend called
            run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=False,
            )
            # Second run — cache hit → backend NOT called again
            run_retro(
                semester=_SEMESTER,
                course=_COURSE,
                data_root=str(data_root),
                llm_mode="subscription",
                require_llm=False,
            )

        assert call_count == 1, (
            f"Backend should be called once (cache hit on 2nd run), was called {call_count} times"
        )

        # Both run reports should contain the cached insight
        md_path = data_root / "gold" / "retro-mester" / _KEY / "CQI회고보고서.md"
        md_text = md_path.read_text(encoding="utf-8")
        assert fixed_insight in md_text

    # ------------------------------------------------------------------
    # SC5: deterministic core unaffected — silver parquet byte-identical in off mode
    # ------------------------------------------------------------------

    def test_core_determinism_unaffected_by_llm_off(self, tmp_path: Path) -> None:
        """Two off-mode runs produce byte-identical Silver parquets (SC-009)."""
        import shutil

        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )

        silver = data_root / "silver" / "retro-mester" / _KEY
        parquet_a = (silver / "빈틈표.parquet").read_bytes()
        recs_a = (silver / "변경권고.parquet").read_bytes()

        # Archive current outputs and re-run
        _build_fixture_tree(data_root)  # reinstate (archive moved them)

        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            llm_mode="off",
        )

        silver2 = data_root / "silver" / "retro-mester" / _KEY
        parquet_b = (silver2 / "빈틈표.parquet").read_bytes()
        recs_b = (silver2 / "변경권고.parquet").read_bytes()

        assert parquet_a == parquet_b, "빈틈표.parquet must be byte-identical across runs"
        assert recs_a == recs_b, "변경권고.parquet must be byte-identical across runs"
