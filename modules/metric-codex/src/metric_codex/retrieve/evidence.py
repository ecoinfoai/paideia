"""T039 — Deterministic evidence retrieval for metric-codex US2.

No I/O, no LLM, no PII.  Pure function: filters a pre-loaded list of
CodexEntry rows and returns a sorted, citable evidence list.
"""

from __future__ import annotations

from typing import Literal

from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind, EvidenceCitation


def retrieve_evidence(
    entries: list[CodexEntry],
    *,
    entry_kinds: set[EntryKind] | None = None,
    domain: str | None = None,
    keyword: str | None = None,
) -> tuple[list[EvidenceCitation], list[Literal["minimal", "rich"]], bool]:
    """Return cited evidence and availability metadata for one student's entries.

    All three filters AND together; a None filter is a no-op.

    Args:
        entries: All CodexEntry rows for ONE student (caller must pre-filter by
            student_id; this function never sees student PII).
        entry_kinds: When set, keep only entries whose ``entry_kind`` is in this
            set.  None means accept all kinds.
        domain: When set, keep only entries whose ``domain`` equals this string
            (exact match).  None means accept all domains.
        keyword: When set, keep only entries where the casefold keyword is a
            substring of ``entry.key``, ``entry.domain``, or ``entry.value_text``
            (when non-None).  None means accept all entries.

    Returns:
        A 3-tuple ``(citations, available_layers, no_evidence)``:

        - ``citations``: Matched entries converted to EvidenceCitation and
          sorted by ``(layer, key, source_id, str(value), observed_at)`` for a
          deterministic total order (no ties → stable bytes across runs).
          ``observed_at=None`` sorts before any ISO date string (v1 limit:
          U24 — not all entry kinds carry an event date; treat as unknown).
        - ``available_layers``: Sorted list of distinct ``layer`` values present
          in the WHOLE ``entries`` list (not just the filtered subset) — reflects
          what richness tiers the student's full codex contains (FR-015 / U28).
          This is a whole-codex property and is NOT narrowed by the filters.
        - ``no_evidence``: True iff ``citations`` is empty.
    """
    # available_layers reflects the whole student codex, not the filter result.
    distinct_layers: list[Literal["minimal", "rich"]] = sorted(
        {e.layer for e in entries}  # type: ignore[type-var]
    )

    # Apply filters (each None filter is a no-op).
    kw_cf = keyword.casefold() if keyword is not None else None

    matched: list[EvidenceCitation] = []
    for entry in entries:
        if entry_kinds is not None and entry.entry_kind not in entry_kinds:
            continue
        if domain is not None and entry.domain != domain:
            continue
        if kw_cf is not None:
            hit = (
                kw_cf in entry.key.casefold()
                or (entry.domain is not None and kw_cf in entry.domain.casefold())
                or (entry.value_text is not None and kw_cf in entry.value_text.casefold())
            )
            if not hit:
                continue

        value: float | str = (
            entry.value_num if entry.value_num is not None else entry.value_text  # type: ignore[assignment]
        )
        matched.append(
            EvidenceCitation(
                key=entry.key,
                value=value,
                source_id=entry.source_id,
                observed_at=entry.observed_at,
                layer=entry.layer,
            )
        )

    # Deterministic total order: all available EvidenceCitation fields are used
    # as sort keys so no tie can leak input-row ordering through.
    # observed_at=None is mapped to "" which sorts before any ISO date string
    # (total-order convention: None → first, v1 limit documented in docstring).
    matched.sort(
        key=lambda c: (
            c.layer,
            c.key,
            c.source_id,
            str(c.value),
            c.observed_at or "",
        )
    )

    return matched, distinct_layers, len(matched) == 0


__all__ = ["retrieve_evidence"]
