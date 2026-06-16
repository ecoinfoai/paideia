"""Cohort markdown writer contract test (T100d)."""

from __future__ import annotations

from pathlib import Path

from immersio.email.cohort_filter import write_cohort_md
from paideia_shared.schemas import CohortLabel, CohortRow


def _row(sid: str, score: float, *, label: CohortLabel) -> CohortRow:
    return CohortRow(
        student_id=sid,
        name_kr="홍길동",
        score_percent=score,
        cohort=label,
    )


def test_three_files_written(tmp_path: Path) -> None:
    low = [_row("1234567001", 45.5, label=CohortLabel.LOW_SCORE)]
    rest = [_row("1234567002", 85.0, label=CohortLabel.REST)]
    combined, low_path, rest_path = write_cohort_md(low, rest, tmp_path)
    assert combined.is_file()
    assert low_path.is_file()
    assert rest_path.is_file()
    assert combined.name == "cohort_명단.md"
    assert low_path.name == "cohort_저득점_명단.md"
    assert rest_path.name == "cohort_나머지_명단.md"


def test_combined_md_includes_both_tables(tmp_path: Path) -> None:
    low = [_row("1234567001", 45.5, label=CohortLabel.LOW_SCORE)]
    rest = [_row("1234567002", 85.0, label=CohortLabel.REST)]
    combined, _, _ = write_cohort_md(low, rest, tmp_path)
    text = combined.read_text(encoding="utf-8")
    assert "## 저득점" in text
    assert "## 나머지" in text
    assert "1234567001" in text
    assert "1234567002" in text


def test_score_format_one_decimal(tmp_path: Path) -> None:
    low = [_row("1234567001", 59.949, label=CohortLabel.LOW_SCORE)]
    rest = []
    combined, low_path, _ = write_cohort_md(low, rest, tmp_path)
    text = combined.read_text(encoding="utf-8")
    # 59.949 → "59.9" (one decimal, banker's rounding via .1f)
    assert "59.9" in text
    assert "59.949" not in text


def test_low_md_contains_low_only(tmp_path: Path) -> None:
    low = [_row("1234567001", 45.0, label=CohortLabel.LOW_SCORE)]
    rest = [_row("1234567002", 85.0, label=CohortLabel.REST)]
    _, low_path, rest_path = write_cohort_md(low, rest, tmp_path)
    low_text = low_path.read_text(encoding="utf-8")
    rest_text = rest_path.read_text(encoding="utf-8")
    assert "1234567001" in low_text
    assert "1234567002" not in low_text
    assert "1234567002" in rest_text
    assert "1234567001" not in rest_text


def test_empty_cohort_renders_placeholder(tmp_path: Path) -> None:
    combined, _, _ = write_cohort_md([], [], tmp_path)
    text = combined.read_text(encoding="utf-8")
    assert "(해당 학생 없음)" in text


def test_sorted_by_student_id(tmp_path: Path) -> None:
    low = [
        _row("1234567003", 40.0, label=CohortLabel.LOW_SCORE),
        _row("1234567001", 30.0, label=CohortLabel.LOW_SCORE),
        _row("1234567002", 50.0, label=CohortLabel.LOW_SCORE),
    ]
    # Caller pre-sorts (filter_by_cohort does this); writer trusts input order
    low.sort(key=lambda r: r.student_id)
    combined, _, _ = write_cohort_md(low, [], tmp_path)
    text = combined.read_text(encoding="utf-8")
    pos_001 = text.find("1234567001")
    pos_002 = text.find("1234567002")
    pos_003 = text.find("1234567003")
    assert pos_001 < pos_002 < pos_003
