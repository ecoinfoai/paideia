"""T015: loaders for retro-mester's own Bronze blueprint + curriculum YAMLs.

retro-mester does NOT read another module's Silver/Gold for the exam
specification: examen never persists the blueprint/curriculum to Silver
(its Gold ``manifest_examen.json`` is an ``ExamenManifest`` and carries
neither).  Instead the professor places copies under retro-mester's own
Bronze tier:

- ``data/bronze/retro-mester/{key}/blueprint.yaml``       → ExamenBlueprint
- ``data/bronze/retro-mester/{key}/curriculum_map.yaml``  → CurriculumMap

Both are parsed with ``yaml.safe_load`` and validated via Pydantic, then
cross-checked against the requested ``semester``/``course_slug`` key.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from paideia_shared.schemas import CurriculumMap, ExamenBlueprint

from .errors import InputError


def load_blueprint(path: Path) -> ExamenBlueprint:
    """Load and validate ``blueprint.yaml`` from retro-mester's Bronze tier.

    Args:
        path: Absolute path to the blueprint.yaml file.

    Returns:
        Validated ExamenBlueprint instance.

    Raises:
        InputError: If the file does not exist, YAML parsing fails, the
            content is not a mapping, or Pydantic validation fails.
    """
    if not path.exists():
        raise InputError(f"blueprint.yaml not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InputError(f"Failed to parse blueprint.yaml at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise InputError(
            f"blueprint.yaml must be a YAML mapping, got {type(raw).__name__}: {path}"
        )

    try:
        return ExamenBlueprint(**raw)
    except ValidationError as exc:
        raise InputError(f"blueprint.yaml validation failed at {path}: {exc}") from exc


def load_curriculum_map(path: Path) -> CurriculumMap:
    """Load and validate ``curriculum_map.yaml`` from retro-mester's Bronze tier.

    Args:
        path: Absolute path to the curriculum_map.yaml file.

    Returns:
        Validated CurriculumMap instance.

    Raises:
        InputError: If the file does not exist, YAML parsing fails, the
            content is not a mapping, or Pydantic validation fails.
    """
    if not path.exists():
        raise InputError(f"curriculum_map.yaml not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InputError(f"Failed to parse curriculum_map.yaml at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise InputError(
            f"curriculum_map.yaml must be a YAML mapping, got {type(raw).__name__}: {path}"
        )

    try:
        return CurriculumMap(**raw)
    except ValidationError as exc:
        raise InputError(
            f"curriculum_map.yaml validation failed at {path}: {exc}"
        ) from exc


def load_exam_spec(
    blueprint_path: Path,
    curriculum_map_path: Path,
    semester: str,
    course_slug: str,
) -> tuple[ExamenBlueprint, CurriculumMap]:
    """Load the blueprint + curriculum pair and cross-check the key.

    Args:
        blueprint_path: Path to ``blueprint.yaml`` (retro-mester Bronze).
        curriculum_map_path: Path to ``curriculum_map.yaml`` (retro-mester Bronze).
        semester: Expected semester code (e.g. ``"2026-1"``).
        course_slug: Expected course slug (e.g. ``"anatomy"``).

    Returns:
        A (blueprint, curriculum_map) tuple of validated Pydantic instances.

    Raises:
        InputError: If either file is missing/malformed, validation fails, or
            the loaded ``semester``/``course_slug`` does not match the
            requested key.
    """
    blueprint = load_blueprint(blueprint_path)
    curriculum = load_curriculum_map(curriculum_map_path)

    if blueprint.semester != semester:
        raise InputError(
            f"Blueprint semester mismatch in {blueprint_path}: "
            f"expected '{semester}', got '{blueprint.semester}'"
        )
    if blueprint.course_slug != course_slug:
        raise InputError(
            f"Blueprint course_slug mismatch in {blueprint_path}: "
            f"expected '{course_slug}', got '{blueprint.course_slug}'"
        )
    if curriculum.semester != semester:
        raise InputError(
            f"Curriculum semester mismatch in {curriculum_map_path}: "
            f"expected '{semester}', got '{curriculum.semester}'"
        )
    if curriculum.course_slug != course_slug:
        raise InputError(
            f"Curriculum course_slug mismatch in {curriculum_map_path}: "
            f"expected '{course_slug}', got '{curriculum.course_slug}'"
        )

    return blueprint, curriculum


__all__ = ["load_blueprint", "load_curriculum_map", "load_exam_spec"]
