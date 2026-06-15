"""T015: loader for silver `manifest_examen.json` → (ExamenBlueprint, CurriculumMap).

The JSON file stores two model_dump dicts under keys ``blueprint`` and
``curriculum_entries`` (parallel to the ``_compute_run_id`` payload in
``modules/examen/src/examen/pipeline.py``).  Both are reconstructed via
Pydantic ``model_validate`` and then cross-checked against the requested
``semester``/``course_slug`` key.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from paideia_shared.schemas import CurriculumMap, ExamenBlueprint

from .errors import InputError


def load_examen_manifest(
    path: Path,
    semester: str,
    course_slug: str,
) -> tuple[ExamenBlueprint, CurriculumMap]:
    """Load ``manifest_examen.json`` and reconstruct blueprint + curriculum.

    Args:
        path: Absolute path to the manifest JSON file.
        semester: Expected semester code (e.g. ``"2026-1"``).
        course_slug: Expected course slug (e.g. ``"anatomy"``).

    Returns:
        A (blueprint, curriculum_map) tuple of validated Pydantic instances.

    Raises:
        InputError: If the file does not exist, required JSON keys are absent,
            Pydantic validation fails, or the loaded ``semester``/``course_slug``
            does not match the requested key.
    """
    if not path.exists():
        raise InputError(f"Examen manifest not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise InputError(f"Failed to read examen manifest {path}: {exc}") from exc

    if "blueprint" not in payload:
        raise InputError(f"Examen manifest {path} is missing key 'blueprint'")
    if "curriculum_entries" not in payload:
        raise InputError(f"Examen manifest {path} is missing key 'curriculum_entries'")

    try:
        blueprint = ExamenBlueprint.model_validate(payload["blueprint"])
    except ValidationError as exc:
        raise InputError(f"ExamenBlueprint validation failed in {path}: {exc}") from exc

    try:
        curriculum = CurriculumMap.model_validate(payload["curriculum_entries"])
    except ValidationError as exc:
        raise InputError(f"CurriculumMap validation failed in {path}: {exc}") from exc

    # Cross-check semester and course_slug.
    if blueprint.semester != semester:
        raise InputError(
            f"Blueprint semester mismatch in {path}: "
            f"expected '{semester}', got '{blueprint.semester}'"
        )
    if blueprint.course_slug != course_slug:
        raise InputError(
            f"Blueprint course_slug mismatch in {path}: "
            f"expected '{course_slug}', got '{blueprint.course_slug}'"
        )

    return blueprint, curriculum


__all__ = ["load_examen_manifest"]
