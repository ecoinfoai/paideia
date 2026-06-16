"""T049 — RED tests for `analyze/silver_writer.py::write_student_metrics_parquet` (FR-018).

Round-trip property: write `학생지표.parquet` → read back via pyarrow →
StudentExamMetrics field equality. snappy compression + 학번 정렬 +
deterministic file bytes for two consecutive writes (FR-023 axis).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest
from immersio.analyze.silver_writer import write_student_metrics_parquet
from paideia_shared.schemas import StudentExamMetrics


def _metric(
    student_id: str,
    *,
    exam_taken: bool,
    score: float | None = None,
    section: str = "A",
    name_kr: str = "테스트",
) -> StudentExamMetrics:
    if exam_taken:
        return StudentExamMetrics(
            student_id=student_id,
            name_kr=name_kr,
            section=section,
            semester="2026-1",
            course_slug="anatomy",
            exam_taken=True,
            total_score=score,
            score_percent=(score / 4.0 * 100.0) if score is not None else None,
            section_percentile=50.0,
            cohort_percentile=50.0,
            z_score=0.0,
            chapter_correct_rates={"1장. 서론": 0.75},
            source_correct_rates={"교과서": 0.5},
            difficulty_correct_rates={2: 0.6},
            expected_difficulty_correct_rates={"보통": 0.6},
            item_type_correct_rates={"지식축적": 0.6},
        )
    return StudentExamMetrics(
        student_id=student_id,
        name_kr=name_kr,
        section=section,
        semester="2026-1",
        course_slug="anatomy",
        exam_taken=False,
    )


def _stub_metrics() -> list[StudentExamMetrics]:
    return [
        _metric("2026100003", exam_taken=True, score=3.0),
        _metric("2026100001", exam_taken=True, score=4.0),
        _metric("2026100002", exam_taken=False),
    ]


def test_writes_parquet_file(tmp_path: Path) -> None:
    out = tmp_path / "학생지표.parquet"
    write_student_metrics_parquet(rows=_stub_metrics(), output_path=out)
    assert out.is_file()
    assert out.stat().st_size > 0


def test_round_trip_preserves_fields(tmp_path: Path) -> None:
    out = tmp_path / "학생지표.parquet"
    write_student_metrics_parquet(rows=_stub_metrics(), output_path=out)
    df = pd.read_parquet(out)
    # rows sorted by student_id ascending
    sids = df["student_id"].tolist()
    assert sids == sorted(sids)
    # taker row carries score, absent carries NaN/None
    by_id = df.set_index("student_id")
    assert (
        by_id.loc["2026100001", "exam_taken"] is True or by_id.loc["2026100001", "exam_taken"] == 1
    )
    assert by_id.loc["2026100001", "total_score"] == 4.0
    absent_score = by_id.loc["2026100002", "total_score"]
    assert absent_score is None or pd.isna(absent_score)


def test_two_writes_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    write_student_metrics_parquet(rows=_stub_metrics(), output_path=a)
    write_student_metrics_parquet(rows=_stub_metrics(), output_path=b)
    sha_a = hashlib.sha256(a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(b.read_bytes()).hexdigest()
    assert sha_a == sha_b, "parquet bytes diverge across two identical writes"


def test_dict_columns_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "x.parquet"
    write_student_metrics_parquet(rows=_stub_metrics(), output_path=out)
    df = pd.read_parquet(out)
    by_id = df.set_index("student_id")
    raw = by_id.loc["2026100001", "chapter_correct_rates"]
    # dict values may be encoded as JSON string or as a struct depending
    # on the writer's chosen serialisation. Either way the value must be
    # recoverable as ``{"1장. 서론": 0.75}``.
    if isinstance(raw, str):
        import json

        decoded = json.loads(raw)
    elif hasattr(raw, "items"):
        decoded = dict(raw)
    else:
        decoded = raw
    assert decoded["1장. 서론"] == 0.75


def test_rejects_empty_rows(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_student_metrics_parquet(rows=[], output_path=tmp_path / "x.parquet")
