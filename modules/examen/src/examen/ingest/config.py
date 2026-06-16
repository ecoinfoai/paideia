"""T012 — Config loader: blueprint.yaml and curriculum_map.yaml.

Parses YAML inputs and validates them against the shared Pydantic schemas.
Fail-fast on any validation error: raises with the offending file path
and a located error message (constitution III — variability via config,
no silent defaults).

Example::

    from examen.ingest.config import load_blueprint, load_curriculum_map, bronze_dir

    bp = load_blueprint(Path("data/bronze/examen/2026-1-anatomy/blueprint.yaml"))
    cm = load_curriculum_map(Path("data/bronze/examen/2026-1-anatomy/curriculum_map.yaml"))
    bronz = bronze_dir("2026-1", "anatomy")
"""

from __future__ import annotations

from pathlib import Path

import yaml
from paideia_shared.schemas import CurriculumMap, ExamenBlueprint
from pydantic import ValidationError

# bronze_dir 의 단일 출처는 paths.py — 여기서는 재노출만 한다 (paths.py 는 stdlib 만
# 의존하므로 import 순환 없음).
from examen.output.paths import bronze_dir


def load_blueprint(path: Path) -> ExamenBlueprint:
    """Load and validate a blueprint.yaml file.

    Args:
        path: Absolute or relative path to the blueprint.yaml file.

    Returns:
        Validated ExamenBlueprint instance.

    Raises:
        FileNotFoundError: If ``path`` does not exist. Message includes the path.
        ValueError: If the YAML is malformed or the content fails schema validation.
            Message always includes the file path and the offending field.
    """
    if not path.exists():
        raise FileNotFoundError(f"blueprint.yaml not found: {path}")

    # YAML 파싱 — 문법 오류는 위치 포함 메시지로 재포장
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse blueprint.yaml at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"blueprint.yaml must be a YAML mapping, got {type(raw).__name__}: {path}")

    # Pydantic 검증 — ValidationError 를 위치 포함 ValueError 로 재포장
    try:
        return ExamenBlueprint.model_validate(raw)
    except ValidationError as exc:
        # pydantic의 오류 목록을 간결한 문자열로 변환
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(f"blueprint.yaml validation failed at {path}: {errors}") from exc


def load_curriculum_map(path: Path) -> CurriculumMap:
    """Load and validate a curriculum_map.yaml file.

    Args:
        path: Absolute or relative path to the curriculum_map.yaml file.

    Returns:
        Validated CurriculumMap instance.

    Raises:
        FileNotFoundError: If ``path`` does not exist. Message includes the path.
        ValueError: If the YAML is malformed or the content fails schema validation.
            Message always includes the file path and the offending field.
    """
    if not path.exists():
        raise FileNotFoundError(f"curriculum_map.yaml not found: {path}")

    # YAML 파싱
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse curriculum_map.yaml at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"curriculum_map.yaml must be a YAML mapping, got {type(raw).__name__}: {path}"
        )

    # Pydantic 검증
    try:
        return CurriculumMap.model_validate(raw)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(f"curriculum_map.yaml validation failed at {path}: {errors}") from exc


__all__ = ["load_blueprint", "load_curriculum_map", "bronze_dir"]
