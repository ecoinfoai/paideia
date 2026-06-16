"""T017 — Config loader: generation_spec.yaml and curriculum_map.yaml.

Parses YAML inputs and validates them against the shared Pydantic schemas.
Fail-fast on any validation error: raises with the offending file path and a
located error message (constitution III — variability via config, no silent
defaults).

Public API
----------
``load_generation_spec(path) -> MaieuticaGenerationSpec``
    Load and validate generation_spec.yaml.

``load_curriculum_map(path) -> CurriculumMap``
    Load and validate curriculum_map.yaml.

``validate_week_in_map(cm, week, curriculum_map_path) -> None``
    Fail-fast check: target week must be present in the curriculum map.
    Raises ``ValueError`` with the week number and file path if absent.

``resolve_chapter_txt(bronze_dir, chapter_no) -> Path``
    Locate the chapter .txt file in ``bronze_dir``.  Matching rule: filename
    stem contains ``{N}장`` (lenient — covers "8장 호흡계통.txt" etc.).
    Raises ``FileNotFoundError`` naming the directory and chapter_no if absent.

Example::

    from maieutica.ingest.spec_load import (
        load_generation_spec,
        load_curriculum_map,
        validate_week_in_map,
        resolve_chapter_txt,
    )

    spec = load_generation_spec(Path("bronze/generation_spec.yaml"))
    cm   = load_curriculum_map(Path("bronze/curriculum_map.yaml"))
    validate_week_in_map(cm, spec.week, curriculum_map_path=Path("curriculum_map.yaml"))
    txt  = resolve_chapter_txt(bronze_dir=Path("bronze"), chapter_no=spec.chapter_no)
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from paideia_shared.schemas import CurriculumMap, MaieuticaGenerationSpec
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# generation_spec.yaml loader
# ---------------------------------------------------------------------------


def load_generation_spec(path: Path) -> MaieuticaGenerationSpec:
    """Load and validate a generation_spec.yaml file.

    Args:
        path: Absolute or relative path to the generation_spec.yaml file.

    Returns:
        Validated MaieuticaGenerationSpec instance.

    Raises:
        FileNotFoundError: If ``path`` does not exist. Message includes the path.
        ValueError: If YAML is malformed or content fails schema validation.
            Message always includes the file path and the offending field.
    """
    if not path.exists():
        raise FileNotFoundError(f"generation_spec.yaml not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse generation_spec.yaml at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"generation_spec.yaml must be a YAML mapping, got {type(raw).__name__}: {path}"
        )

    try:
        return MaieuticaGenerationSpec.model_validate(raw)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(f"generation_spec.yaml validation failed at {path}: {errors}") from exc


# ---------------------------------------------------------------------------
# curriculum_map.yaml loader
# ---------------------------------------------------------------------------


def load_curriculum_map(path: Path) -> CurriculumMap:
    """Load and validate a curriculum_map.yaml file.

    Args:
        path: Absolute or relative path to the curriculum_map.yaml file.

    Returns:
        Validated CurriculumMap instance.

    Raises:
        FileNotFoundError: If ``path`` does not exist. Message includes the path.
        ValueError: If YAML is malformed or content fails schema validation.
            Message always includes the file path and the offending field.
    """
    if not path.exists():
        raise FileNotFoundError(f"curriculum_map.yaml not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse curriculum_map.yaml at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"curriculum_map.yaml must be a YAML mapping, got {type(raw).__name__}: {path}"
        )

    try:
        return CurriculumMap.model_validate(raw)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(f"curriculum_map.yaml validation failed at {path}: {errors}") from exc


# ---------------------------------------------------------------------------
# Week-presence validator (fail-fast — CLI maps to exit 2)
# ---------------------------------------------------------------------------


def validate_week_in_map(
    cm: CurriculumMap,
    week: int,
    *,
    curriculum_map_path: Path,
) -> None:
    """Verify that ``week`` exists in the curriculum map.

    Iterates ``cm.entries`` looking for any entry whose ``week`` equals the
    target.  If absent, raises ``ValueError`` with a message that names both
    the missing week and the source file (constitution III: error messages
    must include expected vs actual context).

    Args:
        cm: Validated CurriculumMap instance.
        week: Target week number (1-based) from the generation spec.
        curriculum_map_path: Path of the curriculum_map.yaml (used in the
            error message only).

    Raises:
        ValueError: If ``week`` is not present in any entry of ``cm``.
            Message includes the week number and the file path.  ValueError is
            used (not KeyError) for consistency with the module's other
            config-validation errors.
    """
    present_weeks = {entry.week for entry in cm.entries}
    if week not in present_weeks:
        raise ValueError(
            f"Week {week} not found in curriculum map '{curriculum_map_path}'. "
            f"Available weeks: {sorted(present_weeks)}"
        )


# ---------------------------------------------------------------------------
# Chapter .txt resolver (fail-fast — CLI maps to exit 2)
# ---------------------------------------------------------------------------


def _chapter_file_pattern(chapter_no: int) -> re.Pattern[str]:
    """Return a compiled regex that matches a filename stem for ``chapter_no``.

    Matching rule: the stem must contain ``{N}장`` where ``N`` is the chapter
    number, not immediately preceded by another digit.  Examples (chapter_no=8):

    - "8장 호흡계통"  → match
    - "8장"           → match
    - "18장"          → NO match (leading ``1`` is a digit before ``8장``)
    """
    n = str(chapter_no)
    return re.compile(rf"(?:^|(?<=\D)){re.escape(n)}장")


def resolve_chapter_txt(bronze_dir: Path, chapter_no: int) -> Path:
    """Locate and return the chapter .txt file for ``chapter_no`` in ``bronze_dir``.

    Searches for a ``.txt`` file whose stem contains ``{chapter_no}장``, using
    the same lenient matching rule as examen (digit-prefix guard prevents
    chapter 8 matching "18장.txt").

    Args:
        bronze_dir: Directory containing textbook ``.txt`` files.
        chapter_no: Chapter number to resolve (1-based).

    Returns:
        Path to the matched chapter ``.txt`` file.

    Raises:
        FileNotFoundError: If no matching file is found. Message includes the
            chapter number and the directory path (expected vs actual).
    """
    pattern = _chapter_file_pattern(chapter_no)
    for p in sorted(bronze_dir.glob("*.txt")):
        if pattern.search(p.stem):
            return p

    raise FileNotFoundError(
        f"No textbook file found for chapter {chapter_no} "
        f"in '{bronze_dir}'. "
        f"Expected a filename containing '{chapter_no}장' "
        f"(e.g. '{chapter_no}장 교재제목.txt')."
    )


__all__ = [
    "load_generation_spec",
    "load_curriculum_map",
    "validate_week_in_map",
    "resolve_chapter_txt",
]
