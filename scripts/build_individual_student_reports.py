"""학생별 중간고사 보고서 — 학생 전달용 + 교수자 보관용 + 이메일_발송용.

사용자 명시 (2026-04-30 / 2026-05-01):
1. 보고서 두 종류:
   - 교수자 보관용 (현행 형식 유지, 그림 옆 안내 문구 2건만 삭제)
   - 학생 전달용 (제목/헤더/시험결과 요약 단순화)
2. 그림 정책:
   - radar chart: 챕터별 + 주차별 (파란 실선 cohort + 빨간 실선 학생)
   - bar chart: 예상 난이도(쉬움/보통/어려움 = 상중하 순) / 문제 유형 / 출처 / 객관 난이도
   - 챕터·주차는 radar 로만 (bar 생산 X)
3. "객관 난이도" 1/2/3 → 쉬움/보통/어려움 라벨 (양쪽 보고서)
4. 그림 옆 안내 문구 ("파란 실선 = ...", "파란 막대 = ...") 양쪽 보고서에서 삭제
5. 모든 시험문제 5점

폴더 구조:
- data/gold/immersio/{semester}-{course_slug}/
  - 학생 전달용/{학번}_{이름}/
      - {학번}_{이름}.md
      - {학번}_{이름}.pdf
      - figs_{학번}_{이름}/{...png}
  - 교수자 보관용/{학번}_{이름}/
      - 보고서.md
      - 보고서.pdf
      - figs/{...png}
  - 이메일_발송용/{학번}_{이름}.pdf  (학생 전달용 PDF 복사 + 중복/개수 검증)

학년도/학기/교과목명 source-of-truth (하드코딩 없음):
- semester ("2026-1") → 학년도/학기 split (학생 전달용 제목)
- mapping yaml metadata.course_name_kr → 교과목명
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

REPO = Path("/home/kjeong/localgit/paideia")
BRONZE_EXAM_ROOT = REPO / "data/bronze/시험성적"
SECTIONS = ("A", "B", "C", "D")
POINTS_PER_ITEM = 5.0  # 사용자 명시

# Korean font setup (NixOS / Gentoo / 일반 distro 대응 + fc-match fallback)
_NANUM: str | None = None
for cand in (
    "/run/current-system/sw/share/fonts/nanum/NanumGothic.ttf",
    "/usr/share/fonts/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
):
    if Path(cand).exists():
        _NANUM = cand
        break
if _NANUM is None:
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "NanumGothic"],
            capture_output=True, text=True, timeout=5,
        )
        c = result.stdout.strip()
        if c and Path(c).exists() and "Nanum" in c:
            _NANUM = c
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
if _NANUM is None:
    for p in Path("/nix/store").glob("*/share/fonts/NanumGothic.ttf"):
        _NANUM = str(p)
        break
if _NANUM:
    fm.fontManager.addfont(_NANUM)
    plt.rcParams["font.family"] = "NanumGothic"
    print(f"[font] NanumGothic land: {_NANUM}")
else:
    print("[font] WARN — NanumGothic not found.", file=sys.stderr)
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150


# --- semester / course parsing ----------------------------------------------

def split_semester(semester: str) -> tuple[str, str]:
    """`2026-1` → (`2026`, `1`). 하드코딩 없이 입력값에서 split."""
    parts = semester.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"split_semester: expected 'YYYY-N', got {semester!r}")
    return parts[0], parts[1]


def get_course_name_kr(mapping_path: Path, course_slug: str) -> str:
    """mapping yaml `metadata.course_name_kr` 추출 — 하드코딩 우회."""
    data = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"get_course_name_kr: expected mapping in {mapping_path}")
    md = data.get("metadata") or {}
    name = md.get("course_name_kr")
    if not name:
        raise ValueError(
            f"get_course_name_kr: metadata.course_name_kr 가 {mapping_path} 에 없음 — "
            f"매핑 yaml 에 명시 필요"
        )
    return str(name).strip()


# --- bronze OX parsers ------------------------------------------------------

def _normalize_sid(raw: object) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        return f"20{s}"
    if len(s) == 10 and s.isdigit():
        return s
    return None


def parse_ox_xls(
    path: Path, section: str, n_items: int, course_name_kr: str,
) -> pd.DataFrame:
    """학생당 3 row (정답/표기/결과) → DataFrame[student_id, item_no, correct]."""
    raw = pd.read_excel(path, sheet_name="Sheet1", dtype=object, header=None)
    rows: list[dict] = []
    n_rows = len(raw)
    i = 2
    while i < n_rows:
        col0 = raw.iat[i, 0]
        if pd.isna(col0):
            i += 1
            continue
        try:
            int(col0)
        except (ValueError, TypeError):
            i += 1
            continue
        sid_raw = raw.iat[i, 2]
        name_raw = raw.iat[i, 3]
        sid = _normalize_sid(sid_raw)
        if sid is None:
            i += 1
            continue
        if i + 2 >= n_rows:
            break
        result_row = raw.iloc[i + 2]
        if str(result_row.iat[8]).strip() != "결과":
            i += 3
            continue
        for it in range(1, n_items + 1):
            col_idx = 8 + it
            ox = result_row.iat[col_idx] if col_idx < raw.shape[1] else None
            if pd.isna(ox):
                continue
            ox_s = str(ox).strip().upper()
            correct = 1 if ox_s == "O" else 0 if ox_s == "X" else None
            if correct is None:
                continue
            rows.append({
                "student_id": sid,
                "name_kr": str(name_raw) if pd.notna(name_raw) else "",
                "section": section,
                "item_no": it,
                "correct": correct,
            })
        i += 3
    return pd.DataFrame(rows)


def parse_exam_meta(path: Path) -> pd.DataFrame:
    items = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for it in items:
        rows.append({
            "item_no": int(it["번호"]),
            "chapter": str(it.get("챕터", "")).strip(),
            "week": int(it.get("주차", 0)) if it.get("주차") is not None else None,
            "question_type": str(it.get("문제유형", "")).strip(),
            "difficulty": int(it.get("난이도", 0)) if it.get("난이도") is not None else None,
            "source": str(it.get("출처", "")).strip(),
            "expected_difficulty": str(it.get("예상_난이도", "")).strip(),
        })
    return pd.DataFrame(rows).sort_values("item_no").reset_index(drop=True)


def cohort_mean_by(merged: pd.DataFrame, meta_col: str) -> pd.DataFrame:
    return (
        merged.groupby(meta_col)
        .agg(mean_score=("score", "mean"), n_responses=("score", "count"))
        .reset_index()
    )


def student_mean_by(merged: pd.DataFrame, sid: str, meta_col: str) -> pd.DataFrame:
    sub = merged[merged["student_id"] == sid]
    return (
        sub.groupby(meta_col)
        .agg(mean_score=("score", "mean"), n_responses=("score", "count"))
        .reset_index()
    )


# --- chart rendering --------------------------------------------------------

def _render_radar_generic(
    cohort: pd.DataFrame,
    student: pd.DataFrame,
    meta_col: str,
    title: str,
    out: Path,
    sort_key=None,
) -> None:
    cats_raw = cohort[meta_col].dropna().unique().tolist()
    cats = sorted(cats_raw, key=sort_key) if sort_key else sorted(cats_raw)
    n = len(cats)
    if n < 3:
        return
    cohort_map = dict(zip(cohort[meta_col], cohort["mean_score"]))
    student_map = dict(zip(student[meta_col], student["mean_score"]))
    cohort_vals = [cohort_map.get(c, 0.0) for c in cats]
    student_vals = [student_map.get(c, 0.0) for c in cats]
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    cohort_vals_c = cohort_vals + [cohort_vals[0]]
    student_vals_c = student_vals + [student_vals[0]]
    angles_c = angles + [angles[0]]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"projection": "polar"})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels([str(c) for c in cats], size=10)
    ax.set_ylim(0, 5.0)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], size=8)
    ax.plot(angles_c, cohort_vals_c, color="blue",
            linewidth=2, label="전체 학생 평균")
    ax.plot(angles_c, student_vals_c, color="red",
            linewidth=2, label="해당 학생")
    ax.fill(angles_c, student_vals_c, color="red", alpha=0.15)
    ax.set_title(title, pad=20, size=12)
    ax.legend(loc="lower right", bbox_to_anchor=(1.25, -0.05))
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="png", dpi=150, metadata={"Software": "paideia"})
    plt.close(fig)


def render_radar_chapter(cohort, student, out: Path) -> None:
    _render_radar_generic(
        cohort, student, "chapter",
        "챕터별 평균 점수 (5점 만점)", out,
    )


def render_radar_week(cohort, student, out: Path) -> None:
    _render_radar_generic(
        cohort, student, "week",
        "주차별 평균 점수 (5점 만점)", out,
        sort_key=lambda x: int(x) if pd.notna(x) else 0,
    )


_META_KIND_LABEL = {
    "expected_difficulty": "예상 난이도",
    "question_type": "문제 유형",
    "source": "문제 출처",
    "difficulty": "객관 난이도",
}

_CATEGORY_ORDER: dict[str, list[Any] | None] = {
    "expected_difficulty": ["쉬움", "보통", "어려움"],  # 상중하
    "question_type": None,
    "source": ["교과서", "형성평가", "퀴즈"],
    "difficulty": [1, 2, 3],  # internal value order (쉬움→보통→어려움)
}

# 사용자 명시 (2026-05-01): 객관 난이도 1/2/3 → 쉬움/보통/어려움 라벨.
_CATEGORY_LABEL_MAP: dict[str, dict[Any, str]] = {
    "difficulty": {1: "쉬움", 2: "보통", 3: "어려움"},
}


def render_bar_meta(
    cohort: pd.DataFrame,
    student: pd.DataFrame,
    meta_col: str,
    out: Path,
) -> None:
    order = _CATEGORY_ORDER.get(meta_col)
    cohort_map = dict(zip(cohort[meta_col], cohort["mean_score"]))
    student_map = dict(zip(student[meta_col], student["mean_score"]))
    if order is not None:
        cats = [c for c in order if c in cohort_map]
    else:
        cats = sorted(cohort_map.keys())
    if not cats:
        return
    cohort_vals = [cohort_map.get(c, 0.0) for c in cats]
    student_vals = [student_map.get(c, 0.0) for c in cats]

    label_map = _CATEGORY_LABEL_MAP.get(meta_col, {})
    tick_labels = [str(label_map.get(c, c)) for c in cats]

    x = np.arange(len(cats))
    w = 0.35
    fig, ax = plt.subplots(figsize=(max(6, len(cats) * 1.2), 5))
    ax.bar(x - w / 2, cohort_vals, w, color="blue", label="전체 학생 평균")
    ax.bar(x + w / 2, student_vals, w, color="red", label="해당 학생")
    ax.set_xticks(x)
    ax.set_xticklabels(tick_labels, rotation=15, ha="right", size=10)
    ax.set_ylim(0, 5.0)
    ax.set_ylabel("평균 점수 (5점 만점)")
    label = _META_KIND_LABEL.get(meta_col, meta_col)
    ax.set_title(f"{label}별 평균 점수", size=12)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="png", dpi=150, metadata={"Software": "paideia"})
    plt.close(fig)


# --- needs-map axis vocabulary (교수자 보관용 §4) ----------------------------

_AXIS_KR = {
    "digital_efficacy": "디지털 효능감",
    "motivation": "학습 동기",
    "time_availability": "학습 시간 가용성",
    "material_preference": "교재 선호도",
    "study_strategy": "학습 전략",
    "study_environment": "학습 환경",
    "social_learning": "사회적 학습",
    "feedback_seeking": "피드백 추구",
}


def _interpret_z(z: float) -> str:
    if z >= 1.0:
        return f"평균 대비 매우 높음 (z={z:+.2f})"
    if z >= 0.5:
        return f"평균 대비 높음 (z={z:+.2f})"
    if z >= -0.5:
        return f"평균 수준 (z={z:+.2f})"
    if z >= -1.0:
        return f"평균 대비 낮음 (z={z:+.2f})"
    return f"평균 대비 매우 낮음 (z={z:+.2f})"


# --- md builders ------------------------------------------------------------

def _radar_block(figs_subdir_name: str) -> list[str]:
    """Radar 섹션 — 안내 문구 삭제 (양쪽 보고서 공통)."""
    return [
        "## 2. 챕터·주차별 평균 점수 (Radar)",
        "",
        "### 챕터별 평균 점수",
        "",
        f"![챕터별 평균 점수]({figs_subdir_name}/radar_chapter.png)",
        "",
        "### 주차별 평균 점수",
        "",
        f"![주차별 평균 점수]({figs_subdir_name}/radar_week.png)",
        "",
    ]


def _bar_block(figs_subdir_name: str) -> list[str]:
    """Bar 섹션 — 안내 문구 삭제 (양쪽 보고서 공통)."""
    return [
        "## 3. 문제 메타데이터별 평균 점수 (Bar)",
        "",
        "### 예상 난이도별 평균 점수",
        "",
        f"![예상 난이도별 평균 점수]({figs_subdir_name}/bar_expected_difficulty.png)",
        "",
        "### 문제 유형별 평균 점수",
        "",
        f"![문제 유형별 평균 점수]({figs_subdir_name}/bar_question_type.png)",
        "",
        "### 문제 출처별 평균 점수",
        "",
        f"![문제 출처별 평균 점수]({figs_subdir_name}/bar_source.png)",
        "",
        "### 객관 난이도별 평균 점수",
        "",
        f"![객관 난이도별 평균 점수]({figs_subdir_name}/bar_difficulty.png)",
        "",
    ]


def build_md_student(
    sid: str,
    name: str,
    silver_row: pd.Series,
    course_name_kr: str,
    year: str,
    term: str,
    figs_subdir_name: str,
) -> str:
    """학생 전달용 — 제목/헤더/시험결과 단순화."""
    title = f"# {sid} {name} {year}학년도 {term}학기 {course_name_kr} 중간고사 보고서"
    parts: list[str] = [title, "", "---", "", "## 1. 시험 결과 요약", ""]
    if bool(silver_row.get("시험응시", False)):
        parts.extend([
            f"- **총점**: **{float(silver_row['total_score']):.1f}** 점",
            f"- **100점 환산**: {float(silver_row['score_percent']):.1f}",
            "",
            "(모든 시험문제는 5점)",
            "",
        ])
    else:
        parts.extend(["**시험 미응시 (결시)**", ""])
    parts.append("---")
    parts.append("")
    parts.extend(_radar_block(figs_subdir_name))
    parts.append("---")
    parts.append("")
    parts.extend(_bar_block(figs_subdir_name))
    parts.append("---")
    return "\n".join(parts)


def build_md_instructor(
    sid: str,
    name: str,
    silver_row: pd.Series,
    cohort_mean: float,
    course_name_kr: str,
    year: str,
    term: str,
    figs_subdir_name: str,
) -> str:
    """교수자 보관용 — 현행 형식 + 안내 문구만 삭제."""
    title = f"# {name} 학생 면담 보고서 — {year}-{term} {course_name_kr}"
    section = silver_row.get("section") or "—"
    cluster_label = (
        silver_row["cluster_label"]
        if pd.notna(silver_row.get("cluster_label"))
        else "(미배정)"
    )
    cluster_id = (
        int(silver_row["cluster_id"])
        if pd.notna(silver_row.get("cluster_id"))
        else "—"
    )
    parts = [
        title, "",
        f"**학번**: `{sid}` | **분반**: {section} | "
        f"**군집**: {cluster_label} (id={cluster_id})",
        "", "---", "",
        "## 1. 시험 결과 요약", "",
    ]
    if bool(silver_row.get("시험응시", False)):
        parts.extend([
            f"- **총점**: **{float(silver_row['total_score']):.1f}** "
            f"점 (cohort 평균 {cohort_mean:.1f})",
            f"- **100점 환산**: {float(silver_row['score_percent']):.1f}",
            f"- **분반 percentile**: {float(silver_row['section_percentile']):.0f}%",
            f"- **cohort percentile**: {float(silver_row['cohort_percentile']):.0f}%",
            f"- **z-score**: {float(silver_row['z_score']):+.2f}",
            "",
            "(모든 시험문제는 5점)",
            "",
        ])
    else:
        parts.extend(["**시험 미응시 (결시)** — 아래 그림은 미land.", ""])
    parts.append("---")
    parts.append("")
    parts.extend(_radar_block(figs_subdir_name))
    parts.append("---")
    parts.append("")
    parts.extend(_bar_block(figs_subdir_name))
    parts.append("---")
    parts.append("")
    parts.append("## 4. needs-map 진단 8 정량 축")
    parts.append("")
    parts.append("| 정량 축 | raw | z-score | 해석 |")
    parts.append("|---|---|---|---|")
    for axis, kr in _AXIS_KR.items():
        raw = silver_row.get(f"{axis}_raw")
        z = silver_row.get(f"{axis}_z")
        miss = bool(silver_row.get(f"{axis}_missing", True))
        if miss or pd.isna(raw):
            parts.append(f"| {kr} | — | — | (응답 누락) |")
        else:
            parts.append(
                f"| {kr} | {float(raw):.2f} | {float(z):+.2f} | "
                f"{_interpret_z(float(z))} |"
            )
    parts.extend(["", "---", ""])
    return "\n".join(parts)


# --- PDF (md → reportlab Platypus) ------------------------------------------

def md_to_pdf(md_text: str, base_dir: Path, out_pdf: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    if _NANUM and "NanumGothic" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NanumGothic", _NANUM))

    styles = getSampleStyleSheet()
    base_font = "NanumGothic" if _NANUM else "Helvetica"
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=base_font, fontSize=16, leading=20)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=base_font, fontSize=13, leading=17, textColor=colors.HexColor("#0b3d8c"))
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName=base_font, fontSize=11, leading=14)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=base_font, fontSize=10, leading=14)

    flow: list = []
    table_buf: list[list[str]] = []

    def _flush_table():
        nonlocal table_buf
        if table_buf:
            tbl = Table(table_buf, hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), base_font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#cfe2ff")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            flow.append(tbl)
            flow.append(Spacer(1, 0.3 * cm))
            table_buf = []

    for line in md_text.split("\n"):
        s = line.rstrip()
        if s.startswith("# "):
            _flush_table()
            flow.append(Paragraph(s[2:], h1))
            flow.append(Spacer(1, 0.2 * cm))
        elif s.startswith("## "):
            _flush_table()
            flow.append(Paragraph(s[3:], h2))
            flow.append(Spacer(1, 0.2 * cm))
        elif s.startswith("### "):
            _flush_table()
            flow.append(Paragraph(s[4:], h3))
            flow.append(Spacer(1, 0.15 * cm))
        elif s.startswith("![") and "](" in s and s.endswith(")"):
            _flush_table()
            try:
                rel_path = s.split("](")[1][:-1]
                abs_path = (base_dir / rel_path).resolve()
                if abs_path.exists():
                    img = Image(str(abs_path), width=14 * cm, height=10 * cm,
                                kind="proportional")
                    flow.append(img)
                    flow.append(Spacer(1, 0.3 * cm))
            except Exception:
                pass
        elif s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("- :") for c in cells):
                continue
            table_buf.append(cells)
        elif s.strip() == "---":
            _flush_table()
            flow.append(Spacer(1, 0.4 * cm))
        elif s.strip() == "":
            _flush_table()
            flow.append(Spacer(1, 0.15 * cm))
        else:
            _flush_table()
            cleaned = s.replace("**", "")
            flow.append(Paragraph(cleaned, body))
    _flush_table()

    doc = SimpleDocTemplate(
        str(out_pdf), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    doc.build(flow)


# --- main -------------------------------------------------------------------

def _safe_name(name: str) -> str:
    return (name or "이름없음").strip().replace("/", "_").replace(" ", "_")


def _emit_one_student(
    sid: str,
    name: str,
    student_grps: dict[str, pd.DataFrame],
    cohort_grps: dict[str, pd.DataFrame],
    silver_row: pd.Series,
    cohort_mean: float,
    course_name_kr: str,
    year: str,
    term: str,
    student_root: Path,
    instructor_root: Path,
) -> tuple[Path, Path]:
    safe_name = _safe_name(name)
    folder = f"{sid}_{safe_name}"

    # 학생 전달용 — figs_{학번}_{이름}/
    s_dir = student_root / folder
    s_figs_name = f"figs_{sid}_{safe_name}"
    s_figs = s_dir / s_figs_name

    # 교수자 보관용 — figs/
    i_dir = instructor_root / folder
    i_figs_name = "figs"
    i_figs = i_dir / i_figs_name

    for figs in (s_figs, i_figs):
        figs.mkdir(parents=True, exist_ok=True)

    # 그림 6개 — 양 폴더에 동일 land
    for figs in (s_figs, i_figs):
        render_radar_chapter(
            cohort_grps["chapter"], student_grps["chapter"],
            figs / "radar_chapter.png",
        )
        render_radar_week(
            cohort_grps["week"], student_grps["week"],
            figs / "radar_week.png",
        )
        for col in _META_KIND_LABEL.keys():
            render_bar_meta(
                cohort_grps[col], student_grps[col], col,
                figs / f"bar_{col}.png",
            )

    # 학생 전달용 md/pdf — 파일명 = 학번_이름
    s_md_text = build_md_student(
        sid, name, silver_row, course_name_kr, year, term, s_figs_name,
    )
    s_md_path = s_dir / f"{sid}_{safe_name}.md"
    s_pdf_path = s_dir / f"{sid}_{safe_name}.pdf"
    s_md_path.write_text(s_md_text, encoding="utf-8")
    md_to_pdf(s_md_text, s_dir, s_pdf_path)

    # 교수자 보관용 md/pdf — 파일명 = 보고서
    i_md_text = build_md_instructor(
        sid, name, silver_row, cohort_mean,
        course_name_kr, year, term, i_figs_name,
    )
    i_md_path = i_dir / "보고서.md"
    i_pdf_path = i_dir / "보고서.pdf"
    i_md_path.write_text(i_md_text, encoding="utf-8")
    md_to_pdf(i_md_text, i_dir, i_pdf_path)

    return s_pdf_path, i_pdf_path


def _copy_student_pdfs_for_email(
    student_root: Path, email_root: Path,
) -> tuple[int, list[str]]:
    """학생 전달용 PDF 모두 → 이메일_발송용 단일 폴더 복사 + 검증.

    Returns:
        (copied_count, conflicts) — conflicts 가 비어있어야 정상.
    """
    if email_root.exists():
        shutil.rmtree(email_root)
    email_root.mkdir(parents=True, exist_ok=True)
    seen: dict[str, Path] = {}
    conflicts: list[str] = []
    src_pdfs: list[Path] = []
    for sid_dir in sorted(student_root.iterdir()):
        if not sid_dir.is_dir():
            continue
        for pdf in sid_dir.glob("*.pdf"):
            src_pdfs.append(pdf)
    for src in src_pdfs:
        target = email_root / src.name
        if target.exists() or src.name in seen:
            conflicts.append(src.name)
            continue
        shutil.copy2(src, target)
        seen[src.name] = src
    return len(seen), conflicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semester", required=True, help="e.g. 2026-1")
    ap.add_argument("--course-slug", required=True, help="e.g. anatomy")
    ap.add_argument("--mapping", required=True, type=Path,
                    help="Diagnostic mapping yaml (course_name_kr 추출).")
    ap.add_argument("--bronze-exam-dir", default=BRONZE_EXAM_ROOT, type=Path)
    ap.add_argument("--exam-yaml", required=True, type=Path)
    ap.add_argument("--silver-dir", required=True, type=Path)
    ap.add_argument("--gold-dir", required=True, type=Path)
    ap.add_argument("--n-items", type=int, default=44)
    args = ap.parse_args()

    year, term = split_semester(args.semester)
    course_name_kr = get_course_name_kr(args.mapping, args.course_slug)
    print(f"[meta] {year}학년도 {term}학기 / {course_name_kr} ({args.course_slug})")

    silver_im = args.silver_dir / "immersio" / f"{args.semester}-{args.course_slug}"
    gold_im = args.gold_dir / "immersio" / f"{args.semester}-{args.course_slug}"
    student_root = gold_im / "학생 전달용"
    instructor_root = gold_im / "교수자 보관용"
    email_root = gold_im / "이메일_발송용"

    # Reset student/instructor dirs (이메일_발송용은 _copy 단계에서 reset).
    for r in (student_root, instructor_root):
        if r.exists():
            shutil.rmtree(r)
        r.mkdir(parents=True, exist_ok=True)

    # OX parse
    print("=== production OX parse ===")
    ox_frames = []
    for sect in SECTIONS:
        # production 파일명 패턴: {course_name_kr}_{section}반 결과(OX).xls
        path = args.bronze_exam_dir / f"{course_name_kr}_{sect}반 결과(OX).xls"
        if path.exists():
            df = parse_ox_xls(path, sect, args.n_items, course_name_kr)
            ox_frames.append(df)
            print(f"  {sect}반: {df['student_id'].nunique()} 학생")
    if not ox_frames:
        raise FileNotFoundError(
            f"OX xls 미land 아래 패턴: {args.bronze_exam_dir}/{course_name_kr}_*반 결과(OX).xls"
        )
    ox = pd.concat(ox_frames, ignore_index=True)
    print(f"  total: {ox['student_id'].nunique()} 학생, {len(ox)} OX 행")

    # meta + score
    meta = parse_exam_meta(args.exam_yaml)
    print(f"=== exam yaml: {len(meta)} items ===")
    merged = ox.merge(meta, on="item_no", how="left")
    merged["score"] = merged["correct"] * POINTS_PER_ITEM

    # silver round-trip
    silver = pq.read_table(silver_im / "진단×시험결합.parquet").to_pandas()
    silver_idx = silver.set_index("student_id")
    cohort_mean = (
        float(silver.loc[silver["시험응시"], "total_score"].mean())
        if silver["시험응시"].any()
        else float("nan")
    )

    META_COLS = (
        "chapter", "week",
        "expected_difficulty", "question_type", "source", "difficulty",
    )
    cohort_grps = {col: cohort_mean_by(merged, col) for col in META_COLS}

    sids = sorted(set(ox["student_id"].unique()))
    print(f"=== rendering {len(sids)} students × 2 reports ===")
    s_pdfs: list[Path] = []
    i_pdfs: list[Path] = []
    for n, sid in enumerate(sids, 1):
        sub = merged[merged["student_id"] == sid]
        if sub.empty:
            continue
        name = sub["name_kr"].iloc[0] or "이름없음"
        student_grps = {col: student_mean_by(merged, sid, col) for col in META_COLS}

        if sid in silver_idx.index:
            srow = silver_idx.loc[sid]
            if isinstance(srow, pd.DataFrame):
                srow = srow.iloc[0]
        else:
            # off-roster 응시자 — silver 미land. OX 점수에서 직접 합성.
            total = float(sub["score"].sum())
            srow = pd.Series({
                "시험응시": True,
                "total_score": total,
                "score_percent": total / (POINTS_PER_ITEM * args.n_items) * 100.0,
                "section_percentile": float("nan"),
                "cohort_percentile": float("nan"),
                "z_score": float("nan"),
                "section": sub["section"].iloc[0],
            })

        s_pdf, i_pdf = _emit_one_student(
            sid, name, student_grps, cohort_grps, srow, cohort_mean,
            course_name_kr, year, term, student_root, instructor_root,
        )
        s_pdfs.append(s_pdf)
        i_pdfs.append(i_pdf)
        if n % 25 == 0:
            print(f"  ... {n}/{len(sids)} done")

    # 이메일_발송용 PDF 복사 + 검증
    print("=== 이메일_발송용 PDF copy ===")
    n_copied, conflicts = _copy_student_pdfs_for_email(student_root, email_root)
    expected = len(s_pdfs)
    if conflicts:
        raise RuntimeError(
            f"이메일_발송용 PDF 복사 중 중복 파일명 {len(conflicts)}건 — "
            f"sample {conflicts[:5]}"
        )
    if n_copied != expected:
        raise RuntimeError(
            f"이메일_발송용 PDF 개수 불일치 — copied={n_copied}, expected={expected}"
        )
    print(f"  ✅ {n_copied} PDF 복사 — 중복 0건, 학생 전달용 == 이메일_발송용 정합")

    # 최종 점검
    print()
    print("=== 산출 inventory ===")
    print(f"  학생 전달용:    {len(list(student_root.iterdir()))} 학생 폴더")
    print(f"  교수자 보관용: {len(list(instructor_root.iterdir()))} 학생 폴더")
    print(f"  이메일_발송용: {len(list(email_root.glob('*.pdf')))} PDF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
