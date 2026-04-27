"""Mapping YAML loader for needs-map (T021).

Reads a course-specific ``{course}.diagnostic.yaml`` and returns a validated
``DiagnosticMappingConfig``. V1-V6 validators (V5 partition_axis × freetext,
V6 standard vocabulary) raise ValidationError with the offending axis name so
downstream phases can refuse to proceed (FR-001, FR-AXIS-001).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from paideia_shared.schemas import DiagnosticMappingConfig
from pydantic import ValidationError


def load_mapping(path: Path) -> DiagnosticMappingConfig:
    """Load a mapping YAML and run all 6 validators.

    Args:
        path: Filesystem path to the ``{course}.diagnostic.yaml`` file.

    Returns:
        Validated :class:`DiagnosticMappingConfig` instance.

    Raises:
        FileNotFoundError: If the file does not exist (message includes path).
        ValueError: If the YAML body is not a mapping at top level
            (message includes path).
        yaml.YAMLError: On malformed YAML (line/column embedded by PyYAML).
        pydantic.ValidationError: On schema/validator violations
            (message preserves V1-V6 prefix and offending axis or column).
    """
    if not isinstance(path, Path):
        raise TypeError(
            f"load_mapping: expected pathlib.Path, got {type(path).__name__}."
        )
    if not path.is_file():
        raise FileNotFoundError(f"Mapping YAML not found: {path}")

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"load_mapping: expected top-level mapping in {path}, got "
            f"{type(data).__name__}."
        )
    try:
        return DiagnosticMappingConfig.model_validate(data)
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            title=f"DiagnosticMappingConfig load failed for {path}",
            line_errors=exc.errors(),  # type: ignore[arg-type]
        ) from exc
