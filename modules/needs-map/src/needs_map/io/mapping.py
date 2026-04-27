"""Mapping YAML loader for needs-map (T021 v0.1.0; T018 v0.1.1).

Reads a course-specific ``{course}.diagnostic.yaml`` and returns a validated
``DiagnosticMappingConfig``. v0.1.1 deltas (T018):

- Enforces ``metadata.mapping_version == 2`` — v1 mappings are rejected
  with a dedicated ``MappingVersionError`` so operators upgrade their
  YAML before any silver output is touched.
- pyyaml ``safe_load`` already resolves YAML anchors / aliases — no
  additional pre-processing needed (research §R-08).
- Surfaces V6 / V7 / V8 validation errors with operator-actionable
  context per ``contracts/cli.md`` "매핑 YAML kind 검증 실패 메시지
  형식". Specifically wraps "single_select on a quantitative axis" and
  related kind/axis mismatches into a multi-line ``MappingKindError``
  whose ``__str__`` matches the spec's block format.

Spec: 003-needs-map-v0-1-1/tasks.md T018, contracts/mapping_yaml_v2.md,
contracts/cli.md.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path
from typing import Any

import yaml
from paideia_shared.schemas import DiagnosticMappingConfig
from paideia_shared.schemas._common import (
    STANDARD_AXIS_KEYS,
    AuxiliaryGroupKey,
    FreetextAreaKey,
)
from pydantic import ValidationError

_QUANT_AXES: frozenset[str] = frozenset(STANDARD_AXIS_KEYS)
_AUX_GROUP_KEYS: frozenset[str] = frozenset(typing.get_args(AuxiliaryGroupKey))
_FREETEXT_KEYS: frozenset[str] = frozenset(typing.get_args(FreetextAreaKey))


class MappingVersionError(ValueError):
    """Raised when ``metadata.mapping_version`` is not the expected v0.1.1 value (2).

    needs-map v0.1.1 refuses to ingest v0.1.0 mappings (mapping_version=1) so
    operators are forced to migrate to the 8-axis vocabulary before silver
    outputs are generated. Subclassing ``ValueError`` keeps it compatible
    with the existing ``except ValueError`` paths in the CLI entry-point
    while still being distinguishable for logging.
    """


class MappingKindError(ValueError):
    """Operator-actionable validation error for kind/axis mismatches.

    Composed by :func:`load_mapping` from a wrapped ``ValidationError`` whose
    message follows the spec block format in ``contracts/cli.md``. Subclasses
    ``ValueError`` to preserve compatibility with existing ``except``
    clauses; the CLI prints the multi-line message verbatim to stderr.
    """


def load_mapping(path: Path) -> DiagnosticMappingConfig:
    """Load a mapping YAML and run the v0.1.1 validators.

    Args:
        path: Filesystem path to the ``{course}.diagnostic.yaml`` file.

    Returns:
        Validated :class:`DiagnosticMappingConfig` instance.

    Raises:
        FileNotFoundError: If the file does not exist (message includes path).
        TypeError: If ``path`` is not a :class:`pathlib.Path`.
        ValueError: If the YAML body is not a mapping at top level
            (message includes path).
        MappingVersionError: If ``metadata.mapping_version`` is missing or
            not equal to ``2``.
        MappingKindError: If a column declares a kind that is incompatible
            with its axis (per V7/V8 + contracts/cli.md).
        yaml.YAMLError: On malformed YAML (line/column embedded by PyYAML).
        pydantic.ValidationError: On other schema/validator violations
            (message preserves V1-V6 prefix and offending axis or column).
    """
    if not isinstance(path, Path):
        raise TypeError(
            f"load_mapping: expected pathlib.Path, got {type(path).__name__}."
        )
    if not path.is_file():
        raise FileNotFoundError(f"Mapping YAML not found: {path}")

    text = path.read_text(encoding="utf-8")
    # pyyaml.safe_load resolves anchors/aliases automatically — no extra step
    # needed for the v0.1.1 ``ordinal_maps`` anchor pattern (research §R-08).
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"load_mapping: expected top-level mapping in {path}, got "
            f"{type(data).__name__}."
        )

    # Drop the top-level ``ordinal_maps:`` block before forwarding to Pydantic
    # — DiagnosticMappingConfig has ``extra='forbid'`` and only knows about
    # ``metadata`` / ``columns`` / ``axes``. The block exists solely to host
    # YAML anchors that columns reference via ``*alias`` (already resolved
    # by safe_load above); keeping it would trigger a spurious extra-field
    # ValidationError. See contracts/mapping_yaml_v2.md §"최상위 구조".
    if "ordinal_maps" in data:
        data = {k: v for k, v in data.items() if k != "ordinal_maps"}

    _enforce_mapping_version_two(data, path)

    try:
        return DiagnosticMappingConfig.model_validate(data)
    except ValidationError as exc:
        kind_error = _try_kind_error_message(exc, data, path)
        if kind_error is not None:
            raise kind_error from exc
        # Re-raise with the original payload so downstream code can still
        # inspect ``exc.errors()``. The bare re-raise preserves the V1-V6
        # prefix Pydantic emits.
        raise


def _enforce_mapping_version_two(data: dict[str, Any], path: Path) -> None:
    """Reject v0.1.0 mappings (``mapping_version != 2``)."""
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        # Let Pydantic surface the exact missing-field error.
        return
    version = metadata.get("mapping_version")
    if version != 2:
        raise MappingVersionError(
            f"load_mapping: needs-map v0.1.1 requires "
            f"metadata.mapping_version=2, got {version!r} in {path}. "
            "Upgrade the YAML to the v2 schema (8 axes + 5 column kinds) "
            "per contracts/mapping_yaml_v2.md §'v0.1.0 → v0.1.1 마이그레이션'."
        )


_KIND_AXIS_PATTERN = re.compile(
    r"V7: aggregate='mean'.+kind=(?P<kind>'[^']+').+source=(?P<source>'[^']+')"
)


def _try_kind_error_message(
    exc: ValidationError, data: dict[str, Any], path: Path
) -> MappingKindError | None:
    """Return a :class:`MappingKindError` when a kind/axis mismatch is detected.

    Currently triggered by V7 (``aggregate='mean'`` on non-likert) errors.
    The Pydantic ValidationError carries one or more ``errors()`` entries;
    a kind/axis mismatch produces an entry whose ``msg`` contains the V7
    prefix and the offending kind + source. We extract those and rebuild
    the multi-line block from contracts/cli.md.
    """
    columns = data.get("columns")
    if not isinstance(columns, list):
        return None
    column_lookup = {
        c["source"]: c
        for c in columns
        if isinstance(c, dict) and isinstance(c.get("source"), str)
    }

    for error in exc.errors():
        msg = str(error.get("msg", ""))
        if "V7" not in msg or "aggregate='mean'" not in msg:
            continue
        match = _KIND_AXIS_PATTERN.search(msg)
        if match is None:
            continue
        bad_kind = match.group("kind").strip("'")
        bad_source = match.group("source").strip("'")
        column = column_lookup.get(bad_source, {})
        axis = column.get("axis")
        if axis not in _QUANT_AXES:
            # Quantitative-axis-only message would not apply (e.g. a
            # mean-on-auxiliary fail). Let the original ValidationError
            # bubble up untouched so the operator sees the raw V7 message.
            continue
        allowed = _allowed_kinds_for_axis(axis)
        action = _action_hint_for_axis(axis)
        block = (
            f"ERROR: Invalid mapping kind for axis {axis!r}\n"
            f"  File: {path}\n"
            f"  Column: {bad_source!r}\n"
            f"  Declared kind: {bad_kind!r}\n"
            f"  Allowed kinds for quantitative axis: {allowed}\n"
            f"  Action: {action}"
        )
        return MappingKindError(block)
    return None


def _allowed_kinds_for_axis(axis: str) -> list[str]:
    """Per spec FR-008 + V6/V7: only ``likert`` may target a quantitative axis."""
    if axis in _QUANT_AXES:
        return ["likert"]
    if axis in _AUX_GROUP_KEYS:
        return ["single_select", "multiselect"]
    if axis in _FREETEXT_KEYS:
        return ["freetext"]
    return ["identity", "likert", "single_select", "multiselect", "freetext"]


def _action_hint_for_axis(axis: str) -> str:
    """Per contracts/cli.md L48-56 — operator-actionable next step."""
    if axis in _QUANT_AXES:
        sample_aux = next(iter(sorted(_AUX_GROUP_KEYS)))
        return (
            "Either change kind to 'likert' (if 7-point scale)\n"
            f"          OR move to auxiliary group key (e.g., {sample_aux!r})."
        )
    return "Adjust kind to one of the allowed values for this axis."


# Mark these helpers as part of the public surface for testability.
__all__ = [
    "MappingKindError",
    "MappingVersionError",
    "load_mapping",
]
