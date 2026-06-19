"""Shared YAML-mapping loader for metric-codex Bronze/config inputs.

Centralises the exists → safe_load → isinstance(dict) boundary-validation
boilerplate so every YAML caller (``ingest/bronze_copies.py``,
``retrieve/query.py``) raises a consistent ``LocatedInputError``. Each caller
keeps its own Pydantic-validation step after obtaining the raw mapping.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from metric_codex.errors import LocatedInputError


def load_yaml_mapping(path: Path, label: str) -> dict:
    """Read a YAML file and return its top-level mapping.

    Args:
        path: Absolute path to the YAML file.
        label: Human-readable file label for error messages (e.g.
            ``"blueprint.yaml"``).

    Returns:
        The parsed top-level mapping as a ``dict``.

    Raises:
        LocatedInputError: If the file does not exist, YAML parsing fails,
            or the parsed content is not a mapping.
    """
    if not path.exists():
        raise LocatedInputError(f"{label} not found", file=str(path))

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LocatedInputError(f"Failed to parse YAML: {exc}", file=str(path)) from exc

    if not isinstance(raw, dict):
        raise LocatedInputError(
            f"{label} must be a YAML mapping, got {type(raw).__name__}",
            file=str(path),
        )

    return raw


__all__ = ["load_yaml_mapping"]
