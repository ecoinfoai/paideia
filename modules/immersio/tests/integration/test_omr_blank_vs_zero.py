"""ExamResult must distinguish blank cells (None) from a literal '0' response."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from immersio.ingest import run_ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRONZE = FIXTURES / "bronze_minimal"
MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"


def test_blank_vs_zero_preserved(tmp_path: Path) -> None:
    """Fixture _build_omr_xls.py seeds student 2026000003 with response '0'
    on item 4, and student 2026099002 with a blank cell on item 5. Both
    semantics must survive into the Silver Parquet."""
    out = tmp_path / "silver"
    run_ingest(
        bronze_dir=BRONZE,
        mapping_path=MAPPING,
        output_dir=out,
        no_git_commit=True,
    )
    exam = pd.read_parquet(out / "2026-1-anatomy" / "exam_result.parquet")

    student_c = exam[(exam["student_id"] == "2026000003") & (exam["item_no"] == 4)]
    assert not student_c.empty, "expected ExamResult row for student C item 4"
    assert student_c.iloc[0]["response"] == "0"
    assert bool(student_c.iloc[0]["is_correct"]) is False

    student_g = exam[(exam["student_id"] == "2026099002") & (exam["item_no"] == 5)]
    assert not student_g.empty, "expected ExamResult row for student G item 5"
    assert student_g.iloc[0]["response"] is None or pd.isna(student_g.iloc[0]["response"])
    assert student_g.iloc[0]["is_correct"] is None or pd.isna(student_g.iloc[0]["is_correct"])
