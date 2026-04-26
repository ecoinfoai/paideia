"""US2: exam YAML defines more items than the OMR sheet records (T058b)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from immersio.ingest import IngestValidationError, run_ingest


def test_yaml_has_more_items_than_omr(
    corrupt_bronze: Path, corrupt_mapping: Path, tmp_path: Path
) -> None:
    yaml_path = corrupt_bronze / "시험문제" / "실제_출제문제.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    data["items"].append(
        {
            "item_no": 99,
            "chapter": "Z장",
            "source": "textbook",
            "expected_difficulty": "easy",
            "bloom": "knowledge",
            "answer_key": "1",
            "points": 1.0,
            "text": "synthetic mismatch item",
        }
    )
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    out = tmp_path / "silver"
    with pytest.raises(IngestValidationError) as exc:
        run_ingest(
            bronze_dir=corrupt_bronze,
            mapping_path=corrupt_mapping,
            output_dir=out,
            no_git_commit=True,
        )
    rendered = str(exc.value)
    assert "item_no coverage" in rendered or "item_nos" in rendered
    assert not (out / "2026-1-anatomy").exists()
