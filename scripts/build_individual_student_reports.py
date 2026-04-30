"""학생별 면담 시트 — md + PDF + figs (radar + bar charts).

사용자 명시 (2026-04-30):
1. md + PDF 양쪽 산출
2. radar chart: 챕터별 cohort 평균 (파란 실선) + 학생 점수 (빨간 실선)
3. bar charts: 메타데이터별 cohort 평균 (파랑) + 학생 평균 (빨강)
   - 예상_난이도 (쉬움/보통/어려움 = 상중하 순)
   - 문제유형 / 출처 / 난이도 / 주차 / 챕터
4. 모든 문제 5점

입력:
- data/bronze/시험성적/인체구조와기능_{A,B,C,D}반 결과(OX).xls (학생당 3 row: 정답/표기/결과)
- data/bronze/시험문제/실제_출제문제.yaml (44 문항 메타)
- data/silver/immersio/2026-1-anatomy/진단×시험결합.parquet (60-col silver)

산출:
- data/gold/immersio/2026-1-anatomy/학생별_상세/{sid}_{name}/
  - 보고서.md
  - 보고서.pdf
  - figs/radar_chapter.png
  - figs/bar_expected_difficulty.png
  - figs/bar_question_type.png
  - figs/bar_source.png
  - figs/bar_difficulty.png
  - figs/bar_week.png
  - figs/bar_chapter.png
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml
from matplotlib.patches import Patch

REPO = Path("/home/kjeong/localgit/paideia")
BRONZE_OX = REPO / "data/bronze/시험성적"
EXAM_YAML = REPO / "data/bronze/시험문제/실제_출제문제.yaml"
SILVER_IM = REPO / "data/silver/immersio/2026-1-anatomy"
GOLD_IM = REPO / "data/gold/immersio/2026-1-anatomy"
OUT_ROOT = GOLD_IM / "학생별_상세"
SECTIONS = ("A", "B", "C", "D")
POINTS_PER_ITEM = 5.0  # 사용자 명시

# Korean font setup — NixOS / Gentoo / 일반 distro 대응. fc-match fallback.
_NANUM: str | None = None
_FONT_HARDCODED = (
    "/run/current-system/sw/share/fonts/nanum/NanumGothic.ttf",
    "/usr/share/fonts/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)
for cand in _FONT_HARDCODED:
    if Path(cand).exists():
        _NANUM = cand
        break
if _NANUM is None:
    import subprocess
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "NanumGothic"],
            capture_output=True, text=True, timeout=5,
        )
        candidate = result.stdout.strip()
        if candidate and Path(candidate).exists() and "Nanum" in candidate:
            _NANUM = candidate
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
if _NANUM is None:
    # NixOS home-manager path glob fallback
    for p in Path("/nix/store").glob("*/share/fonts/NanumGothic.ttf"):
        _NANUM = str(p)
        break
if _NANUM:
    fm.fontManager.addfont(_NANUM)
    plt.rcParams["font.family"] = "NanumGothic"
    print(f"[font] NanumGothic land: {_NANUM}")
else:
    print("[font] WARN — NanumGothic not found. 한글 figs 깨짐 가능.", file=sys.stderr)
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150


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


def parse_ox_xls(path: Path, section: str, n_items: int) -> pd.DataFrame:
    """학생당 3 row (정답/표기/결과) → DataFrame[student_id, item_no, correct]."""
    raw = pd.read_excel(path, sheet_name="Sheet1", dtype=object, header=None)
    rows: list[dict] = []
    n_rows = len(raw)
    i = 2  # row 0+1 = 헤더
    while i < n_rows:
        # 메타 row 식별: col 0 (순번) 이 숫자 + col 8 == "정답"
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
        # 다음 두 row 가 표기/결과여야 함
        if i + 2 >= n_rows:
            break
        # 결과 row = i+2
        result_row = raw.iloc[i + 2]
        if str(result_row.iat[8]).strip() != "결과":
            # 패턴 위반 — skip
            i += 3
            continue
        for it in range(1, n_items + 1):
            col_idx = 8 + it  # col 9 = item 1
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


def compute_meta_scores(ox: pd.DataFrame, meta: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """학생별 + cohort 메타데이터별 평균 점수.

    Returns dict[meta_kind] = DataFrame columns:
      [meta_value, cohort_mean_score, count]
    + per-student: dict[meta_kind][sid] = DataFrame [meta_value, score, count]
    """
    merged = ox.merge(meta, on="item_no", how="left")
    merged["score"] = merged["correct"] * POINTS_PER_ITEM
    return merged


def cohort_mean_by(merged: pd.DataFrame, meta_col: str) -> pd.DataFrame:
    """cohort: 메타값별 평균 점수 (학생별 평균의 평균이 아니라 모든 정답×5점 평균)."""
    grp = (
        merged.groupby(meta_col)
        .agg(mean_score=("score", "mean"), n_responses=("score", "count"))
        .reset_index()
    )
    return grp


def student_mean_by(merged: pd.DataFrame, sid: str, meta_col: str) -> pd.DataFrame:
    sub = merged[merged["student_id"] == sid]
    grp = (
        sub.groupby(meta_col)
        .agg(mean_score=("score", "mean"), n_responses=("score", "count"))
        .reset_index()
    )
    return grp


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
    fig.savefig(out, format="png", dpi=150,
                metadata={"Software": "paideia"})
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


# 주차/챕터는 radar 로만 land — bar 생산 X (사용자 명시 2026-04-30).
_META_KIND_LABEL = {
    "expected_difficulty": "예상 난이도",
    "question_type": "문제 유형",
    "source": "문제 출처",
    "difficulty": "객관 난이도",
}

_CATEGORY_ORDER = {
    "expected_difficulty": ["쉬움", "보통", "어려움"],  # 상중하 순
    "question_type": None,  # alphabetical fallback
    "source": ["교과서", "형성평가", "퀴즈"],
    "difficulty": [1, 2, 3],
}


def render_bar_meta(
    cohort: pd.DataFrame,
    student: pd.DataFrame,
    meta_col: str,
    out: Path,
) -> None:
    """파란 막대 cohort + 빨간 막대 student. 카테고리 순서 _CATEGORY_ORDER 강제."""
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

    x = np.arange(len(cats))
    w = 0.35
    fig, ax = plt.subplots(figsize=(max(6, len(cats) * 1.2), 5))
    ax.bar(x - w / 2, cohort_vals, w, color="blue", label="전체 학생 평균")
    ax.bar(x + w / 2, student_vals, w, color="red", label="해당 학생")
    ax.set_xticks(x)
    ax.set_xticklabels([str(c) for c in cats], rotation=15, ha="right", size=10)
    ax.set_ylim(0, 5.0)
    ax.set_ylabel("평균 점수 (5점 만점)")
    label = _META_KIND_LABEL.get(meta_col, meta_col)
    ax.set_title(f"{label}별 평균 점수", size=12)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="png", dpi=150,
                metadata={"Software": "paideia"})
    plt.close(fig)


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


def _build_md(
    sid: str,
    name: str,
    silver_row: pd.Series,
    cohort_mean: float,
    out_dir: Path,
    fig_files: list[tuple[str, str]],
) -> str:
    """학생별 보고서 md 본문 (그림 inline)."""
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
        f"# {name} 학생 면담 보고서 — 2026-1 인체구조와기능",
        "",
        f"**학번**: `{sid}` | **분반**: {section} | "
        f"**군집**: {cluster_label} (id={cluster_id})",
        "",
        "---",
        "",
        "## 1. 시험 결과 요약",
        "",
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

    parts.extend([
        "---",
        "",
        "## 2. 챕터·주차별 평균 점수 (Radar)",
        "",
        "파란 실선 = 전체 학생 평균 / 빨간 실선 = 해당 학생",
        "",
    ])
    for fname, caption in fig_files:
        if fname.startswith("radar"):
            parts.append(f"### {caption}")
            parts.append("")
            parts.append(f"![{caption}](figs/{fname})")
            parts.append("")
    parts.extend([
        "---",
        "",
        "## 3. 문제 메타데이터별 평균 점수 (Bar)",
        "",
        "파란 막대 = 전체 학생 평균 / 빨간 막대 = 해당 학생. "
        "챕터·주차는 radar 로 land 됨 (이 섹션 제외).",
        "",
    ])
    for fname, caption in fig_files:
        if fname.startswith("bar_"):
            parts.append(f"### {caption}")
            parts.append("")
            parts.append(f"![{caption}](figs/{fname})")
            parts.append("")

    # needs-map 진단
    parts.extend([
        "---",
        "",
        "## 4. needs-map 진단 8 정량 축",
        "",
        "| 정량 축 | raw | z-score | 해석 |",
        "|---|---|---|---|",
    ])
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


def _md_to_pdf(md_text: str, fig_dir: Path, out_pdf: Path) -> None:
    """간단 md → PDF (reportlab Platypus). 그림 inline 으로 embed."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
        TableStyle,
    )

    if _NANUM and "NanumGothic" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NanumGothic", _NANUM))

    styles = getSampleStyleSheet()
    base_font = "NanumGothic" if _NANUM else "Helvetica"
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=base_font, fontSize=18, leading=22)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=base_font, fontSize=14, leading=18, textColor=colors.HexColor("#0b3d8c"))
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName=base_font, fontSize=12, leading=15)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=base_font, fontSize=10, leading=14)

    flow: list = []
    table_buf: list[list[str]] = []
    in_table = False

    def _flush_table():
        nonlocal table_buf, in_table
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
        in_table = False

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
                abs_path = (fig_dir.parent / rel_path).resolve()
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
                continue  # markdown table separator
            in_table = True
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


