"""T031 — Local-only pseudonym map for the metric-codex Silver store.

Assigns a stable ``S{NNN}`` pseudonym to every student so the optional
LLM polish step never sees a real student_id or name (PRIV-03 — PII never
crosses the LLM boundary).  The mapping is append-only: once a student_id
receives a pseudonym it keeps it across runs — new students receive numbers
above the current maximum so earlier assignments are never renumbered.

The map is persisted as ``pseudonym_map.parquet`` next to the codex store but is
never forwarded downstream of the pseudonymization boundary.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from paideia_shared.schemas import PseudonymMapEntry

from metric_codex.errors import LocatedInputError
from metric_codex.output.determinism import atomic_write, parquet_write_options
from metric_codex.store.codex import none_if_na

# Fixed column order for byte-identical parquet output.
_COLUMNS: list[str] = ["student_id", "name_kr", "pseudonym"]


def build_pseudonym_map(
    identities: dict[str, str | None],
    *,
    prior: dict[str, str] | None = None,
) -> list[PseudonymMapEntry]:
    """Build an append-only bijective student → pseudonym map.

    Prior assignments are preserved unchanged: every ``student_id`` present in
    ``prior`` keeps its existing ``S{NNN}`` pseudonym regardless of where it
    would sort in the full set.  New student_ids (absent from ``prior``) receive
    the next consecutive numbers above the current maximum — gaps left by
    dropped students are never reused.  New ids are assigned in ascending
    ``student_id`` order among themselves.

    This makes pseudonym assignment stable across runs (PRIV-03, DET-03): adding
    a student with a low-sorting id does NOT renumber any previously-assigned
    student.

    Args:
        identities: Mapping of ``student_id`` → ``name_kr`` (``None`` when the
            name is unknown).  The name is carried for re-identification only.
        prior: Optional mapping of ``student_id`` → existing pseudonym loaded
            from a previously written ``pseudonym_map.parquet``.  Every sid
            present here keeps its pseudonym; omitted or ``None`` ≡ no prior
            assignments exist (first run).

    Returns:
        One ``PseudonymMapEntry`` per student, sorted ascending by student_id.
    """
    _prior: dict[str, str] = prior or {}

    # Determine the highest N already in use so new assignments start above it.
    # prior comes only from read_pseudonym_map, which validates each value
    # against the S{NNN} schema, so int(p[1:]) is always safe.
    max_n: int = max((int(p[1:]) for p in _prior.values()), default=0)

    # New ids: those in identities but absent from prior, sorted ascending.
    new_ids = sorted(sid for sid in identities if sid not in _prior)

    counter = max_n + 1
    new_assignments: dict[str, str] = {}
    for sid in new_ids:
        new_assignments[sid] = f"S{counter:03d}"
        counter += 1

    entries: list[PseudonymMapEntry] = []
    for student_id in sorted(identities):
        pseudonym = _prior[student_id] if student_id in _prior else new_assignments[student_id]
        entries.append(
            PseudonymMapEntry(
                student_id=student_id,
                name_kr=identities[student_id],
                pseudonym=pseudonym,
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
        name_kr = none_if_na(record.get("name_kr"))
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

    # Cross-row uniqueness: both student_id and pseudonym must be bijective.
    seen_sids: set[str] = set()
    seen_pseudonyms: set[str] = set()
    for offset, entry in enumerate(entries):
        if entry.student_id in seen_sids:
            raise LocatedInputError(
                f"duplicate student_id '{entry.student_id}' in pseudonym map",
                file=path.name,
                row=offset + 1,
            )
        if entry.pseudonym in seen_pseudonyms:
            raise LocatedInputError(
                f"duplicate pseudonym '{entry.pseudonym}' in pseudonym map",
                file=path.name,
                row=offset + 1,
            )
        seen_sids.add(entry.student_id)
        seen_pseudonyms.add(entry.pseudonym)

    return entries


__all__ = ["build_pseudonym_map", "write_pseudonym_map", "read_pseudonym_map"]
