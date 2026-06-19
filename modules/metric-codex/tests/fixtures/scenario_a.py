"""Shared synthetic-fixture builders for the metric-codex ingest integration tests.

Builds a temporary ``data_root`` with the real Bronze/Silver layout that the
``metric-codex ingest`` CLI consumes:

    data/bronze/metric-codex/{semester}-{course}/성적출석.xlsx
    data/bronze/metric-codex/{semester}-{course}/성적출석_map.yaml
    data/silver/immersio/{semester}-{course}/...
    data/silver/needs-map/{semester}-{course}/...

Scenario A: one student (``_SID_A``) appears in BOTH the school Excel (minimal
``value_num`` score/attendance) AND the upstream immersio/needs-map Silver
(rich ``value_num`` percentiles and ``value_text`` free-text categories), so the
consolidated store proves structured + unstructured data coexist under one
``student_id``.
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pandas as pd
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

SEMESTER = "2026-1"
COURSE = "anatomy"
KEY = f"{SEMESTER}-{COURSE}"

# Student A is present everywhere (school + immersio + needs-map).
SID_A = "2026000001"
# Student B is present only in the school Excel (minimal layer only).
SID_B = "2026000002"

NAME_A = "김철수"
NAME_B = "이영희"


def _write_school_excel(path: Path) -> None:
    """Write a minimal school grade/attendance workbook for A and B."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점", "환산점수", "출석"])
    ws.append([int(SID_A), NAME_A, 85, 90.5, 15])
    ws.append([int(SID_B), NAME_B, 70, 75.0, 12])
    wb.save(path)


def _write_school_map(path: Path) -> None:
    """Write the 성적출석_map.yaml describing the school workbook columns."""
    text = (
        f"semester: {SEMESTER}\n"
        f"course_slug: {COURSE}\n"
        "sheet: 0\n"
        "header_row: 1\n"
        "columns:\n"
        "  student_id: 학번\n"
        "  name_kr: 이름\n"
        "  score_total: 총점\n"
        "  score_percent: 환산점수\n"
        "  attendance: 출석\n"
    )
    path.write_text(text, encoding="utf-8")


def _write_student_metrics(path: Path) -> None:
    """Write immersio 학생지표.parquet — rich value_num percentiles for A."""
    rows = [
        {
            "student_id": SID_A,
            "name_kr": NAME_A,
            "section": "A",
            "semester": SEMESTER,
            "course_slug": COURSE,
            "exam_taken": True,
            "total_score": 80.0,
            "score_percent": 80.0,
            "section_percentile": 75.0,
            "cohort_percentile": 70.0,
            "z_score": 1.2,
            "chapter_correct_rates": json.dumps(
                {"순환": 0.9, "호흡": 0.5}, ensure_ascii=False, sort_keys=True
            ),
            "source_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "difficulty_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
            "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
            "interest_chapters_correct_rate": None,
            "aversion_chapters_correct_rate": None,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)


def _write_free_text(path: Path) -> None:
    """Write needs-map free_text_categorization.parquet — value_text for A."""
    rows = [
        {
            "student_id": SID_A,
            "item_id": "q9",
            "matched_categories": ["health", "career"],
            "match_source": "dictionary",
            "raw_length": 42,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)


def build_scenario_a(tmp_path: Path) -> Path:
    """Build the Scenario A ``data_root`` layout and return it.

    Args:
        tmp_path: pytest tmp directory to root the synthetic data tree at.

    Returns:
        The ``data_root`` directory (``tmp_path / "data"``).
    """
    data_root = tmp_path / "data"

    bronze = data_root / "bronze" / "metric-codex" / KEY
    immersio = data_root / "silver" / "immersio" / KEY
    needsmap = data_root / "silver" / "needs-map" / KEY
    for d in (bronze, immersio, needsmap):
        d.mkdir(parents=True)

    _write_school_excel(bronze / "성적출석.xlsx")
    _write_school_map(bronze / "성적출석_map.yaml")
    _write_student_metrics(immersio / "학생지표.parquet")
    _write_free_text(needsmap / "free_text_categorization.parquet")

    return data_root


__all__ = [
    "build_scenario_a",
    "SEMESTER",
    "COURSE",
    "KEY",
    "SID_A",
    "SID_B",
    "NAME_A",
    "NAME_B",
    "STANDARD_AXIS_KEYS",
]
