"""T005 — write_student_metrics_parquet must produce owner-only (0o600) parquet.

Security requirement: 학생지표.parquet carries student PII
(student_id, name_kr, metrics) and must never be world-readable (DAR-01 / SC-006).
"""

from __future__ import annotations

from pathlib import Path

from immersio.analyze.silver_writer import write_student_metrics_parquet
from paideia_shared.schemas import StudentExamMetrics


def _stub_metrics() -> list[StudentExamMetrics]:
    return [
        StudentExamMetrics(
            student_id="2026100001",
            name_kr="테스트",
            section="A",
            semester="2026-1",
            course_slug="anatomy",
            exam_taken=True,
            total_score=4.0,
            score_percent=100.0,
            section_percentile=50.0,
            cohort_percentile=50.0,
            z_score=0.0,
            chapter_correct_rates={"1장": 0.75},
            source_correct_rates={"교과서": 0.5},
            difficulty_correct_rates={2: 0.6},
            expected_difficulty_correct_rates={"보통": 0.6},
            item_type_correct_rates={"지식축적": 0.6},
        )
    ]


def test_student_metrics_parquet_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """DAR-01: 학생지표.parquet must be chmod 0o600 (no group/other bits)."""
    out = tmp_path / "학생지표.parquet"
    write_student_metrics_parquet(rows=_stub_metrics(), output_path=out)
    assert_owner_only(out)