def main() -> int:
    n_items = 44
    print(f"=== production OX parse (4 sections) ===")
    ox_frames = []
    for sect in SECTIONS:
        path = BRONZE_OX / f"인체구조와기능_{sect}반 결과(OX).xls"
        if path.exists():
            df = parse_ox_xls(path, sect, n_items)
            ox_frames.append(df)
            print(f"  {sect}반: {df['student_id'].nunique()} 학생, {len(df)} OX 행")
    ox = pd.concat(ox_frames, ignore_index=True)
    print(f"  total: {ox['student_id'].nunique()} 학생, {len(ox)} OX 행")

    meta = parse_exam_meta(EXAM_YAML)
    print(f"\n=== meta: {len(meta)} items ===")

    merged = compute_meta_scores(ox, meta)
    print(f"merged shape: {merged.shape}")

    print("\n=== silver round-trip ===")
    silver = pq.read_table(SILVER_IM / "진단×시험결합.parquet").to_pandas()
    print(f"silver rows: {len(silver)}")
    silver_idx = silver.set_index("student_id")
    cohort_mean = float(
        silver.loc[silver["시험응시"], "total_score"].mean()
    ) if silver["시험응시"].any() else float("nan")

    # radar 용 메타 (chapter, week) + bar 용 메타 (4종) 모두 cohort 평균 미리 land
    META_COLS = (
        "chapter", "week",  # radar
        "expected_difficulty", "question_type", "source", "difficulty",  # bar
    )

    cohort_grps = {col: cohort_mean_by(merged, col) for col in META_COLS}

    # Reset OUT_ROOT
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    sids = sorted(set(ox["student_id"].unique()))
    print(f"\n=== rendering reports for {len(sids)} students ===")
    for n, sid in enumerate(sids, 1):
        sub = merged[merged["student_id"] == sid]
        if sub.empty:
            continue
        name = sub["name_kr"].iloc[0] or "이름없음"
        safe_name = name.replace("/", "_").replace(" ", "")
        student_dir = OUT_ROOT / f"{sid}_{safe_name}"
        figs_dir = student_dir / "figs"
        figs_dir.mkdir(parents=True, exist_ok=True)

        student_grps = {
            col: student_mean_by(merged, sid, col) for col in META_COLS
        }

        # Radar 2종 — 챕터 + 주차 (사용자 명시: 이 둘은 radar 로만)
        render_radar_chapter(
            cohort_grps["chapter"], student_grps["chapter"],
            figs_dir / "radar_chapter.png",
        )
        render_radar_week(
            cohort_grps["week"], student_grps["week"],
            figs_dir / "radar_week.png",
        )
        fig_files = [
            ("radar_chapter.png", "챕터별 평균 점수"),
            ("radar_week.png", "주차별 평균 점수"),
        ]

        # Bar 4종 — 챕터/주차 제외 (예상_난이도/문제유형/출처/난이도)
        for col, label in _META_KIND_LABEL.items():
            png = f"bar_{col}.png"
            render_bar_meta(
                cohort_grps[col], student_grps[col], col,
                figs_dir / png,
            )
            fig_files.append((png, f"{label}별 평균 점수"))

        # silver row (없으면 default)
        if sid in silver_idx.index:
            silver_row = silver_idx.loc[sid]
            if isinstance(silver_row, pd.DataFrame):
                silver_row = silver_row.iloc[0]
        else:
            silver_row = pd.Series({"시험응시": False, "section": sub["section"].iloc[0]})

        md_text = _build_md(sid, name, silver_row, cohort_mean, student_dir, fig_files)
        md_path = student_dir / "보고서.md"
        md_path.write_text(md_text, encoding="utf-8")

        pdf_path = student_dir / "보고서.pdf"
        _md_to_pdf(md_text, figs_dir, pdf_path)

        if n % 25 == 0:
            print(f"  ... {n}/{len(sids)} 완료")

    print(f"\n=== land 완료 — {len(sids)} 학생 ===")
    print(f"out: {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
