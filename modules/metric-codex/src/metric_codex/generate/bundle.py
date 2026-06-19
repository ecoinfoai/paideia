"""T041 — PII-free student bundle builder for metric-codex generate stage.

Pseudonym-space only: student_id and name_kr are used solely to look up
pseudonyms and are NEVER placed in the bundle payload or staging files.

PII boundary enforced at two points:
1. build_bundles: operates entirely in pseudonym space after the initial lookup.
2. write_staging: runs assert_no_pii on the serialized JSON BEFORE writing.

Scanning strategy for assert_no_pii:
- 10-digit student_id: regex ``r'\\b\\d{10}\\b'`` over the full serialized payload.
- Email: regex RFC-5321 pattern over payload.
- Korean names: literal membership check against the known name set extracted
  from the pseudonym_map.  We do NOT apply a generic Hangul-syllable heuristic
  over the full payload to avoid false positives on legitimate Korean evidence
  text (question text, chapter labels, freetext categories).  The set-membership
  approach catches exactly the names we know about and nothing else.
  The caller passes the known names to ``write_staging`` (which forwards them to
  ``assert_no_pii``); the CLI ``dry-run`` handler computes them from the
  pseudonym map's ``name_kr`` values.  The 10-digit and email scans always run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from paideia_shared.schemas import PseudonymMapEntry
from paideia_shared.schemas.metric_codex import CodexEntry, QueryAnswer
from pydantic import BaseModel, ConfigDict, Field

from metric_codex.errors import LocatedInputError
from metric_codex.output.determinism import atomic_write
from metric_codex.retrieve.query import QuestionSet, answer_question

# ---------------------------------------------------------------------------
# PII scan patterns
# ---------------------------------------------------------------------------

_SID_PATTERN = re.compile(r"\b\d{10}\b")
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


# ---------------------------------------------------------------------------
# Bundle models
# ---------------------------------------------------------------------------


class BundleQuestion(BaseModel):
    """One question + its evidence answer inside a StudentBundle.

    Attributes:
        question_id: Canonical question id from QuestionSet.
        question_text: Human-readable question text (Korean or English).
        answer: Deterministic evidence query result (pure retrieval; no narrative).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    question_text: str
    answer: QueryAnswer


