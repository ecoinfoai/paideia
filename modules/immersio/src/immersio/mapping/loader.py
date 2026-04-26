"""Diagnostic mapping YAML loader."""

from __future__ import annotations

from pathlib import Path

import yaml
from paideia_shared.schemas import DiagnosticMappingConfig


def load_mapping(path: Path) -> DiagnosticMappingConfig:
    """Load a diagnostic mapping YAML and validate it against the contract.

    Args:
        path: Path to the mapping YAML file.

    Returns:
        Validated DiagnosticMappingConfig instance.

    Raises:
        TypeError: If path is not a pathlib.Path.
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If YAML parsing fails (line/column included by PyYAML).
        pydantic.ValidationError: If schema validation fails.
    """
    if not isinstance(path, Path):
        raise TypeError(
            f"load_mapping: expected pathlib.Path, got {type(path).__name__}."
        )
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"load_mapping: expected top-level mapping in {path}, got "
            f"{type(data).__name__}."
        )
    return DiagnosticMappingConfig.model_validate(data)
