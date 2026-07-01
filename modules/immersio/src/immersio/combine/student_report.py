"""Per-student counseling sheet emitter (T067, post-closure follow-up).

silver `진단×시험결합.parquet` 60-column 입력 → 학생-단위 면담 시트
(`gold/학생별/{sid}_{name_kr}.md`) + 합본 시트 (`gold/학생별면담시트_합본.md`).

본 모듈은 spec 005 v0.1.0 closure 이후 *post-closure follow-up* 으로
land — 운영자 (학과 회의 + 면담) 의 직접 운영 가능 산출물을 silver
에서 1-step 으로 추출한다. spec 006 학생-단위 자동 라벨링 (5 라벨
🔴🟡🟢⚪🔵) 의 사전 단계로 사용 가능.

Public:
- :func:`build_student_reports(df, *, manifest_dict, gold_dir)` →
  list[Path] (학생별 .md + 합본 .md 경로 리스트)

결정성:
- 학생 정렬 student_id ascending (joiner row order inherit)
- MD 출력 LF (\\n) 고정 (Path.write_text encoding='utf-8')
- byte-identical re-run 검증 (test_byte_identical_re_run)

Korean vocabulary (8 axis 표준):
- digital_efficacy → 디지털 효능감
- motivation → 학습 동기
- time_availability → 학습 시간 가용성
- material_preference → 교재 선호도
- study_strategy → 학습 전략
- study_environment → 학습 환경
- social_learning → 사회적 학습
- feedback_seeking → 피드백 추구
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from paideia_shared.io import atomic_write
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

_AXIS_KR: dict[str, str] = {
    "digital_efficacy": "디지털 효능감",
    "motivation": "학습 동기",
    "time_availability": "학습 시간 가용성",
    "material_preference": "교재 선호도",
    "study_strategy": "학습 전략",
    "study_environment": "학습 환경",
    "social_learning": "사회적 학습",
    "feedback_seeking": "피드백 추구",
}


def _interpret_z(z: float | None, missing: bool) -> str:
    """5단계 z-score 해석 — z≥1 매우 높음 / z≥0.5 높음 / |z|<0.5 평균 /
    z≤-0.5 낮음 / z≤-1 매우 낮음."""
    if missing or z is None or pd.isna(z):
        return "—"
    if z >= 1.0:
        return f"평균 대비 매우 높음 (z={z:+.2f})"
    if z >= 0.5:
        return f"평균 대비 높음 (z={z:+.2f})"
    if z >= -0.5:
        return f"평균 수준 (z={z:+.2f})"
    if z >= -1.0:
        return f"평균 대비 낮음 (z={z:+.2f})"
    return f"평균 대비 매우 낮음 (z={z:+.2f})"


def _format_axis_table(row: pd.Series) -> str:
    lines = ["| 정량 축 | raw | z-score | 해석 |", "|---|---|---|---|"]
    for axis in STANDARD_AXIS_KEYS:
        raw = row[f"{axis}_raw"]
        z = row[f"{axis}_z"]
        miss = bool(row[f"{axis}_missing"])
        kr = _AXIS_KR[axis]
        if miss or pd.isna(raw):
            lines.append(f"| {kr} | — | — | (응답 누락) |")
        else:
            lines.append(
                f"| {kr} | {float(raw):.2f} | {float(z):+.2f} | {_interpret_z(float(z), miss)} |"
            )
    return "\n".join(lines)


def _format_exam(row: pd.Series, cohort_mean: float) -> str:
    if not row["시험응시"]:
        return "**시험 미응시 — 결시**\n"
    parts = [
        f"- 총점: **{float(row['total_score']):.1f}** "
        f"(cohort 평균: {cohort_mean:.1f}, "
        f"z={float(row['z_score']):+.2f})",
        f"- 분반 percentile: {float(row['section_percentile']):.0f}%",
        f"- cohort percentile: {float(row['cohort_percentile']):.0f}%",
    ]
    return "\n".join(parts) + "\n"


def _top_axes(row: pd.Series, manifest_top3: list[str]) -> str:
    """Top-3 강예측 축 (manifest.top3_predictor_axes) 인용."""
    if not row["진단응답"]:
        return "_진단 미응답 — Top-3 강예측 축 인용 불가._\n"
    if not manifest_top3:
        return "_cohort 회귀에서 q<0.05 통과한 axis 없음 — Top-3 인용 생략._\n"
    lines: list[str] = []
    for axis in manifest_top3:
        if bool(row[f"{axis}_missing"]):
            continue
        z = float(row[f"{axis}_z"])
        kr = _AXIS_KR.get(axis, axis)
        if z >= 0.5:
            stance = f"**상대적 강점** (z={z:+.2f}) — 면담 시 자기효능감 강화 토픽 권장."
        elif z <= -0.5:
            stance = f"**상대적 약점** (z={z:+.2f}) — 면담 시 학습 전략 보강 권장."
        else:
            stance = f"평균 수준 (z={z:+.2f}) — 표준 면담 흐름 적용."
        lines.append(f"- **{kr}** ({axis}): {stance}")
    if not lines:
        return "_Top-3 축이 모두 응답 누락._\n"
    return "\n".join(lines) + "\n"


def _student_section(
    idx: int,
    row: pd.Series,
    cohort_mean: float,
    top3: list[str],
) -> str:
    sid = str(row["student_id"])
    name = row["name_kr"] if pd.notna(row["name_kr"]) else "(이름 없음)"
    section = row["section"] if pd.notna(row["section"]) else "—"
    cluster_label = row["cluster_label"] if pd.notna(row["cluster_label"]) else "(군집 미배정)"
    cluster_id = int(row["cluster_id"]) if pd.notna(row["cluster_id"]) else "—"
    parts = [
        f"## {idx}. {name} (학번 `{sid}`)",
        "",
        "### 기본 정보",
        f"- 분반: {section} | 명단 등재: {'예' if bool(row['on_roster']) else '아니오'}",
        f"- 진단 응답: {'예' if bool(row['진단응답']) else '아니오'} "
        f"| 시험 응시: {'예' if bool(row['시험응시']) else '아니오'}",
        f"- 군집: **{cluster_label}** (cluster_id={cluster_id})",
        "",
        "### needs-map 8 정량 축",
        _format_axis_table(row),
        "",
        "### 시험 결과",
        _format_exam(row, cohort_mean),
        "### 면담 권고 (Top-3 강예측 축)",
        _top_axes(row, top3),
        "---",
        "",
    ]
    return "\n".join(parts)


def _safe_filename(sid: str, name: str | None) -> str:
    """학생별 .md 파일명 — `{sid}_{name_kr}.md` (slash/whitespace strip)."""
    nm = (name or "이름없음").strip().replace("/", "_").replace(" ", "_")
    return f"{sid}_{nm}.md"


def _consolidated_header(
    df: pd.DataFrame, manifest_dict: dict[str, Any], cohort_mean: float
) -> str:
    top3 = list(manifest_dict.get("top3_predictor_axes", []))
    semester = manifest_dict.get("semester", "—")
    course = manifest_dict.get("course_slug", "—")
    return "\n".join(
        [
            f"# 학생별 면담 시트 — {semester} {course}",
            "",
            f"- 학생 수: **{len(df)}명**",
            f"  - 진단 응답: {int(df['진단응답'].sum())}명",
            f"  - 시험 응시: {int(df['시험응시'].sum())}명",
            f"  - 둘 다: {int((df['진단응답'] & df['시험응시']).sum())}명",
            f"- cohort 시험 평균: **{cohort_mean:.1f}**"
            if not pd.isna(cohort_mean)
            else "- cohort 시험 평균: — (응시자 0명)",
            f"- ruleset_version: {manifest_dict.get('ruleset_version', '—')}",
            f"- Top-3 강예측 축 (cohort 회귀): "
            f"{', '.join(_AXIS_KR.get(a, a) for a in top3) or '(유의 축 없음)'}",
            "",
            "_학과 회의 + 학생 면담용 자동 합본._",
            "",
            "---",
            "",
        ]
    )


def build_student_reports(
    df: pd.DataFrame,
    *,
    manifest_dict: dict[str, Any],
    gold_dir: Path,
) -> list[Path]:
    """Build per-student counseling sheets + consolidated md.

    Args:
        df: Joiner output / silver round-trip DataFrame (60-column
            ``CombinedAnalysisRow`` shape). Caller is responsible for
            having validated the row schema upstream.
        manifest_dict: ``CombinedAnalysisManifest.model_dump()`` or the
            equivalent JSON payload (``json.loads(manifest_phase3.json)``).
            Must carry ``top3_predictor_axes`` + ``ruleset_version`` +
            ``semester`` + ``course_slug``.
        gold_dir: Gold output directory for this (semester, course) —
            per-student md lands under ``{gold_dir}/학생별/`` and the
            consolidated md at ``{gold_dir}/학생별면담시트_합본.md``.

    Returns:
        List of all paths land — per-student .md files + consolidated md.

    Raises:
        ValueError: If ``df`` is empty (Fail-Fast).
    """
    if df.empty:
        raise ValueError("build_student_reports: empty DataFrame")

    df_sorted = df.sort_values("student_id").reset_index(drop=True)
    top3 = list(manifest_dict.get("top3_predictor_axes", []))

    cohort_mean = (
        float(df_sorted.loc[df_sorted["시험응시"], "total_score"].mean())
        if df_sorted["시험응시"].any()
        else float("nan")
    )

    student_dir = gold_dir / "학생별"
    student_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    body_sections: list[str] = []
    for idx, row in df_sorted.iterrows():
        section = _student_section(int(idx) + 1, row, cohort_mean, top3)
        body_sections.append(section)

        # Per-student .md — owner-only (student PII: student_id + name_kr).
        sid = str(row["student_id"])
        per_student_path = student_dir / _safe_filename(sid, row.get("name_kr"))
        per_student_text = f"# {row.get('name_kr') or '이름없음'} (학번 `{sid}`)\n\n{section}"
        atomic_write(
            per_student_path,
            lambda p, _t=per_student_text: p.write_text(_t, encoding="utf-8"),
        )
        paths.append(per_student_path)

    consolidated = gold_dir / "학생별면담시트_합본.md"
    header = _consolidated_header(df_sorted, manifest_dict, cohort_mean)
    consolidated_text = header + "\n".join(body_sections)
    atomic_write(
        consolidated,
        lambda p, _t=consolidated_text: p.write_text(_t, encoding="utf-8"),
    )
    paths.append(consolidated)

    return paths


__all__ = ["build_student_reports"]
