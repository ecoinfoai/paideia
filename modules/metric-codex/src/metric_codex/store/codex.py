"""T032 — Accumulating Silver store for metric-codex CodexEntry rows.

The Silver store is two long-form parquet files:

- ``codex_entry.parquet`` — one row per provenance-tagged fact/text snippet.
- ``source_ledger.parquet`` — one row per ingested source file.

``codex_entry.parquet`` carries NO wall-clock field (ingestion time lives only
in the source ledger), so for a fixed input set it is byte-identical across runs.

The store accumulates across ingest runs.  The natural key of a CodexEntry is
``(student_id, source_id, entry_kind, key, item_ref)``: on a key collision the
new entry replaces the old in place (correction semantics, FR-006), and an
identical re-ingest leaves the row count unchanged (idempotent, FR-009).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from paideia_shared.schemas import CodexEntry, SourceRecord

from metric_codex.errors import LocatedInputError
from metric_codex.ingest.result import SourceReadResult
from metric_codex.output.determinism import atomic_write, parquet_write_options

_CODEX_FILE = "codex_entry.parquet"
_LEDGER_FILE = "source_ledger.parquet"

# Fixed column order for byte-identical parquet output.
_CODEX_COLUMNS: list[str] = [
    "student_id",
    "semester",
    "cohort_year",
    "layer",
    "entry_kind",
    "domain",
    "item_ref",
    "key",
    "value_num",
    "value_text",
    "source_id",
    "observed_at",
]
_LEDGER_COLUMNS: list[str] = [
    "source_id",
    "origin_module",
    "origin_layer",
    "source_path",
    "sha256",
    "ingested_at",
]

# Natural key of a CodexEntry, used for accumulation / idempotency.
_NaturalKey = tuple[str, str, str, str, str | None]


def _natural_key(entry: CodexEntry) -> _NaturalKey:
    """Return the natural key ``(student_id, source_id, entry_kind, key, item_ref)``.

    Args:
        entry: A CodexEntry to key.

    Returns:
        The deduplication key tuple (``entry_kind`` as its string value).
    """
    return (
        entry.student_id,
        entry.source_id,
        entry.entry_kind.value,
        entry.key,
        entry.item_ref,
    )


def read_existing_store(
    silver_dir: Path,
) -> tuple[list[CodexEntry], list[SourceRecord]]:
    """Load any existing codex / ledger parquet from a Silver directory.

    Missing files yield empty lists (a first-ever run).  Present-but-malformed
    files surface as a located boundary error.

    Args:
        silver_dir: metric-codex Silver directory for this semester/course.

    Returns:
        ``(entries, records)`` reconstructed from the on-disk store.

    Raises:
        LocatedInputError: If a present store file cannot be read or a row fails
            its Pydantic contract.
    """
    entries = _read_codex(silver_dir / _CODEX_FILE)
    records = _read_ledger(silver_dir / _LEDGER_FILE)
    return entries, records


def _read_codex(path: Path) -> list[CodexEntry]:
    """Read ``codex_entry.parquet`` into validated CodexEntry rows (empty if absent)."""
    if not path.is_file():
        return []
    frame = _safe_read_parquet(path)
    out: list[CodexEntry] = []
    for offset, record in enumerate(frame.to_dict(orient="records")):
        clean = {k: none_if_na(v) for k, v in record.items()}
        try:
            out.append(CodexEntry.model_validate(clean))
        except ValueError as exc:
            raise LocatedInputError(
                f"existing codex row failed CodexEntry contract: {exc}",
                file=path.name,
                row=offset + 1,
            ) from exc
    return out


def _read_ledger(path: Path) -> list[SourceRecord]:
    """Read ``source_ledger.parquet`` into validated SourceRecord rows (empty if absent)."""
    if not path.is_file():
        return []
    frame = _safe_read_parquet(path)
    out: list[SourceRecord] = []
    for offset, record in enumerate(frame.to_dict(orient="records")):
        clean = {k: none_if_na(v) for k, v in record.items()}
        try:
            out.append(SourceRecord.model_validate(clean))
        except ValueError as exc:
            raise LocatedInputError(
                f"existing ledger row failed SourceRecord contract: {exc}",
                file=path.name,
                row=offset + 1,
            ) from exc
    return out


def _safe_read_parquet(path: Path) -> pd.DataFrame:
    """Read a parquet file, wrapping I/O failures as a located error."""
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 — boundary: surface as located error
        raise LocatedInputError(
            f"failed to read existing store: {exc}",
            file=path.name,
        ) from exc


def none_if_na(value: object) -> object:
    """Map pandas NA/NaN scalars to ``None``; pass everything else through.

    Shared parquet-read helper: a true Python ``None`` re-emerges from a parquet
    null column as ``None``, but numeric/float nulls surface as ``NaN``; this
    normalises both so Pydantic ``model_validate`` sees a clean ``None``.

    Args:
        value: A raw cell value from ``DataFrame.to_dict``.

    Returns:
        ``None`` if the value is a pandas NA/NaN scalar, else the value unchanged.
    """
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    return value


def accumulate(
    results: list[SourceReadResult],
    existing_entries: list[CodexEntry],
    existing_records: list[SourceRecord],
) -> tuple[list[CodexEntry], list[SourceRecord]]:
    """Merge this run's read results into the existing store.

    Entries are keyed by their natural key; the new entry replaces an existing
    one in place (correction, FR-006) while an identical re-ingest leaves the
    count unchanged (idempotent, FR-009).  Source records are merged by
    ``source_id`` (new replaces old).

    Args:
        results: This run's per-source read results.
        existing_entries: CodexEntry rows already in the store.
        existing_records: SourceRecord rows already in the store.

    Returns:
        ``(entries, records)`` — entries sorted by natural key, records sorted
        by source_id.
    """
    entry_by_key: dict[_NaturalKey, CodexEntry] = {
        _natural_key(e): e for e in existing_entries
    }
    record_by_id: dict[str, SourceRecord] = {r.source_id: r for r in existing_records}

    for result in results:
        for entry in result.entries:
            entry_by_key[_natural_key(entry)] = entry
        record_by_id[result.source_record.source_id] = result.source_record

    entries = sorted(entry_by_key.values(), key=_natural_key_sort)
    records = sorted(record_by_id.values(), key=lambda r: r.source_id)
    return entries, records


def _natural_key_sort(entry: CodexEntry) -> tuple[str, str, str, str, str]:
    """Sort key matching the natural key, with ``item_ref`` None ordered first."""
    student_id, source_id, kind, key, item_ref = _natural_key(entry)
    return (student_id, source_id, kind, key, "" if item_ref is None else item_ref)


def write_store(
    silver_dir: Path,
    entries: list[CodexEntry],
    records: list[SourceRecord],
) -> None:
    """Write the codex + ledger parquet files deterministically and atomically.

    Args:
        silver_dir: metric-codex Silver directory (created if absent).
        entries: Accumulated CodexEntry rows (already sorted by natural key).
        records: Accumulated SourceRecord rows (already sorted by source_id).
    """
    silver_dir.mkdir(parents=True, exist_ok=True)
    _write_codex(silver_dir / _CODEX_FILE, entries)
    _write_ledger(silver_dir / _LEDGER_FILE, records)


def _write_codex(path: Path, entries: list[CodexEntry]) -> None:
    """Write ``codex_entry.parquet`` with fixed columns and stable dtypes."""
    records = [
        {
            "student_id": e.student_id,
            "semester": e.semester,
            "cohort_year": e.cohort_year,
            "layer": e.layer,
            "entry_kind": e.entry_kind.value,
            "domain": e.domain,
            "item_ref": e.item_ref,
            "key": e.key,
            "value_num": e.value_num,
            "value_text": e.value_text,
            "source_id": e.source_id,
            "observed_at": e.observed_at,
        }
        for e in entries
    ]
    frame = pd.DataFrame.from_records(records, columns=_CODEX_COLUMNS)
    # Pin dtypes so an empty frame and nullable columns stay byte-stable.
    frame = frame.astype(
        {
            "student_id": "object",
            "semester": "object",
            "cohort_year": "int64",
            "layer": "object",
            "entry_kind": "object",
            "domain": "object",
            "item_ref": "object",
            "key": "object",
            "value_num": "float64",
            "value_text": "object",
            "source_id": "object",
            "observed_at": "object",
        }
    )

    def _write(tmp: Path) -> None:
        frame.to_parquet(tmp, index=False, **parquet_write_options())

    atomic_write(path, _write)


def _write_ledger(path: Path, records: list[SourceRecord]) -> None:
    """Write ``source_ledger.parquet`` with fixed columns."""
    rows = [
        {
            "source_id": r.source_id,
            "origin_module": r.origin_module,
            "origin_layer": r.origin_layer,
            "source_path": r.source_path,
            "sha256": r.sha256,
            "ingested_at": r.ingested_at,
        }
        for r in records
    ]
    frame = pd.DataFrame.from_records(rows, columns=_LEDGER_COLUMNS).astype("object")

    def _write(tmp: Path) -> None:
        frame.to_parquet(tmp, index=False, **parquet_write_options())

    atomic_write(path, _write)


__all__ = ["read_existing_store", "accumulate", "write_store", "none_if_na"]
