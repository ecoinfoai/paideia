"""T039 — Write 차년도방향.yaml (US3 forward-contract output).

``write_forward`` serialises ledger + baseline (+ optional audit) into a
deterministic YAML file via ``dump_yaml``.  No ``datetime.now()`` is called —
the output is byte-identical for identical inputs.

``next_year`` helper:
    Increments the year component of a semester code.
    "2026-1" → "2027-1", "2026-2" → "2027-2".

Schema version: ``"retro-forward/1.0"``
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import BaselineSnapshotRow, ImprovementLedgerEntry

from retro_mester.output.determinism import dump_yaml
from retro_mester.output.manager import atomic_write_text


def next_year(semester: str) -> str:
    """Return the same term one academic year later.

    Increments the year component and preserves the term number.

    Args:
        semester: Semester code of the form ``"YYYY-T"`` (e.g. ``"2026-1"``).

    Returns:
        Semester code one year later (e.g. ``"2027-1"``).

    Examples:
        >>> next_year("2026-1")
        '2027-1'
        >>> next_year("2026-2")
        '2027-2'
    """
    year, term = semester.rsplit("-", 1)
    return f"{int(year) + 1}-{term}"


def write_forward(
    path: Path,
    *,
    ledger: list[ImprovementLedgerEntry],
    baseline: list[BaselineSnapshotRow],
    semester: str,
    course_slug: str,
    created_for_year: str,
    audit: dict | None = None,
) -> None:
    """Write the forward-planning YAML to ``path`` atomically.

    The output structure::

        schema_version: retro-forward/1.0
        semester: <semester>
        course_slug: <course_slug>
        created_for_year: <created_for_year>
        ledger:
          - ...ImprovementLedgerEntry fields...
        baseline:
          - ...BaselineSnapshotRow fields...
        audit:           # omitted when audit is None (cold-start)
          ...

    ``dump_yaml`` is used for serialisation: ``sort_keys=True``,
    ``allow_unicode=True`` — output is deterministic across runs.
    No ``datetime.now()`` is ever called here.

    Args:
        path: Destination file path.  Parent directory must exist.
        ledger: List of ``ImprovementLedgerEntry`` records to serialise.
        baseline: List of ``BaselineSnapshotRow`` records to serialise.
        semester: Semester code for the top-level header.
        course_slug: Course slug for the top-level header.
        created_for_year: Academic year this plan targets.
        audit: Optional audit dict from ``audit_prior``.  Omitted from
            YAML when ``None`` (cold-start scenario).
    """
    # Serialise Pydantic models to plain dicts via model_dump.
    ledger_dicts = [e.model_dump() for e in ledger]
    baseline_dicts = [r.model_dump() for r in baseline]

    doc: dict = {
        "schema_version": "retro-forward/1.0",
        "semester": semester,
        "course_slug": course_slug,
        "created_for_year": created_for_year,
        "ledger": ledger_dicts,
        "baseline": baseline_dicts,
    }

    if audit is not None:
        doc["audit"] = audit

    text = dump_yaml(doc)
    atomic_write_text(path, text, encoding="utf-8")


__all__ = ["next_year", "write_forward"]
