"""T040 — Audit prior-year improvement ledger (US3).

``audit_prior`` loads a prior ``차년도방향.yaml``, matches each ledger entry
against the current-year baseline, and reports whether each target was met.

Matching key: (segment, chapter) at cognitive_level="전체".
Missing row in current baseline → ``met=False`` with a ``note`` explaining
the absence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from paideia_shared.schemas import BaselineSnapshotRow
from pydantic import BaseModel, ConfigDict, ValidationError

from retro_mester.load.errors import InputError


class _PriorYearContract(BaseModel):
    """Structural contract for a prior-year ``차년도방향.yaml`` document.

    Validated at the ``audit_prior`` boundary so a malformed prior file
    fails fast as an ``InputError`` (exit 2) rather than surfacing as a raw
    ``KeyError`` deep inside the matching logic.  Per-entry detail is left to
    the existing ``ImprovementLedgerEntry`` / ``BaselineSnapshotRow`` schemas;
    this contract only guards the top-level shape.

    Attributes:
        schema_version: Prior forward-plan schema version string.
        semester: Prior-year semester code.
        course_slug: Course slug.
        created_for_year: Year the prior plan targeted.
        ledger: Improvement-ledger entry dicts.
        baseline: Baseline-snapshot row dicts.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    semester: str
    course_slug: str
    created_for_year: str
    ledger: list[dict]
    baseline: list[dict]


def _load_prior_contract(prior_yaml_path: Path) -> _PriorYearContract:
    """Load and structurally validate a prior-year ``차년도방향.yaml``.

    Args:
        prior_yaml_path: Path to the prior-year forward-plan YAML.

    Returns:
        A validated ``_PriorYearContract``.

    Raises:
        InputError: If the file is missing, fails to parse as YAML, has a
            non-mapping top level, or fails the ``_PriorYearContract`` schema.
    """
    if not prior_yaml_path.exists():
        raise InputError(f"Prior-year forward yaml not found: {prior_yaml_path}")

    try:
        raw = yaml.safe_load(prior_yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InputError(f"YAML parse error in prior-year file {prior_yaml_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise InputError(
            f"Prior-year file {prior_yaml_path} must be a YAML mapping; got {type(raw).__name__}"
        )

    try:
        return _PriorYearContract.model_validate(raw)
    except ValidationError as exc:
        raise InputError(
            f"Prior-year file {prior_yaml_path} failed structure validation: {exc}"
        ) from exc


def audit_prior(
    prior_yaml_path: Path,
    current_baseline: list[BaselineSnapshotRow],
) -> dict[str, Any]:
    """Compare prior ledger targets against current-year baseline values.

    For each ``ImprovementLedgerEntry`` in the prior yaml, finds the
    matching ``BaselineSnapshotRow`` in ``current_baseline`` by
    ``(segment, chapter)`` (``cognitive_level`` is always ``"전체"``).
    Computes ``met = this_year_value >= prior_target``.

    Args:
        prior_yaml_path: Path to the prior-year ``차년도방향.yaml`` file.
        current_baseline: Current-year ``BaselineSnapshotRow`` instances
            (from ``build_baseline`` for the current run).

    Returns:
        Dict with::

            {
                "prior_year": str,               # semester from prior yaml
                "results": [
                    {
                        "entry_id": str,
                        "prior_baseline": float,
                        "prior_target": float,
                        "this_year_value": float | None,
                        "met": bool,
                        "note": str,             # only present when row missing
                    },
                    ...
                ],
            }

    Raises:
        InputError: If ``prior_yaml_path`` is missing, fails to parse as
            YAML, has a non-mapping top level, or violates the
            ``_PriorYearContract`` structure (FR-008).
    """
    contract = _load_prior_contract(prior_yaml_path)
    prior_year: str = contract.semester
    ledger_dicts: list[dict] = contract.ledger

    # Build lookup: (segment, chapter) → correct_rate for current year.
    current_lookup: dict[tuple[str, str], float] = {
        (r.segment, r.chapter): r.correct_rate
        for r in current_baseline
        if r.cognitive_level == "전체"
    }

    results: list[dict[str, Any]] = []
    for entry in ledger_dicts:
        entry_id: str = entry["entry_id"]
        segment: str = entry["segment"]
        chapter: str = entry["chapter"]
        prior_baseline: float = float(entry["baseline_value"])
        prior_target: float = float(entry["target_value"])

        key = (segment, chapter)
        if key in current_lookup:
            this_year_value = current_lookup[key]
            met = this_year_value >= prior_target
            result: dict[str, Any] = {
                "entry_id": entry_id,
                "prior_baseline": prior_baseline,
                "prior_target": prior_target,
                "this_year_value": this_year_value,
                "met": met,
            }
        else:
            # No matching current-year row for this (segment, chapter).
            result = {
                "entry_id": entry_id,
                "prior_baseline": prior_baseline,
                "prior_target": prior_target,
                "this_year_value": None,
                "met": False,
                "note": (
                    f"현재 기준선에 해당 데이터 없음 — segment={segment!r}, chapter={chapter!r}"
                ),
            }

        results.append(result)

    return {
        "prior_year": prior_year,
        "results": results,
    }


__all__ = ["audit_prior"]
