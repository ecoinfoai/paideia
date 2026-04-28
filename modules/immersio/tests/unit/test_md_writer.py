"""T042 — RED tests for `report/md_writer.py` (FR-021, SC-005).

`render_quality_report_md(...)` consumes the analysis primitives produced by
``analysis/{overall_summary,histogram,metadata_stats,discrimination,
item_stats,distractor_labels}.py`` and emits a deterministic Markdown
document containing the nine sections enumerated in spec.md SC-005(b):

  (1) 전체 분포
  (2) 메타데이터별 통계
  (3) 변별력 요약
  (4) 정답률 표
  (5) 오답 분석
  (6) 학생 성적 요약
  (7) 결시·무응답 통계
  (8) 출제 캘리브레이션 (예상 vs 실제 난이도)
  (9) 권고사항

The renderer is deterministic — same inputs → byte-identical Markdown.
"""

from __future__ import annotations

import pytest

from paideia_shared.schemas import (
    HistogramBin,
    ItemStatistics,
    MetadataAggregate,
)

from immersio.report.md_writer import render_quality_report_md


def _stub_overall() -> list[dict[str, object]]:
    return [
        {"지표": "응시자 수", "값": 184},
        {"지표": "결시자 수", "값": 19},
        {"지표": "무응답 응답 수", "값": 12},
        {"지표": "만점", "값": 220.0},
        {"지표": "평균", "값": 125.35},
        {"지표": "표준편차", "값": 39.55},
        {"지표": "중앙값", "값": 127.5},
        {"지표": "최저", "값": 25.0},
        {"지표": "최고", "값": 195.0},
        {"지표": "Q1", "값": 95.0},
        {"지표": "Q3", "값": 156.25},
        {"지표": "100점환산_평균", "값": 56.98},
        {"지표": "100점환산_표준편차", "값": 17.98},
    ]


def _stub_histogram() -> list[HistogramBin]:
    return [
        HistogramBin(bin_start=0.0, bin_end=10.0, count=2, cumulative=2, cumulative_pct=1.09),
        HistogramBin(bin_start=10.0, bin_end=20.0, count=5, cumulative=7, cumulative_pct=3.80),
        HistogramBin(bin_start=20.0, bin_end=30.0, count=15, cumulative=22, cumulative_pct=11.96),
        HistogramBin(bin_start=30.0, bin_end=40.0, count=30, cumulative=52, cumulative_pct=28.26),
        HistogramBin(bin_start=40.0, bin_end=50.0, count=40, cumulative=92, cumulative_pct=50.0),
        HistogramBin(bin_start=50.0, bin_end=60.0, count=42, cumulative=134, cumulative_pct=72.83),
        HistogramBin(bin_start=60.0, bin_end=70.0, count=30, cumulative=164, cumulative_pct=89.13),
        HistogramBin(bin_start=70.0, bin_end=80.0, count=14, cumulative=178, cumulative_pct=96.74),
        HistogramBin(bin_start=80.0, bin_end=90.0, count=5, cumulative=183, cumulative_pct=99.46),
        HistogramBin(bin_start=90.0, bin_end=100.0, count=1, cumulative=184, cumulative_pct=100.0),
    ]


def _stub_metadata() -> list[MetadataAggregate]:
    return [
        MetadataAggregate(
            metadata_kind="분반",
            metadata_value="A",
            n=46,
            mean=128.5,
            sd=38.0,
            test_kind="ANOVA",
            test_p_value=0.012,
            levene_p_value=0.21,
            note=None,
        ),
        MetadataAggregate(
            metadata_kind="분반",
            metadata_value="B",
            n=46,
            mean=120.0,
            sd=40.0,
            test_kind="ANOVA",
            test_p_value=0.012,
            levene_p_value=0.21,
            note=None,
        ),
        MetadataAggregate(
            metadata_kind="고교생물_이수",
            metadata_value="이수",
            n=70,
            mean=132.1,
            sd=37.0,
            test_kind="Welch t-test",
            test_p_value=0.001,
            levene_p_value=None,
            note=None,
        ),
        MetadataAggregate(
            metadata_kind="고교생물_이수",
            metadata_value="미이수",
            n=114,
            mean=121.0,
            sd=39.5,
            test_kind="Welch t-test",
            test_p_value=0.001,
            levene_p_value=None,
            note=None,
        ),
    ]


def _stub_item(
    *,
    item_no: int,
    correct_rate: float,
    discrimination: float,
    label: str,
    chapter: str = "1장. 서론",
    item_type: str = "지식축적",
    difficulty_level: int = 2,
    expected_difficulty: str = "보통",
    source: str = "교과서",
    omit_rate: float = 0.0,
) -> ItemStatistics:
    # Build a valid option_distribution that respects V3 (sum ≤ 1.0).
    remaining = max(0.0, 1.0 - correct_rate - omit_rate)
    top_distractor_rate = min(0.20, remaining)
    other = max(0.0, remaining - top_distractor_rate)
    o3 = other / 3
    return ItemStatistics(
        item_no=item_no,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=1,
        item_type=item_type,
        difficulty_level=difficulty_level,
        expected_difficulty=expected_difficulty,
        source=source,
        correct_answer=1,
        n_responders=184,
        n_correct=int(184 * correct_rate),
        n_omit=int(184 * omit_rate),
        correct_rate=correct_rate,
        omit_rate=omit_rate,
        discrimination_index=discrimination,
        point_biserial=discrimination,
        top_distractor_no=2,
        top_distractor_rate=top_distractor_rate,
        is_top_distractor_adjacent=True,
        option_distribution={1: correct_rate, 2: top_distractor_rate, 3: o3, 4: o3, 5: o3},
        distractor_label=label,
    )


