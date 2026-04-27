"""Unit tests for the mapping YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from immersio.mapping import load_mapping
from paideia_shared.schemas import DiagnosticMappingConfig
from pydantic import ValidationError

_VALID_MAPPING_YAML = """\
metadata:
  semester: "2026-1"
  course_slug: anatomy
  course_name_kr: "인체구조와기능"
  mapping_version: 2
columns:
  - source: "학번"
    kind: identity
  - source: "Q_digital_efficacy"
    axis: digital_efficacy
    kind: likert
  - source: "Q01_나는_의학에_관심이_많다"
    axis: motivation
    kind: likert
  - source: "Q_time_availability"
    axis: time_availability
    kind: likert
  - source: "Q_material_preference"
    axis: material_preference
    kind: likert
  - source: "Q_study_strategy"
    axis: study_strategy
    kind: likert
  - source: "Q_study_environment"
    axis: study_environment
    kind: likert
  - source: "Q_social_learning"
    axis: social_learning
    kind: likert
  - source: "Q_feedback_seeking"
    axis: feedback_seeking
    kind: likert
  - source: "Q11_관심있는_챕터"
    axis: interest_topics
    kind: multiselect
axes:
  required:
    - digital_efficacy
    - motivation
    - time_availability
    - material_preference
    - study_strategy
    - study_environment
    - social_learning
    - feedback_seeking
  optional:
    - interest_topics
"""


def _write_yaml(tmp_path: Path, content: str, name: str = "m.yaml") -> Path:
    target = tmp_path / name
    target.write_text(content, encoding="utf-8")
    return target


def test_loader_positive(tmp_path: Path) -> None:
    target = _write_yaml(tmp_path, _VALID_MAPPING_YAML)
    config = load_mapping(target)
    assert isinstance(config, DiagnosticMappingConfig)
    assert config.metadata.course_slug == "anatomy"
    assert {c.axis for c in config.columns if c.axis} == {
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
        "interest_topics",
    }


def test_loader_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mapping(tmp_path / "missing.yaml")


def test_loader_yaml_error(tmp_path: Path) -> None:
    target = _write_yaml(tmp_path, "metadata: { unterminated:\n")
    with pytest.raises(yaml.YAMLError):
        load_mapping(target)


def test_loader_two_identity_columns(tmp_path: Path) -> None:
    payload = _VALID_MAPPING_YAML.replace(
        '  - source: "학번"\n    kind: identity\n',
        '  - source: "학번"\n    kind: identity\n  - source: "ID"\n    kind: identity\n',
    )
    target = _write_yaml(tmp_path, payload)
    with pytest.raises(ValidationError, match="V2"):
        load_mapping(target)


def test_loader_required_axis_unmapped(tmp_path: Path) -> None:
    """V3 fires when a declared required axis has no backing column.

    Replace the feedback_seeking column with an unmapped one to keep
    axes.required at 8 (V6 strict) but break V3.
    """
    payload = _VALID_MAPPING_YAML.replace(
        "    - feedback_seeking\n",
        "    - missing_axis\n",
    ).replace(
        '  - source: "Q_feedback_seeking"\n    axis: feedback_seeking\n    kind: likert\n',
        "",
    )
    target = _write_yaml(tmp_path, payload)
    with pytest.raises(ValidationError, match="V3"):
        load_mapping(target)


def test_loader_inconsistent_aggregate(tmp_path: Path) -> None:
    payload = _VALID_MAPPING_YAML.replace(
        '  - source: "Q01_나는_의학에_관심이_많다"\n    axis: motivation\n    kind: likert\n',
        (
            '  - source: "Q01_나는_의학에_관심이_많다"\n    axis: motivation\n'
            "    kind: likert\n    aggregate: mean\n"
            '  - source: "Q02_나는_간호사가_되고_싶다"\n    axis: motivation\n'
            "    kind: likert\n"
        ),
    )
    target = _write_yaml(tmp_path, payload)
    with pytest.raises(ValidationError, match="V4"):
        load_mapping(target)


def test_loader_path_type_check() -> None:
    with pytest.raises(TypeError, match="pathlib.Path"):
        load_mapping("/tmp/x.yaml")  # type: ignore[arg-type]