class StudentBundle(BaseModel):
    """PII-free bundle for one pseudonymized student.

    The bundle is the sole input to the generate/narrative layer (EVID-03).
    It is serialized to staging/{pseudonym}.json before any LLM call.

    Invariants:
    - pseudonym matches ``^S\\d{3,}$`` (verified by the QueryAnswer contract).
    - No student_id, name, or email appears anywhere in the payload.

    Attributes:
        pseudonym: De-identified student label, e.g. ``'S001'``.
        available_layers: Sorted distinct data layers present in this student's codex.
        questions: One BundleQuestion per CanonicalQuestion in the QuestionSet.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pseudonym: str = Field(..., pattern=r"^S\d{3,}$")
    available_layers: list[Literal["minimal", "rich"]]
    questions: list[BundleQuestion]


# ---------------------------------------------------------------------------
# PII scan
# ---------------------------------------------------------------------------


def assert_no_pii(
    payload: str,
    *,
    known_names: frozenset[str] | None = None,
) -> None:
    """Scan a serialized string for PII and raise on any hit.

    Scans for:
    - 10-digit student IDs (``\\b\\d{10}\\b``).
    - Email addresses (RFC-5321 localpart @ domain pattern).
    - Known Korean names: exact substring match against ``known_names`` (when
      provided).  Generic Hangul heuristics are intentionally avoided to prevent
      false positives on legitimate Korean evidence text.

    Args:
        payload: Serialized string to scan (typically JSON).
        known_names: Frozenset of Korean names to check for.  When ``None``,
            name scanning is skipped (caller must supply names separately or
            rely on the name-free bundle construction guarantee).

    Raises:
        LocatedInputError: On the first PII match found, listing the offending
            value and the scan type.
    """
    m = _SID_PATTERN.search(payload)
    if m:
        raise LocatedInputError(
            f"PII scan: 10-digit student_id found in payload: {m.group()!r}",
            expected="no 10-digit student_id",
            actual=m.group(),
        )

    m = _EMAIL_PATTERN.search(payload)
    if m:
        raise LocatedInputError(
            f"PII scan: Email address found in payload: {m.group()!r}",
            expected="no email address",
            actual=m.group(),
        )

    if known_names:
        for name in known_names:
            if name and name in payload:
                raise LocatedInputError(
                    f"PII scan: known Korean name found in payload: {name!r}",
                    expected="no Korean name",
                    actual=name,
                )


# ---------------------------------------------------------------------------
# build_bundles
# ---------------------------------------------------------------------------


def build_bundles(
    *,
    codex_entries: list[CodexEntry],
    pseudonym_map: list[PseudonymMapEntry],
    question_set: QuestionSet,
) -> list[StudentBundle]:
    """Build one PII-free StudentBundle per student in the codex.

    Groups codex entries by student_id, maps each to a pseudonym, and builds
    a BundleQuestion for every CanonicalQuestion in the question_set.

    All lookups are done in pseudonym space once the initial student_id →
    pseudonym resolution is complete.  The student_id and name_kr are never
    placed in the bundle payload.

    Args:
        codex_entries: All CodexEntry rows for the semester/course.
        pseudonym_map: Full pseudonym map for the same semester/course.
        question_set: Ordered set of canonical questions to answer.

    Returns:
        List of StudentBundle, one per student, sorted ascending by pseudonym.

    Raises:
        LocatedInputError: If any codex student_id has no entry in the
            pseudonym map (fail-fast; no silent skip).
    """
    # Build lookup: student_id → pseudonym
    sid_to_pseudonym: dict[str, str] = {
        entry.student_id: entry.pseudonym for entry in pseudonym_map
    }

    # Group entries by student_id.
    entries_by_sid: dict[str, list[CodexEntry]] = {}
    for entry in codex_entries:
        entries_by_sid.setdefault(entry.student_id, []).append(entry)

    # Fail-fast: every student_id in the codex must have a pseudonym.
    for sid in entries_by_sid:
        if sid not in sid_to_pseudonym:
            raise LocatedInputError(
                f"codex student_id {sid!r} has no entry in pseudonym_map — "
                "run 'ingest' to rebuild the pseudonym map before 'dry-run'",
                file="pseudonym_map.parquet",
                expected="pseudonym for all codex student_ids",
                actual=sid,
            )

    bundles: list[StudentBundle] = []

    for sid in sorted(entries_by_sid):
        student_entries = entries_by_sid[sid]
        pseudonym = sid_to_pseudonym[sid]

        # Compute available_layers from the full entry set for this student.
        available_layers: list[Literal["minimal", "rich"]] = sorted(
            {e.layer for e in student_entries}  # type: ignore[type-var]
        )

        # Build one BundleQuestion per canonical question.
        bundle_questions: list[BundleQuestion] = []
        for q in question_set.questions:
            # answer_question never sees student_id/name — only the pre-filtered
            # entries and the pseudonym we supply.
            qa = answer_question(student_entries, pseudonym=pseudonym, question=q)
            bundle_questions.append(
                BundleQuestion(
                    question_id=q.id,
                    question_text=q.text,
                    answer=qa,
                )
            )

        bundles.append(
            StudentBundle(
                pseudonym=pseudonym,
                available_layers=available_layers,
                questions=bundle_questions,
            )
        )

    # Sort ascending by pseudonym for deterministic output.
    bundles.sort(key=lambda b: b.pseudonym)
    return bundles


# ---------------------------------------------------------------------------
# write_staging
# ---------------------------------------------------------------------------


def write_staging(
    silver_dir: Path,
    bundles: list[StudentBundle],
    *,
    known_names: frozenset[str] | None = None,
) -> list[Path]:
    """Serialize bundles to deterministic JSON and write to staging directory.

    Scans each serialized bundle for PII with assert_no_pii BEFORE writing to
    disk.  Uses atomic_write (temp→rename) for constitution-V atomicity.

    Output path convention: ``silver_dir/staging/{pseudonym}.json``.

    Args:
        silver_dir: metric-codex Silver directory for this semester/course.
        bundles: Pseudonymized student bundles to write.
        known_names: Korean names to scan for (typically the name_kr values from
            the pseudonym map).  When provided, any name appearing in a bundle
            payload raises before that file is written.  The 10-digit id and
            email scans always run regardless.

    Returns:
        List of written paths, one per bundle, in pseudonym order.

    Raises:
        LocatedInputError: If assert_no_pii detects any PII in a bundle JSON.
    """
    staging_dir = silver_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Bundles are PII-free by construction (build_bundles operates in pseudonym
    # space).  write_staging adds an enforcement layer: it scans for 10-digit
    # ids and emails unconditionally, and for the supplied known_names, so any
    # upstream regression that leaked a name fails fast before it hits disk.
    written: list[Path] = []

    for bundle in bundles:
        # model_dump → sort_keys for byte-identical output.
        payload = json.dumps(bundle.model_dump(), sort_keys=True, ensure_ascii=False)

        # PII scan BEFORE writing.
        assert_no_pii(payload, known_names=known_names)

        dest = staging_dir / f"{bundle.pseudonym}.json"

        def _write(tmp: Path, _payload: str = payload) -> None:
            tmp.write_text(_payload, encoding="utf-8")

        atomic_write(dest, _write)
        written.append(dest)

    return written


__all__ = [
    "BundleQuestion",
    "StudentBundle",
    "assert_no_pii",
    "build_bundles",
    "write_staging",
]
