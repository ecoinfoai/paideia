"""T049 — Advisor roster loader for metric-codex distribute stage.

Reads ``지도교수배정.yaml`` and returns a sorted, validated list of
:class:`paideia_shared.schemas.metric_codex.AdvisorRosterEntry` objects.

All boundary failures raise :class:`metric_codex.errors.LocatedInputError`
so the CLI handler maps them to exit code 2 automatically.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas.metric_codex import AdvisorRosterEntry
from pydantic import ValidationError

from metric_codex.errors import LocatedInputError
from metric_codex.yaml_load import load_yaml_mapping


def load_roster(path: Path) -> list[AdvisorRosterEntry]:
    """Load and validate the advisor-to-student roster YAML.

    Expected file structure::

        assignments:
          - student_id: "2026000001"
            advisor_id: "ADV_A"
            advisor_name: "김교수"   # optional

    The function validates every row via :class:`AdvisorRosterEntry` and
    enforces uniqueness of ``student_id`` across the collection (a duplicate
    is a hard error — a student cannot be assigned to two advisors).

    Args:
        path: Absolute path to the ``지도교수배정.yaml`` file.

    Returns:
        List of :class:`AdvisorRosterEntry` objects sorted by ``student_id``
        (ascending), so downstream callers get a deterministic ordering.

    Raises:
        LocatedInputError: If the file is missing, cannot be parsed, lacks the
            ``assignments`` key, contains non-mapping rows, has invalid field
            values, or contains a duplicate ``student_id``.
    """
    raw = load_yaml_mapping(path, "지도교수배정.yaml")

    if "assignments" not in raw:
        raise LocatedInputError(
            "missing required top-level key 'assignments'",
            file=str(path),
            expected="assignments: [...]",
            actual=str(list(raw.keys())),
        )

    assignments = raw["assignments"]
    if not isinstance(assignments, list):
        raise LocatedInputError(
            f"'assignments' must be a list, got {type(assignments).__name__}",
            file=str(path),
            expected="list of assignment mappings",
            actual=type(assignments).__name__,
        )

    entries: list[AdvisorRosterEntry] = []
    seen_sids: set[str] = set()

    for idx, row in enumerate(assignments, start=1):
        if not isinstance(row, dict):
            raise LocatedInputError(
                f"assignments[{idx}] must be a mapping, got {type(row).__name__}",
                file=str(path),
                row=idx,
                expected="mapping with student_id and advisor_id",
                actual=type(row).__name__,
            )
        try:
            entry = AdvisorRosterEntry.model_validate(row)
        except ValidationError as exc:
            raise LocatedInputError(
                f"assignments[{idx}] validation failed: {exc}",
                file=str(path),
                row=idx,
            ) from exc

        if entry.student_id in seen_sids:
            raise LocatedInputError(
                f"duplicate student_id {entry.student_id!r} in roster",
                file=str(path),
                row=idx,
                actual=entry.student_id,
            )
        seen_sids.add(entry.student_id)
        entries.append(entry)

    return sorted(entries, key=lambda e: e.student_id)


__all__ = ["load_roster"]
