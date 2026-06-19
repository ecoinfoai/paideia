"""T031 — Local-only pseudonym map for the metric-codex Silver store.

Assigns a deterministic ``S{NNN}`` pseudonym to every student so the optional
LLM polish step never sees a real student_id or name (PRIV-03 — PII never
crosses the LLM boundary).  The mapping is bijective and fully reproducible for
a given student set: pseudonyms are handed out ``S001, S002, …`` in ascending
``student_id`` order.

The map is persisted as ``pseudonym_map.parquet`` next to the codex store but is
never forwarded downstream of the pseudonymization boundary.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from paideia_shared.schemas import PseudonymMapEntry

from metric_codex.errors import LocatedInputError
from metric_codex.output.determinism import atomic_write, parquet_write_options

# Fixed column order for byte-identical parquet output.
_COLUMNS: list[str] = ["student_id", "name_kr", "pseudonym"]


def build_pseudonym_map(identities: dict[str, str | None]) -> list[PseudonymMapEntry]:
    """Build a deterministic bijective student → pseudonym map.

    Students are sorted ascending by ``student_id`` and assigned pseudonyms
    ``S001``, ``S002``, … in that order.  The assignment depends only on the set
    of student_ids, so two calls with the same students always agree (PRIV-03).

    Args:
        identities: Mapping of ``student_id`` → ``name_kr`` (``None`` when the
            name is unknown).  The name is carried for re-identification only.

    Returns:
        One ``PseudonymMapEntry`` per student, sorted ascending by student_id.
    """
    entries: list[PseudonymMapEntry] = []
    for index, student_id in enumerate(sorted(identities), start=1):
        entries.append(
            PseudonymMapEntry(
                student_id=student_id,
                name_kr=identities[student_id],
                pseudonym=f"S{index:03d}",
            )
        )
    return entries


def write_pseudonym_map(path: Path, entries: list[PseudonymMapEntry]) -> None:
    """Write the pseudonym map to ``pseudonym_map.parquet`` deterministically.

    Rows are sorted by ``student_id``; columns use a fixed order; pyarrow write
    options strip non-deterministic metadata so identical inputs yield a
    byte-identical file.  The write is atomic (temp→rename).

    Args:
        path: Destination ``pseudonym_map.parquet`` path.  Parent must exist.
        entries: Pseudonym map entries to persist.
    """
    records = [
        {
            "student_id": e.student_id,
            "name_kr": e.name_kr,
            "pseudonym": e.pseudonym,
        }
        for e in sorted(entries, key=lambda e: e.student_id)
    ]
    frame = pd.DataFrame.from_records(records, columns=_COLUMNS)
    # Object dtype keeps None as a true null (not the float NaN) for str columns.
    frame = frame.astype({"student_id": "object", "name_kr": "object", "pseudonym": "object"})

    def _write(tmp: Path) -> None:
        frame.to_parquet(tmp, index=False, **parquet_write_options())

    atomic_write(path, _write)


def read_pseudonym_map(path: Path) -> list[PseudonymMapEntry]:
    """Read a ``pseudonym_map.parquet`` file back into validated entries.

    Args:
        path: Path to a previously written ``pseudonym_map.parquet``.

    Returns:
        Pseudonym map entries, sorted ascending by student_id.

    Raises:
        LocatedInputError: If the file cannot be read or a row fails the
            ``PseudonymMapEntry`` contract (malformed local store).
    """
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 — boundary: surface as located error
        raise LocatedInputError(
            f"failed to read pseudonym map: {exc}",
            file=path.name,
        ) from exc

    entries: list[PseudonymMapEntry] = []
    for offset, record in enumerate(frame.to_dict(orient="records")):
        name_kr = record.get("name_kr")
        if name_kr is not None and pd.isna(name_kr):
            name_kr = None
        try:
            entries.append(
                PseudonymMapEntry(
                    student_id=str(record["student_id"]),
                    name_kr=None if name_kr is None else str(name_kr),
                    pseudonym=str(record["pseudonym"]),
                )
            )
        except (ValueError, KeyError) as exc:
            raise LocatedInputError(
                f"pseudonym map row failed contract: {exc}",
                file=path.name,
                row=offset + 1,
            ) from exc

    entries.sort(key=lambda e: e.student_id)
    return entries


__all__ = ["build_pseudonym_map", "write_pseudonym_map", "read_pseudonym_map"]