def _stub_items() -> list[ItemStatistics]:
    return [
        _stub_item(item_no=1, correct_rate=0.75, discrimination=0.35, label="특이사항 없음"),
        _stub_item(
            item_no=2,
            correct_rate=0.40,
            discrimination=-0.05,
            label="역변별 의심 — 출제 재검토",
        ),
        _stub_item(
            item_no=3,
            correct_rate=0.97,
            discrimination=0.05,
            label="모두 풀 수 있는 기본 문항",
        ),
        _stub_item(
            item_no=4,
            correct_rate=0.25,
            discrimination=0.32,
            label="어려운 변별 우수 문항(유지 권장)",
            difficulty_level=3,
            expected_difficulty="어려움",
        ),
    ]


SECTION_HEADERS = (
    "## (1) 전체 분포",
    "## (2) 메타데이터별 통계",
    "## (3) 변별력 요약",
    "## (4) 정답률 표",
    "## (5) 오답 분석",
    "## (6) 학생 성적 요약",
    "## (7) 결시·무응답 통계",
    "## (8) 출제 캘리브레이션",
    "## (9) 권고사항",
)


@pytest.fixture
def md_text() -> str:
    return render_quality_report_md(
        overall_rows=_stub_overall(),
        histogram_bins=_stub_histogram(),
        metadata_rows=_stub_metadata(),
        item_stats=_stub_items(),
        semester="2026-1",
        course_name_kr="인체구조와기능",
        generated_at_utc="2026-04-29T00:00:00Z",
    )


def test_all_nine_section_headers_present(md_text: str) -> None:
    for header in SECTION_HEADERS:
        assert header in md_text, f"missing section header: {header!r}"


def test_section_order_is_canonical(md_text: str) -> None:
    indices = [md_text.index(h) for h in SECTION_HEADERS]
    assert indices == sorted(indices), "sections must appear in (1)..(9) order"


def test_overall_section_quotes_mean_and_sd(md_text: str) -> None:
    section = md_text.split("## (2)")[0]
    assert "125.35" in section
    assert "39.55" in section
    assert "184" in section


def test_metadata_section_reports_test_kind_and_p(md_text: str) -> None:
    section = md_text.split("## (2)")[1].split("## (3)")[0]
    assert "ANOVA" in section
    assert "Welch t-test" in section
    # p-values appear in scientific or fixed format with at least 3 decimals
    assert "0.012" in section or "0.0120" in section
    assert "0.001" in section or "0.0010" in section


def test_discrimination_section_lists_negative_items(md_text: str) -> None:
    section = md_text.split("## (3)")[1].split("## (4)")[0]
    # item_no=2 has discrimination=-0.05 → must be cited
    assert "2" in section
    assert "변별력" in section


def test_distractor_section_lists_six_label_buckets(md_text: str) -> None:
    section = md_text.split("## (5)")[1].split("## (6)")[0]
    # at least the labels actually present in the fixture must show up
    assert "역변별 의심 — 출제 재검토" in section
    assert "모두 풀 수 있는 기본 문항" in section
    assert "어려운 변별 우수 문항(유지 권장)" in section


def test_student_summary_section_marks_phase4_placeholder(md_text: str) -> None:
    section = md_text.split("## (6)")[1].split("## (7)")[0]
    # Phase 4 placeholder (per dispatch instructions) — `학생성적` 시트는 Phase 4
    # 책임이라는 사실을 보고서가 명시해야 함.
    assert "Phase 4" in section or "후속" in section or "placeholder" in section.lower()


def test_absent_omit_section_has_explicit_counts(md_text: str) -> None:
    section = md_text.split("## (7)")[1].split("## (8)")[0]
    assert "19" in section  # n_absent
    assert "12" in section  # n_omit


def test_calibration_section_compares_expected_vs_actual(md_text: str) -> None:
    section = md_text.split("## (8)")[1].split("## (9)")[0]
    # per-difficulty bucket should be cited
    assert "보통" in section or "어려움" in section


def test_recommendation_section_present(md_text: str) -> None:
    section = md_text.split("## (9)")[1]
    assert section.strip(), "recommendation section must not be empty"


def test_no_llm_free_text(md_text: str) -> None:
    # The renderer is rule-based; no llm coments / disclaimers should leak in
    forbidden = ["GPT", "ChatGPT", "Claude", "OpenAI", "Anthropic"]
    for token in forbidden:
        assert token not in md_text


def test_render_is_deterministic() -> None:
    a = render_quality_report_md(
        overall_rows=_stub_overall(),
        histogram_bins=_stub_histogram(),
        metadata_rows=_stub_metadata(),
        item_stats=_stub_items(),
        semester="2026-1",
        course_name_kr="인체구조와기능",
        generated_at_utc="2026-04-29T00:00:00Z",
    )
    b = render_quality_report_md(
        overall_rows=_stub_overall(),
        histogram_bins=_stub_histogram(),
        metadata_rows=_stub_metadata(),
        item_stats=_stub_items(),
        semester="2026-1",
        course_name_kr="인체구조와기능",
        generated_at_utc="2026-04-29T00:00:00Z",
    )
    assert a == b
