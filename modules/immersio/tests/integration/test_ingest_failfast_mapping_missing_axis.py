"""US2: mapping declares a required axis that no column maps to."""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.ingest import IngestValidationError, run_ingest


def test_required_axis_unmapped(
    corrupt_bronze: Path, corrupt_mapping: Path, tmp_path: Path
) -> None:
    text = corrupt_mapping.read_text(encoding="utf-8")
    bad = text.replace(
        "    - interest\n",
        "    - interest\n    - missing_axis\n",
    )
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
    assert "missing_axis" in rendered or "V3" in rendered
    assert not (out / "2026-1-anatomy").exists()
