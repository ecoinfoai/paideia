"""T044 — PRIV-05 fail-fast re-identification for metric-codex Gold.

Re-identification is the highest privacy-risk step: it maps a pseudonymized
narrative back to a real student and writes it to the local Gold tier.  The
pseudonym map is validated for bijection BEFORE any Gold byte is written, and a
missing mapping aborts with a located error writing NOTHING (no partial Gold).

PRIV-05: an absent / corrupt / non-bijective pseudonym map fails fast.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import PseudonymMapEntry

from metric_codex.errors import LocatedInputError
from metric_codex.output.determinism import atomic_write


def validate_pseudonym_map(
    entries: list[PseudonymMapEntry],
) -> dict[str, PseudonymMapEntry]:
    """Validate bijection and build a ``pseudonym -> entry`` index.

    Args:
        entries: The full pseudonym map for the semester/course.

    Returns:
        A ``pseudonym -> PseudonymMapEntry`` index.

    Raises:
        LocatedInputError: If the list is empty, or non-bijective (a duplicate
            pseudonym OR a duplicate student_id). (PRIV-05.)
    """
    if not entries:
        raise LocatedInputError(
            "pseudonym map is empty — re-identification needs a non-empty bijective map",
            file="pseudonym_map.parquet",
            expected="at least one mapping row",
            actual="0 rows",
        )

    by_pseudonym: dict[str, PseudonymMapEntry] = {}
    seen_sids: set[str] = set()

    for entry in entries:
        if entry.pseudonym in by_pseudonym:
            raise LocatedInputError(
                f"pseudonym map is non-bijective: duplicate pseudonym {entry.pseudonym!r}",
                file="pseudonym_map.parquet",
                expected="unique pseudonyms",
                actual=entry.pseudonym,
            )
        if entry.student_id in seen_sids:
            raise LocatedInputError(
                f"pseudonym map is non-bijective: duplicate student_id {entry.student_id!r}",
                file="pseudonym_map.parquet",
                expected="unique student_ids",
                actual=entry.student_id,
            )
        by_pseudonym[entry.pseudonym] = entry
        seen_sids.add(entry.student_id)

    return by_pseudonym


def reidentify_and_write(
    *,
    gold_dir: Path,
    pseudonym: str,
    narrative: str,
    pseudonym_index: dict[str, PseudonymMapEntry],
) -> Path:
    """Re-identify ``pseudonym`` and write its narrative to the Gold tier.

    Output path: ``gold_dir/학생별/{student_id}_{name_kr}.md`` (or
    ``{student_id}.md`` when ``name_kr`` is ``None``).  The write is atomic;
    on any failure NOTHING is written (헌장 V — no partial Gold).

    Args:
        gold_dir: Gold tier directory for this semester/course.
        pseudonym: The student's pseudonym to re-identify.
        narrative: The rendered Korean markdown narrative to write.
        pseudonym_index: Validated ``pseudonym -> entry`` index from
            ``validate_pseudonym_map``.

    Returns:
        The written Gold markdown path.

    Raises:
        LocatedInputError: If ``pseudonym`` is absent from the index (the needed
            mapping is missing). No file is written. (PRIV-05.)
    """
    entry = pseudonym_index.get(pseudonym)
    if entry is None:
        raise LocatedInputError(
            f"re-identification mapping absent for pseudonym {pseudonym!r}",
            file="pseudonym_map.parquet",
            expected="a mapping for every generated pseudonym",
            actual=pseudonym,
        )

    # name_kr has no pattern constraint at the schema level, so a '/' or NUL
    # could escape 학생별/.  Fail-fast (consistent with PRIV-05) before any write.
    if entry.name_kr is not None and ("/" in entry.name_kr or "\x00" in entry.name_kr):
        raise LocatedInputError(
            f"name_kr for student {entry.student_id!r} contains illegal path character",
            file="pseudonym_map.parquet",
            expected="name without '/' or NUL",
            actual=entry.name_kr,
        )

    student_dir = gold_dir / "학생별"
    student_dir.mkdir(parents=True, exist_ok=True)

    if entry.name_kr is not None:
        filename = f"{entry.student_id}_{entry.name_kr}.md"
    else:
        filename = f"{entry.student_id}.md"

    dest = student_dir / filename

    def _write(tmp: Path) -> None:
        tmp.write_text(narrative, encoding="utf-8")

    atomic_write(dest, _write)
    return dest


__all__ = ["validate_pseudonym_map", "reidentify_and_write"]
