"""US2: exam YAML schema violation (missing answer_key)."""

from __future__ import annotations

from pathlib import Path

import pytest

from immersio.ingest import IngestValidationError, run_ingest


def test_exam_yaml_missing_answer_key(corrupt_bronze: Path, corrupt_mapping: Path, tmp_path: Path) -> None:
    target = corrupt_bronze / "시험문제" / "실제_출제문제.yaml"
    text = target.read_text(encoding="utf-8")
    bad = text.replace('answer_key: "3"', "", 1)  # remove first answer_key
    target.write_text(bad, encoding="utf-8")

    out = tmp_path / "silver"
    with pytest.raises(IngestValidationError) as exc:
        run_ingest(
            bronze_dir=corrupt_bronze,
            mapping_path=corrupt_mapping,
            output_dir=out,
            no_git_commit=True,
        )
    rendered = str(exc.value)
    assert "answer_key" in rendered or "Field required" in rendered
    assert not (out / "2026-1-anatomy").exists()
