"""Quality report Markdown renderer (T042, FR-021, SC-005).

Spec 004 SC-005(b) enumerates the nine sections that
``시험품질보고서.md`` must contain, in this exact order:

  (1) 전체 분포
  (2) 메타데이터별 통계
  (3) 변별력 요약
  (4) 정답률 표
  (5) 오답 분석
  (6) 학생 성적 요약        — Phase 4 placeholder
  (7) 결시·무응답 통계
  (8) 출제 캘리브레이션 (예상 vs 실제 난이도)
  (9) 권고사항

The renderer is rule-based and deterministic: same inputs yield byte-identical
output (FR-023). No LLM call paths exist (FR-005, SC-006).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Mapping, Sequence

from paideia_shared.schemas import (
    HistogramBin,
    ItemStatistics,
    MetadataAggregate,
)

_REPORT_TITLE = "시험품질보고서"

_LABELS_OF_INTEREST: tuple[str, ...] = (
    "역변별 의심 — 출제 재검토",
    "모두 풀 수 있는 기본 문항",
    "어려운 변별 우수 문항(유지 권장)",
    "시간 부족 또는 포기형",
    "근접 distractor에 의한 변별 성공형",
    "변별 기여 적음 — 차년도 교체 검토",
    "특이사항 없음",
)


def _overall_lookup(overall_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {str(row["지표"]): row["값"] for row in overall_rows}


def _fmt_float(value: object, *, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value):.{decimals}f}"
    return str(value)


def _fmt_p(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value < 0.001:
        return f"{value:.4f}"
    return f"{value:.3f}"


def _section_header() -> str:
    return ""


def _render_overall(
    overall_rows: Sequence[Mapping[str, object]],
    histogram_bins: Sequence[HistogramBin],
) -> str:
    o = _overall_lookup(overall_rows)
    n_resp = o.get("응시자 수", 0)
    n_absent = o.get("결시자 수", 0)
    n_omit = o.get("무응답 응답 수", 0)
    mean = o.get("평균", 0.0)
    sd = o.get("표준편차", 0.0)
    median = o.get("중앙값", 0.0)
    minimum = o.get("최저", 0.0)
    maximum = o.get("최고", 0.0)
    q1 = o.get("Q1", 0.0)
    q3 = o.get("Q3", 0.0)
    pct_mean = o.get("100점환산_평균", 0.0)
    pct_sd = o.get("100점환산_표준편차", 0.0)

    lines = [
        "## (1) 전체 분포",
        "",
        f"응시자 {n_resp}명 (결시 {n_absent}명, 무응답 응답 {n_omit}건).",
        f"전체 평균은 **{_fmt_float(mean)}점** (SD {_fmt_float(sd)}), "
        f"중앙값 {_fmt_float(median)}점, 최저 {_fmt_float(minimum)} / 최고 {_fmt_float(maximum)} "
        f"(Q1 {_fmt_float(q1)} / Q3 {_fmt_float(q3)}).",
        f"100점 환산: 평균 {_fmt_float(pct_mean)}점 (SD {_fmt_float(pct_sd)}).",
        "",
        "표 1. 점수 히스토그램 (10점 단위)",
        "",
        "| 구간_시작 | 구간_끝 | 도수 | 누적 | 누적_백분율 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for b in histogram_bins:
        lines.append(
            f"| {_fmt_float(b.bin_start, decimals=1)} "
            f"| {_fmt_float(b.bin_end, decimals=1)} "
            f"| {b.count} | {b.cumulative} "
            f"| {_fmt_float(b.cumulative_pct, decimals=2)} |"
        )
    lines.append("")
    lines.append("![fig1 전체 성적 히스토그램](figs/fig1_전체성적_히스토그램.png)")
    lines.append("")
    return "\n".join(lines)


def _render_metadata(metadata_rows: Sequence[MetadataAggregate]) -> str:
    by_kind: dict[str, list[MetadataAggregate]] = defaultdict(list)
    for r in metadata_rows:
        by_kind[r.metadata_kind].append(r)

    lines = ["## (2) 메타데이터별 통계", ""]
    if not metadata_rows:
        lines.append("(메타데이터 통계 결측)")
        lines.append("")
        return "\n".join(lines)

    for kind in sorted(by_kind.keys()):
        rows = by_kind[kind]
        # Find the test kind / p-value (first non-N/A entry per group)
        test_kind = next((r.test_kind for r in rows if r.test_kind != "N/A"), "N/A")
        p_value = next(
            (r.test_p_value for r in rows if r.test_p_value is not None), None
        )
        verdict = "유의함" if (p_value is not None and p_value < 0.05) else "유의하지 않음"
        lines.append(f"### {kind}")
        lines.append("")
        lines.append(
            f"그룹간 차이 검정: **{test_kind}** (p={_fmt_p(p_value)}) — {verdict}."
        )
        lines.append("")
        lines.append("| 그룹 | n | 평균 | SD | 비고 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in rows:
            note = r.note or ""
            lines.append(
                f"| {r.metadata_value} | {r.n} "
                f"| {_fmt_float(r.mean)} | {_fmt_float(r.sd)} | {note} |"
            )
        lines.append("")

    lines.append("![fig2 메타데이터별 정답률](figs/fig2_메타데이터별_정답률.png)")
    lines.append("")
    return "\n".join(lines)


def _render_discrimination(items: Sequence[ItemStatistics]) -> str:
    negatives = [it for it in items if it.discrimination_index < 0]
    weak = [it for it in items if 0 <= it.discrimination_index < 0.20]
    strong = [it for it in items if it.discrimination_index >= 0.40]

    lines = ["## (3) 변별력 요약", ""]
    lines.append(
        f"전체 {len(items)}문항 중 변별력 < 0 (역변별) 문항 **{len(negatives)}개**, "
        f"변별력 0.00–0.20 (약함) {len(weak)}개, 변별력 ≥ 0.40 (우수) {len(strong)}개."
    )
    if negatives:
        nos = ", ".join(str(it.item_no) for it in sorted(negatives, key=lambda x: x.item_no))
        lines.append(f"역변별 의심 문항: {nos}.")
    lines.append("")
    return "\n".join(lines)


def _render_correct_rate_table(items: Sequence[ItemStatistics]) -> str:
    lines = [
        "## (4) 정답률 표",
        "",
        "| 문항 | 정답률 | 챕터 | 문제유형 | 출처 | 난이도 | 예상난이도 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for it in sorted(items, key=lambda x: x.item_no):
        lines.append(
            f"| {it.item_no} | {_fmt_float(it.correct_rate * 100, decimals=1)}% "
            f"| {it.chapter} | {it.item_type} | {it.source} "
            f"| {it.difficulty_level} | {it.expected_difficulty} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_distractor(items: Sequence[ItemStatistics]) -> str:
    label_buckets: dict[str, list[ItemStatistics]] = defaultdict(list)
    for it in items:
        label_buckets[it.distractor_label].append(it)

    lines = ["## (5) 오답 분석", ""]
    lines.append("문항별 오답 라벨 (FR-019 6 종 룰 + `특이사항 없음`).")
    lines.append("")
    lines.append("| 라벨 | 문항 수 | 해당 문항 |")
    lines.append("| --- | --- | --- |")
    for label in _LABELS_OF_INTEREST:
        bucket = label_buckets.get(label, [])
        nos = ", ".join(str(it.item_no) for it in sorted(bucket, key=lambda x: x.item_no))
        lines.append(f"| {label} | {len(bucket)} | {nos or '—'} |")
    lines.append("")
    return "\n".join(lines)


def _render_student_summary_placeholder() -> str:
    return (
        "## (6) 학생 성적 요약\n\n"
        "본 섹션의 분반 별 백분위·z-score 분포 요약은 **Phase 4 (학생 지표)** "
        "land 후 채워진다 (placeholder). 현재는 `시험분석결과.xlsx` 의 `학생성적` 시트를 "
        "함께 검토하면 된다.\n\n"
    )


def _render_absent_omit(
    overall_rows: Sequence[Mapping[str, object]],
    items: Sequence[ItemStatistics],
) -> str:
    o = _overall_lookup(overall_rows)
    n_absent = o.get("결시자 수", 0)
    n_omit_resp = o.get("무응답 응답 수", 0)
    high_omit_items = [it for it in items if it.omit_rate > 0.10]

    lines = [
        "## (7) 결시·무응답 통계",
        "",
        f"결시자 {n_absent}명 — 응시자 카운트·정답률 분모에서 제외됨.",
        f"무응답 응답 누계 {n_omit_resp}건 — 응시자 분모에 포함되며 오답으로 처리됨.",
    ]
    if high_omit_items:
        nos = ", ".join(str(it.item_no) for it in sorted(high_omit_items, key=lambda x: x.item_no))
        lines.append(
            f"무응답률 > 10% 문항 **{len(high_omit_items)}개**: {nos} (시간 부족·난이도 점검 필요)."
        )
    else:
        lines.append("무응답률 > 10% 문항 없음.")
    lines.append("")
    return "\n".join(lines)


def _render_calibration(items: Sequence[ItemStatistics]) -> str:
    by_expected: dict[str, list[ItemStatistics]] = defaultdict(list)
    for it in items:
        by_expected[it.expected_difficulty].append(it)

    lines = ["## (8) 출제 캘리브레이션 (예상 vs 실제 난이도)", ""]
    lines.append("| 예상 난이도 | 문항 수 | 평균 정답률 | 비고 |")
    lines.append("| --- | --- | --- | --- |")
    expected_order = ["쉬움", "보통", "어려움"]
    seen = set()
    for level in expected_order:
        bucket = by_expected.get(level, [])
        if not bucket:
            continue
        seen.add(level)
        avg = sum(it.correct_rate for it in bucket) / len(bucket)
        # Naive calibration heuristic — 쉬움 expected → 정답률 ≥ 0.8 정합
        if level == "쉬움" and avg < 0.80:
            note = "예상보다 어려움"
        elif level == "어려움" and avg > 0.50:
            note = "예상보다 쉬움"
        else:
            note = "정합"
        lines.append(
            f"| {level} | {len(bucket)} | {_fmt_float(avg * 100, decimals=1)}% | {note} |"
        )
    # Expected-difficulty levels not in the canonical set still surface
    for level, bucket in by_expected.items():
        if level in seen:
            continue
        avg = sum(it.correct_rate for it in bucket) / len(bucket)
        lines.append(
            f"| {level} | {len(bucket)} | {_fmt_float(avg * 100, decimals=1)}% | — |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_recommendations(items: Sequence[ItemStatistics]) -> str:
    label_counts = Counter(it.distractor_label for it in items)
    n_neg = label_counts.get("역변별 의심 — 출제 재검토", 0)
    n_too_easy = label_counts.get("모두 풀 수 있는 기본 문항", 0)
    n_replace = label_counts.get("변별 기여 적음 — 차년도 교체 검토", 0)
    n_time = label_counts.get("시간 부족 또는 포기형", 0)

    bullets: list[str] = []
    if n_neg > 0:
        bullets.append(
            f"역변별 의심 문항 {n_neg}개 — 출제 의도·정답 키 재검토 필수 (다음 학기 교체 권장)."
        )
    if n_too_easy > 0:
        bullets.append(
            f"정답률 > 95% 문항 {n_too_easy}개 — 기본 개념 확인용으로는 유지하되 변별 기여는 낮음."
        )
    if n_replace > 0:
        bullets.append(
            f"변별 기여 적음 문항 {n_replace}개 — 차년도 교체 후보로 분류."
        )
    if n_time > 0:
        bullets.append(
            f"무응답률 높은 문항 {n_time}개 — 시험 시간·문항 길이 조정 검토."
        )
    if not bullets:
        bullets.append("심각한 출제 이상 신호 없음 — 차학기 동일 출제 안 으로 안정 운영 가능.")

    lines = ["## (9) 권고사항", ""]
    for b in bullets:
        lines.append(f"- {b}")
    lines.append("")
    return "\n".join(lines)


def render_quality_report_md(
    *,
    overall_rows: Sequence[Mapping[str, object]],
    histogram_bins: Sequence[HistogramBin],
    metadata_rows: Sequence[MetadataAggregate],
    item_stats: Iterable[ItemStatistics],
    semester: str,
    course_name_kr: str,
    generated_at_utc: str,
) -> str:
    """Render the quality report Markdown (9 sections, deterministic).

    Args:
        overall_rows: Output of ``compute_overall_summary`` (list of 13
            ``{지표, 값}`` dicts).
        histogram_bins: Output of ``compute_score_histogram``.
        metadata_rows: Output of ``compute_metadata_aggregates``.
        item_stats: Output of ``compute_item_statistics`` (one
            ``ItemStatistics`` per question).
        semester: e.g. ``"2026-1"``.
        course_name_kr: e.g. ``"인체구조와기능"``.
        generated_at_utc: ISO8601 UTC timestamp pinned at the manifest.

    Returns:
        Markdown source string with a stable ``\\n`` line ending.

    Raises:
        ValueError: When ``overall_rows`` / ``item_stats`` are empty.
    """
    if not overall_rows:
        raise ValueError("render_quality_report_md: overall_rows is empty")
    items = list(item_stats)
    if not items:
        raise ValueError("render_quality_report_md: item_stats is empty")
    if not isinstance(semester, str) or not semester:
        raise ValueError("render_quality_report_md: semester must be a non-empty string")
    if not isinstance(course_name_kr, str) or not course_name_kr:
        raise ValueError(
            "render_quality_report_md: course_name_kr must be a non-empty string"
        )
    if not isinstance(generated_at_utc, str) or not generated_at_utc:
        raise ValueError(
            "render_quality_report_md: generated_at_utc must be a non-empty ISO8601 string"
        )

    parts: list[str] = [
        f"# {_REPORT_TITLE} — {course_name_kr} ({semester})",
        "",
        f"발행: {generated_at_utc}",
        "",
        _render_overall(overall_rows, histogram_bins),
        _render_metadata(metadata_rows),
        _render_discrimination(items),
        _render_correct_rate_table(items),
        _render_distractor(items),
        _render_student_summary_placeholder(),
        _render_absent_omit(overall_rows, items),
        _render_calibration(items),
        _render_recommendations(items),
    ]
    return "\n".join(parts)


__all__ = ["render_quality_report_md"]
