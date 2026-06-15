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
    """
    raw = yaml.safe_load(prior_yaml_path.read_text(encoding="utf-8"))
    prior_year: str = raw["semester"]
    ledger_dicts: list[dict] = raw.get("ledger", [])

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
                    f"현재 기준선에 해당 데이터 없음 — "
                    f"segment={segment!r}, chapter={chapter!r}"
                ),
            }

        results.append(result)

    return {
        "prior_year": prior_year,
        "results": results,
    }


__all__ = ["audit_prior"]
