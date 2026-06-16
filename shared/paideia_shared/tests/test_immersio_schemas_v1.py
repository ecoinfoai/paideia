"""Contract tests for the 6 immersio Phase 1+2 schemas (spec 004, T012).

Each schema has:
- one positive case (canonical valid instance), and
- one negative case per validator declared in data-model.md.

Validators referenced (data-model.md sections):
- §1 ItemStatistics: V1 (n_correct ≤ n_responders),
                     V2 (n_omit ≤ n_responders),
                     V3 (option_distribution sum ≤ 1.0001).
- §2 StudentExamMetrics: V1 (absent_implies_no_scores),
                         V2 (percentile_consistency).
- §3 MetadataAggregate: no model-validator; positive case + Literal coverage.
- §4 HistogramBin: V1 (bin_start < bin_end).
- §5 LegacyDiffEntry: V1 (difference_only_for_numeric).
- §6 ImmersioPhase1Manifest: V1 (legacy_diff_diff_cells ≤ legacy_diff_total_cells).
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    HistogramBin,
    ImmersioPhase1Manifest,
    ItemStatistics,
    LegacyDiffEntry,
    MetadataAggregate,
    StudentExamMetrics,
)
from pydantic import ValidationError

# =====================================================================
# §1 ItemStatistics
# =====================================================================


def _item_stats_kwargs(**overrides) -> dict:
    base = dict(
        item_no=1,
        semester="2026-1",
        course_slug="anatomy",
        chapter="1장. 서론",
        week=1,
        item_type="지식축적",
        difficulty_level=3,
        expected_difficulty="보통",
        source="형성평가",
        correct_answer=2,
        n_responders=180,
        n_correct=150,
        n_omit=4,
        correct_rate=150 / 180,
        omit_rate=4 / 180,
        discrimination_index=0.42,
        point_biserial=0.31,
        top_distractor_no=3,
        top_distractor_rate=0.12,
        is_top_distractor_adjacent=True,
        option_distribution={1: 0.05, 2: 0.83, 3: 0.06, 4: 0.04, 5: 0.02},
        distractor_label="어려운 변별 우수 문항(유지 권장)",
    )
    base.update(overrides)
    return base


def test_item_statistics_positive() -> None:
    obj = ItemStatistics(**_item_stats_kwargs())
    assert obj.item_no == 1
    assert obj.discrimination_index == pytest.approx(0.42)


def test_item_statistics_v1_n_correct_exceeds_responders() -> None:
    with pytest.raises(ValidationError, match="V1"):
        ItemStatistics(**_item_stats_kwargs(n_correct=200, n_responders=180))


def test_item_statistics_v2_n_omit_exceeds_responders() -> None:
    with pytest.raises(ValidationError, match="V2"):
        ItemStatistics(**_item_stats_kwargs(n_omit=200, n_responders=180))


def test_item_statistics_v3_option_distribution_sum_exceeds_one() -> None:
    bad = {1: 0.4, 2: 0.4, 3: 0.4, 4: 0.0, 5: 0.0}  # sum = 1.2
    with pytest.raises(ValidationError, match="V3"):
        ItemStatistics(**_item_stats_kwargs(option_distribution=bad))


# =====================================================================
# §2 StudentExamMetrics
# =====================================================================


def _student_kwargs(**overrides) -> dict:
    base = dict(
        student_id="2026194001",
        name_kr="김아무",
        section="A",
        semester="2026-1",
        course_slug="anatomy",
        exam_taken=True,
        total_score=132.0,
        score_percent=75.0,
        section_percentile=68.5,
        cohort_percentile=70.1,
        z_score=0.8,
    )
    base.update(overrides)
    return base


def test_student_exam_metrics_positive() -> None:
    obj = StudentExamMetrics(**_student_kwargs())
    assert obj.exam_taken is True
    assert obj.total_score == pytest.approx(132.0)


def test_student_exam_metrics_v1_absent_with_score() -> None:
    bad = _student_kwargs(exam_taken=False)  # 점수 필드는 그대로
    with pytest.raises(ValidationError, match="V1"):
        StudentExamMetrics(**bad)


def test_student_exam_metrics_v1_absent_clean() -> None:
    obj = StudentExamMetrics(
        **_student_kwargs(
            exam_taken=False,
            total_score=None,
            score_percent=None,
            section_percentile=None,
            cohort_percentile=None,
            z_score=None,
        )
    )
    assert obj.exam_taken is False


def test_student_exam_metrics_v2_score_without_percentile() -> None:
    with pytest.raises(ValidationError, match="V2"):
        StudentExamMetrics(**_student_kwargs(section_percentile=None))


# =====================================================================
# §3 MetadataAggregate
# =====================================================================


def test_metadata_aggregate_positive_section_anova() -> None:
    obj = MetadataAggregate(
        metadata_kind="분반",
        metadata_value="A반",
        n=46,
        mean=125.3,
        sd=39.5,
        test_kind="ANOVA",
        test_p_value=0.012,
        levene_p_value=0.42,
    )
    assert obj.metadata_kind == "분반"
    assert obj.test_kind == "ANOVA"


def test_metadata_aggregate_invalid_metadata_kind() -> None:
    with pytest.raises(ValidationError):
        MetadataAggregate(
            metadata_kind="없는메타",  # type: ignore[arg-type]
            metadata_value="X",
            n=10,
            test_kind="N/A",
        )


def test_metadata_aggregate_invalid_test_kind() -> None:
    with pytest.raises(ValidationError):
        MetadataAggregate(
            metadata_kind="분반",
            metadata_value="A반",
            n=10,
            test_kind="t-test",  # type: ignore[arg-type]
        )


# =====================================================================
# §4 HistogramBin
# =====================================================================


def test_histogram_bin_positive() -> None:
    obj = HistogramBin(
        bin_start=120.0,
        bin_end=130.0,
        count=24,
        cumulative=85,
        cumulative_pct=46.2,
    )
    assert obj.bin_start == 120.0
    assert obj.bin_end == 130.0


def test_histogram_bin_v1_start_eq_end() -> None:
    with pytest.raises(ValidationError, match="V1"):
        HistogramBin(
            bin_start=130.0,
            bin_end=130.0,
            count=0,
            cumulative=0,
            cumulative_pct=0.0,
        )


def test_histogram_bin_v1_start_gt_end() -> None:
    with pytest.raises(ValidationError, match="V1"):
        HistogramBin(
            bin_start=140.0,
            bin_end=130.0,
            count=0,
            cumulative=0,
            cumulative_pct=0.0,
        )


# =====================================================================
# §5 LegacyDiffEntry
# =====================================================================


def test_legacy_diff_entry_positive_numeric() -> None:
    obj = LegacyDiffEntry(
        sheet_name="4_정답률",
        cell_address="C5",
        cell_kind="numeric",
        legacy_value=0.733,
        immersio_value=0.731,
        difference=-0.002,
        reason_estimate="결시 분모 포함 의심",
        decision="immersio_채택",
    )
    assert obj.cell_kind == "numeric"
    assert obj.difference == pytest.approx(-0.002)


def test_legacy_diff_entry_positive_text() -> None:
    obj = LegacyDiffEntry(
        sheet_name="2_메타데이터통계",
        cell_address="A1",
        cell_kind="text",
        legacy_value="분반별 평균",
        immersio_value="분반별 평균(±SD)",
        difference=None,
        reason_estimate="라벨 표기 불일치",
        decision="immersio_채택",
    )
    assert obj.cell_kind == "text"
    assert obj.difference is None


def test_legacy_diff_entry_v1_numeric_without_difference() -> None:
    with pytest.raises(ValidationError, match="V1"):
        LegacyDiffEntry(
            sheet_name="4_정답률",
            cell_address="C5",
            cell_kind="numeric",
            legacy_value=0.5,
            immersio_value=0.6,
            difference=None,  # 위배
            reason_estimate="x",
            decision="immersio_채택",
        )


def test_legacy_diff_entry_v1_text_with_difference() -> None:
    with pytest.raises(ValidationError, match="V1"):
        LegacyDiffEntry(
            sheet_name="2_메타데이터통계",
            cell_address="A1",
            cell_kind="text",
            legacy_value="X",
            immersio_value="Y",
            difference=0.5,  # 위배
            reason_estimate="x",
            decision="immersio_채택",
        )


# =====================================================================
# §6 ImmersioPhase1Manifest
# =====================================================================


def _manifest_kwargs(**overrides) -> dict:
    base = dict(
        schema_version="1.0.0",
        semester="2026-1",
        course_slug="anatomy",
        generated_at_utc="2026-04-28T00:00:42Z",
        exam_item_yaml_sha256="0" * 64,
        omr_xls_sha256_list=["a" * 64, "b" * 64],
        attendance_sha256="c" * 64,
        needs_map_silver_sha256=None,
        run_seed=42,
        ruleset_version="1.0.0",
        total_items=44,
        total_responders=180,
        total_absent=4,
        total_omit_responses=12,
        silver_outputs={"item_stats": "silver/2026-1-anatomy/문항통계.parquet"},
        gold_outputs={"xlsx": "gold/2026-1-anatomy/시험분석결과.xlsx"},
        legacy_diff_total_cells=300,
        legacy_diff_diff_cells=12,
        legacy_diff_immersio_chose_count=10,
        notes=["needs-map silver 부재 — 관심 챕터 컬럼 N/A 처리"],
    )
    base.update(overrides)
    return base


def test_immersio_phase1_manifest_positive() -> None:
    obj = ImmersioPhase1Manifest(**_manifest_kwargs())
    assert obj.schema_version == "1.0.0"
    assert obj.legacy_diff_diff_cells == 12


def test_immersio_phase1_manifest_v1_diff_exceeds_total() -> None:
    with pytest.raises(ValidationError, match="V1"):
        ImmersioPhase1Manifest(
            **_manifest_kwargs(
                legacy_diff_total_cells=10,
                legacy_diff_diff_cells=20,
            )
        )


def test_immersio_phase1_manifest_invalid_schema_version() -> None:
    with pytest.raises(ValidationError):
        ImmersioPhase1Manifest(**_manifest_kwargs(schema_version="2.0.0"))
