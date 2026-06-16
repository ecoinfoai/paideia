"""Test — T069 exam yaml list root support (spec 004 V3 fix).

Production exam yamls (`data/bronze/시험문제/*.yaml`) land as a bare
list of question dicts; the spec-contract form is a mapping with an
``items`` key. Both layouts must yield identical ExamItem lists.
"""

from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import pytest
import yaml

_spec = _ilu.spec_from_file_location(
    "exam_yaml_isolated",
    Path(__file__).resolve().parents[2] / "src" / "immersio" / "io" / "exam_yaml.py",
)
_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
parse_exam_yaml = _mod.parse_exam_yaml


_QUESTION_DICTS = [
    {
        "item_no": 1,
        "chapter": "1장",
        "answer_key": "B",
        "text": "Q1 text",
        "distractors": ["A", "C", "D", "E"],
    },
    {
        "item_no": 2,
        "chapter": "2장",
        "answer_key": "A",
        "text": "Q2 text",
        "distractors": ["B", "C", "D", "E"],
    },
]


def _write_list_root(path: Path) -> None:
    path.write_text(yaml.safe_dump(_QUESTION_DICTS, allow_unicode=True), encoding="utf-8")


def _write_mapping_root(path: Path) -> None:
    path.write_text(
        yaml.safe_dump({"items": _QUESTION_DICTS}, allow_unicode=True),
        encoding="utf-8",
    )


def test_list_root_accepted(tmp_path: Path) -> None:
    yaml_path = tmp_path / "list_root.yaml"
    _write_list_root(yaml_path)
    items = parse_exam_yaml(yaml_path, "2026-1", "anatomy")
    assert len(items) == 2
    assert items[0].item_no == 1
    assert items[1].item_no == 2


def test_mapping_root_still_accepted(tmp_path: Path) -> None:
    yaml_path = tmp_path / "mapping_root.yaml"
    _write_mapping_root(yaml_path)
    items = parse_exam_yaml(yaml_path, "2026-1", "anatomy")
    assert len(items) == 2


def test_list_and_mapping_yield_identical_items(tmp_path: Path) -> None:
    list_yaml = tmp_path / "list.yaml"
    map_yaml = tmp_path / "map.yaml"
    _write_list_root(list_yaml)
    _write_mapping_root(map_yaml)
    items_list = parse_exam_yaml(list_yaml, "2026-1", "anatomy")
    items_map = parse_exam_yaml(map_yaml, "2026-1", "anatomy")
    # Same shape, same field values.
    assert [it.model_dump() for it in items_list] == [it.model_dump() for it in items_map]


def test_neither_layout_rejected(tmp_path: Path) -> None:
    yaml_path = tmp_path / "scalar.yaml"
    yaml_path.write_text("just a string\n", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level"):
        parse_exam_yaml(yaml_path, "2026-1", "anatomy")


def test_empty_list_root_rejected(tmp_path: Path) -> None:
    yaml_path = tmp_path / "empty.yaml"
    yaml_path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        parse_exam_yaml(yaml_path, "2026-1", "anatomy")
