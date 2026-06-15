"""T037-T043 — US3 forward-contract + cold-start + audit integration tests.

RED phase: written before implementation.

Verifies:
1. Cold-start pipeline emits 차년도방향.yaml (ledger + baseline, no audit key)
   and 차년도진단문항제안.md.
2. Second run with prior_year pointing to the first run's yaml → audit.results
   present with met booleans.
3. 차년도방향.yaml is fully deterministic across identical runs.
4. Markdown report includes '내년 준비 예견' section.
5. Markdown report states no micro YoY extrapolation (FR-016 note).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEMESTER}-{_COURSE}"

_CHAPTER_A = "1장. 해부학 서론"    # structural: both segments below threshold
_CHAPTER_B = "2장. 세포와 조직"    # non-structural: only 학령기 below

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


# ---------------------------------------------------------------------------
# Fixture helpers (inline — each integration test module is self-contained)
# ---------------------------------------------------------------------------


def _combined_row(
    student_id: str,
    chapter_rates: dict[str, float],
    cluster_label: str | None = None,
) -> dict:
    has_cluster = cluster_label is not None
    row: dict = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": _SEMESTER,
        "course_slug": _COURSE,
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


def _item_row(
    item_no: int,
    chapter: str,
    expected_difficulty: str = "어려움",
    correct_rate: float = 0.3,
) -> dict:
    return {
        "item_no": item_no,
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "chapter": chapter,
        "week": None,
        "item_type": "이해",
        "difficulty_level": 3,
        "expected_difficulty": expected_difficulty,
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


def _build_fixture_tree(data_root: Path) -> None:
    """Write fixture files under data_root with structural gap scenario."""
    key = _KEY

    silver_dir = data_root / "silver" / "immersio" / key
    silver_dir.mkdir(parents=True, exist_ok=True)

    combined_rows = [
        # 학령기: both below threshold
        _combined_row("2026000001", {_CHAPTER_A: 0.35, _CHAPTER_B: 0.40}, cluster_label="전략적"),
        _combined_row("2026000002", {_CHAPTER_A: 0.40, _CHAPTER_B: 0.45}, cluster_label="전략적"),
        # 만학도: below CHAPTER_A (structural), above CHAPTER_B
        _combined_row("2026000003", {_CHAPTER_A: 0.30, _CHAPTER_B: 0.70}, cluster_label="습관중심"),
        _combined_row("2026000004", {_CHAPTER_A: 0.25, _CHAPTER_B: 0.75}, cluster_label="습관중심"),
    ]
    pd.DataFrame(combined_rows).to_parquet(
        silver_dir / "진단×시험결합.parquet", index=False
    )

    item_rows = [
        _item_row(1, _CHAPTER_A, expected_difficulty="어려움", correct_rate=0.3),
        _item_row(2, _CHAPTER_B, expected_difficulty="어려움", correct_rate=0.35),
    ]
    pd.DataFrame(item_rows).to_parquet(silver_dir / "문항통계.parquet", index=False)

    bronze = data_root / "bronze" / "retro-mester" / key
    bronze.mkdir(parents=True, exist_ok=True)

    retro_cfg = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
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
            {"week": 1, "chapter": _CHAPTER_A, "chapter_no": 1, "subtopic": None, "sections": ["1.1 인체의 조직"]},
            {"week": 2, "chapter": _CHAPTER_B, "chapter_no": 2, "subtopic": None, "sections": ["2.1 세포의 구조"]},
        ],
    }

    (bronze / "retro_config.yaml").write_text(yaml.dump(retro_cfg, allow_unicode=True), encoding="utf-8")
    (bronze / "blueprint.yaml").write_text(yaml.dump(blueprint, allow_unicode=True), encoding="utf-8")
    (bronze / "curriculum_map.yaml").write_text(yaml.dump(curriculum, allow_unicode=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper: run pipeline
# ---------------------------------------------------------------------------


def _run(
    tmp_path: Path,
    *,
    prior_yaml_path: str | None = None,
) -> Path:
    """Build fixture, run pipeline, return gold dir."""
    from retro_mester.pipeline import run_retro

    data_root = tmp_path / "data"
    if not (data_root / "silver").exists():
        _build_fixture_tree(data_root)

    code = run_retro(
        semester=_SEMESTER,
        course=_COURSE,
        data_root=str(data_root),
        llm_mode="off",
        prior_yaml_path=prior_yaml_path,
    )
    assert code == 0, f"Pipeline exited with code {code}"
    return data_root / "gold" / "retro-mester" / _KEY


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUS3ColdStart:
    """US3 cold-start: prior_yaml_path=None → yaml with ledger+baseline, no audit."""

    def test_차년도방향_yaml_exists(self, tmp_path: Path) -> None:
        """차년도방향.yaml is created in the gold dir."""
        gold = _run(tmp_path)
        assert (gold / "차년도방향.yaml").exists()

    def test_차년도진단문항제안_md_exists(self, tmp_path: Path) -> None:
        """차년도진단문항제안.md is created in the gold dir."""
        gold = _run(tmp_path)
        assert (gold / "차년도진단문항제안.md").exists()

    def test_cold_start_omits_audit(self, tmp_path: Path) -> None:
        """Cold-start yaml does NOT contain an 'audit' key."""
        gold = _run(tmp_path)
        data = yaml.safe_load((gold / "차년도방향.yaml").read_text(encoding="utf-8"))
        assert "audit" not in data

    def test_ledger_non_empty(self, tmp_path: Path) -> None:
        """Ledger list has at least one entry (covered gaps exist)."""
        gold = _run(tmp_path)
        data = yaml.safe_load((gold / "차년도방향.yaml").read_text(encoding="utf-8"))
        assert len(data.get("ledger", [])) > 0

    def test_baseline_non_empty(self, tmp_path: Path) -> None:
        """Baseline list has at least one row."""
        gold = _run(tmp_path)
        data = yaml.safe_load((gold / "차년도방향.yaml").read_text(encoding="utf-8"))
        assert len(data.get("baseline", [])) > 0

    def test_schema_version(self, tmp_path: Path) -> None:
        """schema_version is 'retro-forward/1.0'."""
        gold = _run(tmp_path)
        data = yaml.safe_load((gold / "차년도방향.yaml").read_text(encoding="utf-8"))
        assert data["schema_version"] == "retro-forward/1.0"

    def test_yaml_deterministic(self, tmp_path: Path) -> None:
        """Two identical cold-start runs produce byte-identical 차년도방향.yaml."""
        from retro_mester.pipeline import run_retro

        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)

        # Run 1
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))
        gold = data_root / "gold" / "retro-mester" / _KEY
        bytes1 = (gold / "차년도방향.yaml").read_bytes()

        # Run 2 — archive existing, re-run
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))
        # gold dir recreated fresh after archive
        bytes2 = (gold / "차년도방향.yaml").read_bytes()

        assert bytes1 == bytes2, "차년도방향.yaml must be byte-identical across runs"

    def test_md_report_has_내년_준비_예견_section(self, tmp_path: Path) -> None:
        """MD report includes '내년 준비 예견' section header (US3 T042)."""
        gold = _run(tmp_path)
        md = (gold / "CQI회고보고서.md").read_text(encoding="utf-8")
        assert "내년 준비 예견" in md

    def test_md_report_has_no_yoy_extrapolation_note(self, tmp_path: Path) -> None:
        """MD report explicitly states no micro YoY extrapolation (FR-016)."""
        gold = _run(tmp_path)
        md = (gold / "CQI회고보고서.md").read_text(encoding="utf-8")
        # Must contain some form of "연도간 외삽 없음" or "미시적 연도비교 없음"
        assert "연도간" in md or "YoY" in md or "외삽" in md

    def test_next_items_md_has_table(self, tmp_path: Path) -> None:
        """차년도진단문항제안.md contains a Markdown table."""
        gold = _run(tmp_path)
        text = (gold / "차년도진단문항제안.md").read_text(encoding="utf-8")
        assert "|" in text

    def test_next_items_md_has_생물_학습시기(self, tmp_path: Path) -> None:
        """차년도진단문항제안.md mentions '생물 최종학습 시기'."""
        gold = _run(tmp_path)
        text = (gold / "차년도진단문항제안.md").read_text(encoding="utf-8")
        assert "생물 최종학습 시기" in text


class TestUS3AuditRoundtrip:
    """US3 audit round-trip: use cold-start yaml as prior_year input."""

    def _build_data(self, tmp_path: Path) -> Path:
        """Build fixture tree and return data_root."""
        data_root = tmp_path / "data"
        _build_fixture_tree(data_root)
        return data_root

    def test_audit_results_present(self, tmp_path: Path) -> None:
        """Second run with prior_yaml_path → audit.results in yaml."""
        from retro_mester.pipeline import run_retro

        data_root = self._build_data(tmp_path)
        gold = data_root / "gold" / "retro-mester" / _KEY

        # Run 1: cold-start
        code1 = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
        )
        assert code1 == 0
        prior_yaml = gold / "차년도방향.yaml"
        assert prior_yaml.exists()

        # Copy prior yaml to a stable path before run2 archives gold dir
        import shutil
        prior_copy = tmp_path / "prior_차년도방향.yaml"
        shutil.copy(prior_yaml, prior_copy)

        # Run 2: with prior year audit
        code2 = run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            prior_yaml_path=str(prior_copy),
        )
        assert code2 == 0

        data = yaml.safe_load((gold / "차년도방향.yaml").read_text(encoding="utf-8"))
        assert "audit" in data
        assert "results" in data["audit"]
        assert len(data["audit"]["results"]) > 0

    def test_audit_results_have_met_boolean(self, tmp_path: Path) -> None:
        """Each audit result row has a boolean 'met' field."""
        import shutil

        from retro_mester.pipeline import run_retro

        data_root = self._build_data(tmp_path)
        gold = data_root / "gold" / "retro-mester" / _KEY

        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))
        prior_copy = tmp_path / "prior_차년도방향.yaml"
        shutil.copy(gold / "차년도방향.yaml", prior_copy)

        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            prior_yaml_path=str(prior_copy),
        )

        data = yaml.safe_load((gold / "차년도방향.yaml").read_text(encoding="utf-8"))
        for r in data["audit"]["results"]:
            assert "met" in r
            assert isinstance(r["met"], bool)

    def test_audit_md_report_has_효과감사_section(self, tmp_path: Path) -> None:
        """MD report includes '작년 변경 효과감사' subsection when audit present."""
        import shutil

        from retro_mester.pipeline import run_retro

        data_root = self._build_data(tmp_path)
        gold = data_root / "gold" / "retro-mester" / _KEY

        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(data_root))
        prior_copy = tmp_path / "prior_차년도방향.yaml"
        shutil.copy(gold / "차년도방향.yaml", prior_copy)

        run_retro(
            semester=_SEMESTER,
            course=_COURSE,
            data_root=str(data_root),
            prior_yaml_path=str(prior_copy),
        )

        md = (gold / "CQI회고보고서.md").read_text(encoding="utf-8")
        assert "효과감사" in md or "변경 효과" in md
