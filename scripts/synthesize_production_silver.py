"""V2 우회 — production *결과.xls* + *결시.xls* → silver 학생지표.parquet.

spec 004 ingest 의 V2 violation (xls multi-file mode) 후속 spec 분리 결정.
본 스크립트는 *결과.xls* 8-col 단순 형식만 read 하여 학생-단위 보고서 land
필수 데이터 (학생지표.parquet + immersio manifest + cluster_names sidecar)
를 합성한다.

production 형식:
- {course}_{section}반 결과.xls: row0+1 header, col=[순번/학년/학번/성명/점수/총점/100점환산/석차]
- {course}_{section}반 결시.xls: row0+1 header, col=[순번/학년/학번/성명/결시/결시과목수]

학번 normalize: 8자리 (21194145) → 10자리 (2021194145) — student_master 정합.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO = Path("/home/kjeong/localgit/paideia")
BRONZE_EXAM = REPO / "data/bronze/시험성적"
SILVER_IM = REPO / "data/silver/immersio/2026-1-anatomy"
SILVER_NM = REPO / "data/silver/needs-map/2026-1-anatomy"
GOLD_NM = REPO / "data/gold/needs-map/2026-1-anatomy"
SECTIONS = ("A", "B", "C", "D")


def _normalize_sid(raw: object) -> str | None:
    """8자리 학번 → 10자리 (`20` prefix 추가, student_master 정합)."""
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        return f"20{s}"
    if len(s) == 10 and s.isdigit():
        return s
    return None  # malformed — silent drop


def _read_result_xls(path: Path, section: str) -> pd.DataFrame:
    """8-col *결과.xls* → DataFrame (학번/성명/총점/100점환산/석차/section)."""
    raw = pd.read_excel(path, sheet_name="Sheet1", dtype=object, header=None)
    rows: list[dict] = []
    for _, r in raw.iloc[2:].iterrows():
        sid_raw = r.iloc[2]
        sid = _normalize_sid(sid_raw)
        if sid is None:  # "전체평균" / 빈 행 / NaN 학번
            continue
        try:
            total = float(r.iloc[5]) if pd.notna(r.iloc[5]) else None
            percent = float(r.iloc[6]) if pd.notna(r.iloc[6]) else None
            rank = int(r.iloc[7]) if pd.notna(r.iloc[7]) else None
        except (ValueError, TypeError):
            continue
        if total is None:
            continue
        rows.append(
            {
                "student_id": sid,
                "name_kr": str(r.iloc[3]) if pd.notna(r.iloc[3]) else "(이름없음)",
                "section": section,
                "exam_taken": True,
                "total_score": total,
                "score_percent": percent,
                "section_rank": rank,
            }
        )
    return pd.DataFrame(rows)


def _read_absent_xls(path: Path, section: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Sheet1", dtype=object, header=None)
    rows: list[dict] = []
    for _, r in raw.iloc[2:].iterrows():
        sid_raw = r.iloc[2]
        sid = _normalize_sid(sid_raw)
        if sid is None:
            continue
        rows.append(
            {
                "student_id": sid,
                "name_kr": str(r.iloc[3]) if pd.notna(r.iloc[3]) else "(이름없음)",
                "section": section,
                "exam_taken": False,
                "total_score": None,
                "score_percent": None,
                "section_rank": None,
            }
        )
    return pd.DataFrame(rows)


def _build_student_metrics() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for sect in SECTIONS:
        result = BRONZE_EXAM / f"인체구조와기능_{sect}반 결과.xls"
        absent = BRONZE_EXAM / f"인체구조와기능_{sect}반 결시.xls"
        if result.exists():
            frames.append(_read_result_xls(result, sect))
        if absent.exists():
            frames.append(_read_absent_xls(absent, sect))
    df = pd.concat(frames, ignore_index=True)
    # Dedup: a student listed in both 결과 and 결시 (rare) — prefer 결과.
    df = df.sort_values(["student_id", "exam_taken"], ascending=[True, False])
    df = df.drop_duplicates("student_id", keep="first").reset_index(drop=True)

    # cohort + section percentiles + z-score (응시자 기준).
    sat = df[df["exam_taken"]].copy()
    cohort_mean = float(sat["total_score"].mean())
    cohort_std = float(sat["total_score"].std(ddof=1))

    # cohort percentile via rank
    sat = sat.sort_values("total_score", ascending=True).reset_index(drop=True)
    sat["cohort_percentile"] = 100.0 * (sat.index + 1).astype(float) / len(sat)
    sat["z_score"] = (sat["total_score"] - cohort_mean) / cohort_std if cohort_std > 0 else 0.0

    # section percentile per section
    section_pct: dict[str, pd.Series] = {}
    for sect, sg in sat.groupby("section"):
        sg = sg.sort_values("total_score").reset_index(drop=True)
        section_pct[sect] = pd.Series(
            data=100.0 * (sg.index + 1).astype(float) / len(sg),
            index=sg["student_id"].values,
        )
    pct_map: dict[str, float] = {}
    for sect, ser in section_pct.items():
        for sid, val in ser.items():
            pct_map[sid] = float(val)
    sat["section_percentile"] = sat["student_id"].map(pct_map)

    # Merge back into df
    sat_keep = sat[["student_id", "section_percentile", "cohort_percentile", "z_score"]]
    df = df.merge(sat_keep, on="student_id", how="left")

    # 학생지표 schema 정합
    df["semester"] = "2026-1"
    df["course_slug"] = "anatomy"
    for c in (
        "chapter_correct_rates",
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
    ):
        df[c] = "{}"
    for c in ("interest_chapters_correct_rate", "aversion_chapters_correct_rate"):
        df[c] = None

    cols_keep = [
        "student_id",
        "name_kr",
        "section",
        "semester",
        "course_slug",
        "exam_taken",
        "total_score",
        "score_percent",
        "section_percentile",
        "cohort_percentile",
        "z_score",
        "chapter_correct_rates",
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
        "interest_chapters_correct_rate",
        "aversion_chapters_correct_rate",
    ]
    return df[cols_keep].sort_values("student_id").reset_index(drop=True)


def _write_student_metrics(df: pd.DataFrame) -> Path:
    schema = pa.schema(
        [
            pa.field("student_id", pa.large_string()),
            pa.field("name_kr", pa.large_string()),
            pa.field("section", pa.large_string()),
            pa.field("semester", pa.large_string()),
            pa.field("course_slug", pa.large_string()),
            pa.field("exam_taken", pa.bool_()),
            pa.field("total_score", pa.float64()),
            pa.field("score_percent", pa.float64()),
            pa.field("section_percentile", pa.float64()),
            pa.field("cohort_percentile", pa.float64()),
            pa.field("z_score", pa.float64()),
            pa.field("chapter_correct_rates", pa.large_string()),
            pa.field("source_correct_rates", pa.large_string()),
            pa.field("difficulty_correct_rates", pa.large_string()),
            pa.field("expected_difficulty_correct_rates", pa.large_string()),
            pa.field("item_type_correct_rates", pa.large_string()),
            pa.field("interest_chapters_correct_rate", pa.null()),
            pa.field("aversion_chapters_correct_rate", pa.null()),
        ]
    )
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    out = SILVER_IM / "학생지표.parquet"
    pq.write_table(
        table,
        out,
        compression="snappy",
        use_dictionary=False,
        write_statistics=False,
    )
    return out


def _write_immersio_manifest() -> Path:
    payload = {
        "schema_version": "0.1.0",
        "module_version": "immersio/0.1.0-prod-v2-bypass",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "generated_at_utc": "2026-04-30T00:00:00Z",
        "note": "V2 우회 합성 — production *결과.xls* 직접 read. spec 004 ingest 비정합 (학생지표만 land, exam_result/exam_item 미land).",
    }
    out = SILVER_IM / "manifest.json"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def _write_cluster_names() -> Path:
    """needs-map cluster_summary.xlsx → cluster_names.json sidecar (SPEC-GAP-001)."""
    summary = pd.read_excel(GOLD_NM / "cluster_summary.xlsx", sheet_name="summary")
    names: dict[str, str] = {}
    for _, r in summary.iterrows():
        cid = int(r["cluster_id"])
        # cluster_summary 가 동일 라벨을 부여한 경우 (production state)
        # cluster_id 로 disambiguate.
        base = str(r["name"]).strip()
        names[str(cid)] = f"{base} (cluster {cid})"
    out = SILVER_NM / "cluster_names.json"
    out.write_text(
        json.dumps(names, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def _backfill_student_master(metrics_df: pd.DataFrame) -> Path:
    """학생지표 정보를 student_master.parquet 의 exam_taken/exam_absent/total
    필드에 backfill. joiner 가 student_master 의 exam_taken 을 silver 시험 응시
    flag 의 source-of-truth 로 사용하므로 본 backfill 없이는 시험응시=0 으로
    silver 가 land 된다.
    """
    sm_path = SILVER_IM / "student_master.parquet"
    sm = pq.read_table(sm_path).to_pandas()
    metrics_idx = metrics_df.set_index("student_id")
    for sid, srow in metrics_idx.iterrows():
        mask = sm["student_id"] == sid
        if not mask.any():
            continue  # off-roster respondent — skip
        sm.loc[mask, "exam_taken"] = bool(srow["exam_taken"])
        sm.loc[mask, "exam_absent"] = not bool(srow["exam_taken"])
        if srow["exam_taken"] and pd.notna(srow["total_score"]):
            sm.loc[mask, "exam_total_score"] = float(srow["total_score"])
            sm.loc[mask, "exam_max_score"] = 220.0  # 100 items × 2.2pt avg
    table = pa.Table.from_pandas(sm, preserve_index=False)
    pq.write_table(
        table,
        sm_path,
        compression="snappy",
        use_dictionary=False,
        write_statistics=False,
    )
    return sm_path


def main() -> int:
    df = _build_student_metrics()
    print(f"학생지표 {len(df)} rows synthesized")
    print(f"  - 응시: {int(df['exam_taken'].sum())}, 결시: {int((~df['exam_taken']).sum())}")
    print(f"  - cohort 평균: {df.loc[df['exam_taken'], 'total_score'].mean():.1f}")
    print(f"  - sections: {df['section'].value_counts().sort_index().to_dict()}")
    metrics_path = _write_student_metrics(df)
    print(f"  → {metrics_path}")
    manifest_path = _write_immersio_manifest()
    print(f"  → {manifest_path}")
    cluster_names_path = _write_cluster_names()
    print(f"  → {cluster_names_path}")
    sm_path = _backfill_student_master(df)
    print(f"  → {sm_path} (backfilled exam_taken/total_score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
