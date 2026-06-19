"""T030 — Determinism tests for retro-mester US1 pipeline.

Two back-to-back ``run_retro`` calls on identical inputs must produce
byte-identical Silver parquet + Gold md/xlsx/pdf outputs.
``manifest_retro.json`` is explicitly excluded from the byte-identity check
because it carries ``generated_at_utc`` (a real wall-clock timestamp).

SC-009 compliance: the deterministic core is {빈틈표.parquet,
변경권고.parquet, CQI회고보고서.md, 회고분석.xlsx, CQI회고보고서.pdf}.

T024 (audit M1): alignment_flags in insight_facts must be sorted so the
LLM prompt is deterministic across runs on the same inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Fixture helpers (duplicated from test_us1_e2e.py — self-contained)
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
    """Minimal CombinedAnalysisRow-compatible dict."""
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


def _write_fixture_tree(data_root: Path) -> None:
    """Write the complete fixture file tree under ``data_root``."""
    silver_dir = data_root / "silver" / "immersio" / _KEY
    silver_dir.mkdir(parents=True, exist_ok=True)

    combined_rows = [
        _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
        _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
        _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
        _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
    ]
    pd.DataFrame(combined_rows).to_parquet(silver_dir / "진단×시험결합.parquet", index=False)
    pd.DataFrame([_item_row(1, _CHAPTER_A), _item_row(2, _CHAPTER_B)]).to_parquet(
        silver_dir / "문항통계.parquet", index=False
    )

    bronze_dir = data_root / "bronze" / "retro-mester" / _KEY
    bronze_dir.mkdir(parents=True, exist_ok=True)

    retro_cfg = {
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

    (bronze_dir / "retro_config.yaml").write_text(
        yaml.dump(retro_cfg, allow_unicode=True), encoding="utf-8"
    )
    (bronze_dir / "blueprint.yaml").write_text(
        yaml.dump(blueprint, allow_unicode=True), encoding="utf-8"
    )
    (bronze_dir / "curriculum_map.yaml").write_text(
        yaml.dump(curriculum, allow_unicode=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Fixture variant that produces two distinct alignment flags
# ---------------------------------------------------------------------------


def _write_fixture_tree_multi_flags(data_root: Path) -> None:
    """Write a fixture that yields two distinct AlignmentFlag values.

    Chapter layout (3 chapters, 10 items, 4 taught weeks):
    - _CHAPTER_A: 3 taught weeks, 3 tested items → share ~= 75%/30%
      → taught_share 0.75 - tested_share 0.30 = 0.45 > 0.10  → 과다교수-과소평가
    - _CHAPTER_B: 1 taught week,  7 tested items → share ~= 25%/70%
      → tested_share 0.70 - taught_share 0.25 = 0.45 > 0.10  → 과소교수-과다평가

    Two distinct flags → list(set(...)) is nondeterministic; sorted must fix it.
    """
    silver_dir = data_root / "silver" / "immersio" / _KEY
    silver_dir.mkdir(parents=True, exist_ok=True)

    combined_rows = [
        _combined_row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.3}),
        _combined_row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.35}),
        _combined_row("2026000003", {_CHAPTER_A: 0.45, _CHAPTER_B: 0.25}),
        _combined_row("2026000004", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.2}),
    ]
    # 3 items for CHAPTER_A, 7 for CHAPTER_B → creates flag asymmetry
    items = [_item_row(i, _CHAPTER_A) for i in range(1, 4)] + [
        _item_row(i, _CHAPTER_B) for i in range(4, 11)
    ]
    pd.DataFrame(combined_rows).to_parquet(silver_dir / "진단×시험결합.parquet", index=False)
    pd.DataFrame(items).to_parquet(silver_dir / "문항통계.parquet", index=False)

    bronze_dir = data_root / "bronze" / "retro-mester" / _KEY
    bronze_dir.mkdir(parents=True, exist_ok=True)

    retro_cfg = {
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
    # 3 weeks for CHAPTER_A, 1 week for CHAPTER_B
    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": w,
                "chapter": _CHAPTER_A,
                "chapter_no": 1,
                "subtopic": None,
                "sections": ["1.1 인체의 조직"],
            }
            for w in range(1, 4)
        ]
        + [
            {
                "week": 4,
                "chapter": _CHAPTER_B,
                "chapter_no": 2,
                "subtopic": None,
                "sections": ["2.1 세포의 구조"],
            }
        ],
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

    (bronze_dir / "retro_config.yaml").write_text(
        yaml.dump(retro_cfg, allow_unicode=True), encoding="utf-8"
    )
    (bronze_dir / "blueprint.yaml").write_text(
        yaml.dump(blueprint, allow_unicode=True), encoding="utf-8"
    )
    (bronze_dir / "curriculum_map.yaml").write_text(
        yaml.dump(curriculum, allow_unicode=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Determinism test
# ---------------------------------------------------------------------------

_DETERMINISTIC_FILES = [
    "silver/retro-mester/{key}/빈틈표.parquet",
    "silver/retro-mester/{key}/변경권고.parquet",
    "gold/retro-mester/{key}/CQI회고보고서.md",
    "gold/retro-mester/{key}/회고분석.xlsx",
    "gold/retro-mester/{key}/CQI회고보고서.pdf",
]


class TestUS1Determinism:
    """T030 (SC-009): two runs on identical inputs → byte-identical core outputs."""

    def test_byte_identical_core_outputs(self, tmp_path: Path) -> None:
        """Two ``run_retro`` calls on the same inputs produce identical core outputs.

        Strategy: run once into ``run1/data``, snapshot bytes, then run again
        into ``run2/data`` (identical fixture), compare byte strings.  The
        second run archives the silver+gold from the first run automatically.
        """
        from retro_mester.pipeline import run_retro

        # Build TWO independent data roots with identical fixtures
        root1 = tmp_path / "run1" / "data"
        root2 = tmp_path / "run2" / "data"
        _write_fixture_tree(root1)
        _write_fixture_tree(root2)

        code1 = run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(root1))
        code2 = run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(root2))

        assert code1 == 0, f"First run failed with code {code1}"
        assert code2 == 0, f"Second run failed with code {code2}"

        for template in _DETERMINISTIC_FILES:
            rel = template.format(key=_KEY)
            p1 = root1 / rel
            p2 = root2 / rel
            assert p1.exists(), f"run1 missing: {rel}"
            assert p2.exists(), f"run2 missing: {rel}"
            b1 = p1.read_bytes()
            b2 = p2.read_bytes()
            assert b1 == b2, f"Byte mismatch in {rel}: run1={len(b1)} bytes, run2={len(b2)} bytes"

    def test_manifest_excluded_from_identity(self, tmp_path: Path) -> None:
        """manifest_retro.json is not required to be byte-identical across runs.

        This test merely confirms that our two roots both produce valid manifests
        — it does NOT assert byte equality for the manifest.
        """
        from retro_mester.pipeline import run_retro

        root1 = tmp_path / "r1" / "data"
        root2 = tmp_path / "r2" / "data"
        _write_fixture_tree(root1)
        _write_fixture_tree(root2)
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(root1))
        run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(root2))

        m1 = json.loads(
            (root1 / "silver" / "retro-mester" / _KEY / "manifest_retro.json").read_text()
        )
        m2 = json.loads(
            (root2 / "silver" / "retro-mester" / _KEY / "manifest_retro.json").read_text()
        )

        # Non-timestamp fields must be identical
        for key in (
            "module_version",
            "schema_version",
            "semester",
            "course_slug",
            "thresholds",
            "counts",
            "degrade",
        ):
            assert m1[key] == m2[key], f"Manifest field '{key}' differs between runs"


class TestAlignmentFlagsSorted:
    """T024 (audit M1): insight_facts alignment_flags must be deterministically sorted.

    ``list({f.flag ...})`` iterates a set whose order is nondeterministic.
    After the fix the flags must arrive in ``sorted()`` order so the LLM
    prompt hash is stable across interpreter restarts.
    """

    def test_alignment_flags_are_sorted_in_insight_facts(self, tmp_path: Path) -> None:
        """alignment_flags in insight_facts must equal sorted(unique_flags).

        Strategy: build a fixture that produces two distinct alignment flags
        (one aligned chapter + one under-taught/over-tested chapter), then
        monkey-patch ``build_insight`` on the ``retro_mester.pipeline``
        module namespace to capture the ``facts`` dict.  Assert that
        ``alignment_flags`` list equals ``sorted(alignment_flags)``.
        """
        import retro_mester.pipeline as pipeline_mod
        from retro_mester.llm.insight import build_insight as original_build
        from retro_mester.pipeline import run_retro

        captured_facts: list[dict] = []

        def capturing_build(
            facts: dict,
            *,
            llm_mode: str,
            require_llm: bool,
            cache: object,
        ) -> tuple[str, bool]:
            captured_facts.append(dict(facts))
            return original_build(
                facts,
                llm_mode=llm_mode,
                require_llm=require_llm,
                cache=cache,
            )

        root = tmp_path / "data"
        _write_fixture_tree_multi_flags(root)

        pipeline_mod.build_insight = capturing_build  # type: ignore[attr-defined]
        try:
            code = run_retro(semester=_SEMESTER, course=_COURSE, data_root=str(root))
        finally:
            pipeline_mod.build_insight = original_build  # type: ignore[attr-defined]

        assert code == 0, f"run_retro failed with code {code}"
        assert captured_facts, "build_insight was not called — pipeline changed"

        flags = captured_facts[0]["alignment_flags"]
        assert len(flags) >= 2, (
            f"Fixture must yield at least 2 distinct flags to test order; got {flags!r}"
        )
        assert flags == sorted(flags), (
            f"alignment_flags must be sorted; got {flags!r}, expected {sorted(flags)!r}"
        )
