"""US2: mapping YAML referencing a column absent from the diagnostic CSV."""

from __future__ import annotations

from pathlib import Path

import pytest

from immersio.ingest import IngestValidationError, run_ingest


def test_mapping_missing_column(corrupt_bronze: Path, corrupt_mapping: Path, tmp_path: Path) -> None:
    text = corrupt_mapping.read_text(encoding="utf-8")
    bad = text.replace('source: "Q05_나는_시험이_두렵다"', 'source: "Q99_없는_컬럼"')
    corrupt_mapping.write_text(bad, encoding="utf-8")

    out = tmp_path / "silver"
    with pytest.raises(IngestValidationError) as exc:
        run_ingest(
            bronze_dir=corrupt_bronze,
            mapping_path=corrupt_mapping,
            output_dir=out,
            no_git_commit=True,
        )
    rendered = str(exc.value)
    assert "Q99_없는_컬럼" in rendered or "mapping references columns absent" in rendered
    assert not (out / "2026-1-anatomy").exists()
