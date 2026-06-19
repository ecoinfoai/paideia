"""Shared reader-result interface for metric-codex ingest sources.

Every source reader (school Excel, immersio Silver, needs-map Silver, …)
returns a ``SourceReadResult``.  This lets the pipeline stage that
assembles the Silver parquet accept any source uniformly.

The dataclass is frozen so callers cannot accidentally mutate the ingested
snapshot after construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from paideia_shared.schemas.metric_codex import CodexEntry, SourceRecord


@dataclass(frozen=True)
class SourceReadResult:
    """Immutable result of reading one source file.

    Attributes:
        entries: CodexEntry rows for codex_entry.parquet; source_id is
            already populated on each entry.
        source_record: One provenance ledger row for this source;
            ingested_at is already populated.
        identities: Mapping of student_id → name_kr (``None`` when the
            name was absent in the source).  Used by U1c to build the
            pseudonym map; the name itself never leaves the Bronze boundary.
    """

    entries: list[CodexEntry]
    source_record: SourceRecord
    identities: dict[str, str | None]


__all__ = ["SourceReadResult"]
