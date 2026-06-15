"""T016: loader and reconciler for Bronze `retro_config.yaml` → RetroMesterConfig.

Two public functions:
- ``load_config(path) -> RetroMesterConfig``: pure parse + Pydantic validation.
- ``reconcile_config(config, chapters, student_ids) -> ConfigReconcileReport``:
    cross-file key checks without touching the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import yaml
from pydantic import ValidationError

from paideia_shared.schemas import RetroMesterConfig

from .errors import InputError


class ConfigReconcileReport(TypedDict):
    """Outcome of cross-file reconciliation for RetroMesterConfig."""

    unclassified_students: list[str]
    """group_roster student IDs not present in the loaded combined-analysis student set."""


def load_config(path: Path) -> RetroMesterConfig:
    """Parse and validate ``retro_config.yaml``.

    Args:
        path: Absolute path to the YAML config file.

    Returns:
        Validated RetroMesterConfig instance.

    Raises:
        InputError: If the file does not exist, YAML parsing fails, or
            Pydantic schema validation fails.
    """
    if not path.exists():
        raise InputError(f"Retro-mester config not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InputError(f"YAML parse error in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise InputError(f"Config file {path} must be a YAML mapping; got {type(raw).__name__}")

    try:
        return RetroMesterConfig.model_validate(raw)
    except ValidationError as exc:
        raise InputError(f"Config validation failed in {path}: {exc}") from exc


def reconcile_config(
    config: RetroMesterConfig,
    chapters: set[str],
    student_ids: set[str],
) -> ConfigReconcileReport:
    """Cross-check config keys against loaded chapter and student sets.

    Rules:
    - ``unit_importance`` keys must be a subset of ``chapters``;
      any extraneous key raises InputError.
    - ``effort_ratings`` keys may be ``"chapter"`` or ``"chapter|segment"``
      form; the chapter part (before ``|``) must be a subset of ``chapters``;
      any extraneous chapter raises InputError.
    - ``group_roster`` student IDs not in ``student_ids`` are collected and
      returned as ``unclassified_students``; this does NOT raise.

    Args:
        config: Validated RetroMesterConfig.
        chapters: Chapter label set from the loaded ExamenBlueprint or
            CurriculumMap (``blueprint.chapters`` or
            ``{e.chapter for e in curriculum.entries}``).
        student_ids: Student ID set from the loaded CombinedAnalysisRow list.

    Returns:
        ConfigReconcileReport with ``unclassified_students`` list.

    Raises:
        InputError: If any ``unit_importance`` key or any chapter part of
            an ``effort_ratings`` key is not in ``chapters``.
    """
    # Check unit_importance keys.
    extra_importance = set(config.unit_importance.keys()) - chapters
    if extra_importance:
        raise InputError(
            f"unit_importance contains chapter keys not in the loaded chapter set: "
            f"{sorted(extra_importance)}"
        )

    # Check effort_ratings keys (support "chapter" or "chapter|segment" form).
    extra_effort: set[str] = set()
    for key in config.effort_ratings:
        chapter_part = key.split("|", 1)[0]
        if chapter_part not in chapters:
            extra_effort.add(key)
    if extra_effort:
        raise InputError(
            f"effort_ratings contains chapter keys not in the loaded chapter set: "
            f"{sorted(extra_effort)}"
        )

    # Collect unclassified students (do NOT raise).
    unclassified = sorted(
        sid for sid in config.group_roster if sid not in student_ids
    )

    return ConfigReconcileReport(unclassified_students=unclassified)


__all__ = ["load_config", "reconcile_config", "ConfigReconcileReport"]
