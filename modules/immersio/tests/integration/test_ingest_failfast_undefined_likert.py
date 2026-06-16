"""US2: undefined Likert text triggers IngestValidationError + zero outputs."""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.ingest import IngestValidationError, run_ingest


def test_undefined_likert_blocks_silver(
    corrupt_bronze: Path, corrupt_mapping: Path, tmp_path: Path
) -> None:
    diag_csv = corrupt_bronze / "진단평가" / "diag_test.csv"
    text = diag_csv.read_text(encoding="utf-8")
    bad_text = text.replace("매우 그렇다", "매우 좋아요", 1)
    diag_csv.write_text(bad_text, encoding="utf-8")

    out = tmp_path / "silver"
    with pytest.raises(IngestValidationError) as exc:
        run_ingest(
            bronze_dir=corrupt_bronze,
            mapping_path=corrupt_mapping,
            output_dir=out,
            no_git_commit=True,
        )

    rendered = str(exc.value)
    assert "매우 좋아요" in rendered or "undefined Likert" in rendered
    assert not out.exists() or not (out / "2026-1-anatomy").exists()
