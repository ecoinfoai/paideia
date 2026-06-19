"""T030 — Rich-layer ingest of upstream paideia Silver into CodexEntry rows.

Reads immersio and needs-map Silver parquet files and converts each per-student
fact into a ``layer="rich"`` :class:`CodexEntry`.  Each reader validates every
row against its upstream Pydantic contract and wraps any failure as a located
boundary error naming the offending file (Silver-consumption boundary).

Source → EntryKind mapping (authoritative):

- immersio ``학생지표.parquet`` (``StudentExamMetrics``)
  → ``percentile_section`` / ``percentile_cohort`` / ``z_score`` /
    ``domain_correct_rate`` (per chapter).
- immersio ``exam_result.parquet`` ⊕ ``exam_item.parquet`` (join on
  ``(semester, course_slug, item_no)``) → ``item_correct`` with chapter domain.
- needs-map ``factor_scores.parquet`` (``FactorScoreRow``) → ``axis_score_z``
  for each of the 8 standard axes.
- needs-map ``free_text_categorization.parquet`` (``FreeTextRow``)
  → ``freetext_category`` (one per matched category).
- needs-map ``cluster_assignment.parquet`` (``ClusterAssignmentRow``) +
  ``cluster_names.json`` sidecar → ``cluster_label``.
- immersio ``진단×시험결합.parquet`` (``CombinedAnalysisRow``) — Phase 3 master
  that carries the SAME per-student data as 학생지표 + factor_scores +
  cluster_assignment combined.  When present it supersedes those three for the
  percentile/z/domain/axis_z/cluster kinds (preference rule in
  :func:`read_paideia_sources`), avoiding double counting.

Determinism: entries within each result are sorted by
``(student_id, entry_kind, key)``; dict columns are JSON-decoded with the
standard library (stable).  Rich entries carry ``observed_at=None`` (no
per-event date is available in v1) and ``cohort_year=int(student_id[:4])``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

import pandas as pd
from paideia_shared.schemas import (
    ClusterAssignmentRow,
    CombinedAnalysisRow,
    ExamItem,
    ExamResult,
    FactorScoreRow,
    FreeTextRow,
    StudentExamMetrics,
)
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS
from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind, SourceRecord
from pydantic import BaseModel, ValidationError

from metric_codex.errors import LocatedInputError
from metric_codex.ingest.normalize import normalize_student_id
from metric_codex.ingest.result import SourceReadResult
from metric_codex.output.sha256 import compute_sha256

# Canonical Silver file names (authoritative — research.md §sources).
_F_STUDENT_METRICS = "학생지표.parquet"
_F_EXAM_RESULT = "exam_result.parquet"
_F_EXAM_ITEM = "exam_item.parquet"
_F_COMBINED = "진단×시험결합.parquet"
_F_FACTOR_SCORES = "factor_scores.parquet"
_F_FREE_TEXT = "free_text_categorization.parquet"
_F_CLUSTER_ASSIGNMENT = "cluster_assignment.parquet"
_F_CLUSTER_NAMES = "cluster_names.json"

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _sort_key(entry: CodexEntry) -> tuple[str, str, str]:
    """Deterministic sort key for emitted entries.

    Args:
        entry: A CodexEntry to be ordered.

    Returns:
        ``(student_id, entry_kind value, key)`` tuple.
    """
    return (entry.student_id, entry.entry_kind.value, entry.key)


def _read_parquet(path: Path) -> pd.DataFrame:
    """Read a parquet file into a DataFrame, wrapping I/O failures.

    Args:
        path: Real filesystem path to the ``.parquet`` file.

    Returns:
        The loaded DataFrame.

    Raises:
        LocatedInputError: If the file cannot be parsed as parquet.
    """
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 — boundary: surface as located error
        raise LocatedInputError(
            f"failed to read parquet: {exc}",
            file=path.name,
        ) from exc


def _validate_rows(
    df: pd.DataFrame,
    model: type[_ModelT],
    *,
    filename: str,
) -> list[_ModelT]:
    """Validate each DataFrame row against an upstream Pydantic model.

    Dict columns arrive as JSON strings (the upstream writers serialise them);
    they are decoded before validation so the model sees native ``dict`` values.

    Args:
        df: Loaded parquet rows.
        model: Upstream Pydantic model class to validate each row against.
        filename: Source file name for error location.

    Returns:
        List of validated model instances, in file order.

    Raises:
        LocatedInputError: If any row fails the contract (wraps ValidationError).
    """
    instances: list[_ModelT] = []
    for offset, record in enumerate(df.to_dict(orient="records")):
        # Coercion is part of the located boundary: any decode/normalisation
        # failure must surface as LocatedInputError naming (file, row), never a
        # bare json/numpy exception.
        try:
            clean = {k: _coerce_cell(v) for k, v in record.items()}
            instances.append(model.model_validate(clean))
        except ValidationError as exc:
            raise LocatedInputError(
                f"row failed {model.__name__} contract: {exc}",
                file=filename,
                row=offset + 1,
            ) from exc
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise LocatedInputError(
                f"failed to decode row cell: {exc}",
                file=filename,
                row=offset + 1,
            ) from exc
    return instances


def _coerce_cell(value: object) -> object:
    """Normalise one parquet cell value for Pydantic validation.

    Decodes JSON-string dict/list columns to native ``dict``/``list``, converts
    numpy arrays (list columns) to Python lists, and maps pandas NA / NaN to
    ``None``.

    A string that *looks* like a JSON container (``{...}`` or ``[...]``) but does
    not parse is returned unchanged rather than raising — a genuine free-text
    value such as ``"{health}"`` must pass through verbatim. Downstream Pydantic
    validation then rejects any container-shaped string that lands in a non-text
    field, keeping the failure inside the located-error boundary.

    Args:
        value: Raw cell value from ``DataFrame.to_dict``.

    Returns:
        A JSON/Pydantic-friendly Python value.
    """
    # JSON-encoded container column (e.g. chapter_correct_rates dict, list cols).
    if isinstance(value, str):
        stripped = value.strip()
        looks_json = (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        )
        if looks_json:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Not actually JSON (e.g. a free-text category "{health}"):
                # return the raw string and let Pydantic decide if it fits.
                return value
        return value
    # pyarrow list columns surface as numpy arrays / lists.
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return value.tolist()
    if isinstance(value, list):
        return value
    # pandas NA / NaN scalar → None.
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    return value


def _cohort_year(student_id: str, *, filename: str, row: int) -> int:
    """Derive cohort year from a normalized student id, validating the range.

    Args:
        student_id: 10-digit canonical student id.
        filename: Source file name for error location.
        row: 1-based row number for error location.

    Returns:
        Enrollment year in [2000, 2100].

    Raises:
        LocatedInputError: If the year prefix is outside [2000, 2100].
    """
    year = int(student_id[:4])
    if not (2000 <= year <= 2100):
        raise LocatedInputError(
            f"cohort_year {year} derived from id prefix is out of range [2000, 2100]",
            file=filename,
            row=row,
            expected="student id starting with a year in [2000, 2100]",
            actual=student_id,
        )
    return year


def _source_record(
    *,
    source_id: str,
    origin_module: str,
    path: Path,
    source_path: str,
    ingested_at: str,
) -> SourceRecord:
    """Build the provenance record for one read Silver file.

    Args:
        source_id: Logical source identifier (FK referenced by CodexEntry).
        origin_module: Owning paideia module (``"immersio"`` / ``"needs-map"``).
        path: Real filesystem path to the source file (hashed for ``sha256``).
        source_path: Repo-relative path string recorded verbatim for
            cross-machine-deterministic manifests.
        ingested_at: ISO-8601 UTC timestamp of ingestion.

    Returns:
        A ``SourceRecord`` with ``origin_layer="silver"`` and the file's digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist (from ``compute_sha256``).
    """
    return SourceRecord(
        source_id=source_id,
        origin_module=origin_module,  # type: ignore[arg-type]
        origin_layer="silver",
        source_path=source_path,
        sha256=compute_sha256(path),
        ingested_at=ingested_at,
    )


# ---------------------------------------------------------------------------
# Shared row-level emitters (so combined + individual reuse one code path)
# ---------------------------------------------------------------------------


def _emit_percentile_z_domain(
    *,
    student_id: str,
    cohort_year: int,
    semester: str,
    source_id: str,
    section_percentile: float | None,
    cohort_percentile: float | None,
    z_score: float | None,
    chapter_correct_rates: dict[str, float],
) -> list[CodexEntry]:
    """Emit percentile/z/domain entries for one student (None values skipped)."""
    out: list[CodexEntry] = []

    def _num(kind: EntryKind, key: str, value: float | None, domain: str | None) -> None:
        if value is None:
            return
        out.append(
            CodexEntry(
                student_id=student_id,
                semester=semester,
                cohort_year=cohort_year,
                layer="rich",
                entry_kind=kind,
                key=key,
                value_num=float(value),
                domain=domain,
                source_id=source_id,
                observed_at=None,
            )
        )

    _num(EntryKind.percentile_section, "percentile_section", section_percentile, None)
    _num(EntryKind.percentile_cohort, "percentile_cohort", cohort_percentile, None)
    _num(EntryKind.z_score, "z_score", z_score, None)
    for chapter, rate in chapter_correct_rates.items():
        _num(
            EntryKind.domain_correct_rate,
            f"chapter_correct_rate:{chapter}",
            rate,
            chapter,
        )
    return out


def _emit_axis_z(
    *,
    student_id: str,
    cohort_year: int,
    semester: str,
    source_id: str,
    axis_z: dict[str, float | None],
) -> list[CodexEntry]:
    """Emit axis_score_z entries (None axes skipped)."""
    out: list[CodexEntry] = []
    for axis in STANDARD_AXIS_KEYS:
        value = axis_z.get(axis)
        if value is None:
            continue
        out.append(
            CodexEntry(
                student_id=student_id,
                semester=semester,
                cohort_year=cohort_year,
                layer="rich",
                entry_kind=EntryKind.axis_score_z,
                key=f"axis_z:{axis}",
                value_num=float(value),
                domain=axis,
                source_id=source_id,
                observed_at=None,
            )
        )
    return out


def _cluster_label_entry(
    *,
    student_id: str,
    cohort_year: int,
    semester: str,
    source_id: str,
    label: str,
) -> CodexEntry:
    """Build one cluster_label entry (value_text=label)."""
    return CodexEntry(
        student_id=student_id,
        semester=semester,
        cohort_year=cohort_year,
        layer="rich",
        entry_kind=EntryKind.cluster_label,
        key="cluster_label",
        value_text=label,
        domain=None,
        source_id=source_id,
        observed_at=None,
    )


# ---------------------------------------------------------------------------
# Per-file readers
# ---------------------------------------------------------------------------


def read_student_metrics(
    path: Path,
    *,
    semester: str,
    ingested_at: str,
    source_path: str,
) -> SourceReadResult:
    """Read immersio ``학생지표.parquet`` into rich percentile/z/domain entries.

    Args:
        path: Real filesystem path to the parquet file.
        semester: Academic semester code embedded in every emitted entry.
        ingested_at: ISO-8601 UTC timestamp for the SourceRecord.
        source_path: Repo-relative path string recorded verbatim in the
            SourceRecord (caller-supplied for cross-machine determinism).

    Returns:
        A ``SourceReadResult`` with sorted entries, the SourceRecord, and an
        ``identities`` map of student_id → name_kr.

    Raises:
        LocatedInputError: On unreadable parquet or any row that fails the
            ``StudentExamMetrics`` contract.
    """
    source_id = "immersio:학생지표"
    df = _read_parquet(path)
    rows = _validate_rows(df, StudentExamMetrics, filename=path.name)

    entries: list[CodexEntry] = []
    identities: dict[str, str | None] = {}
    for offset, row in enumerate(rows):
        sid = normalize_student_id(row.student_id, source=path.name, row=offset + 1)
        cohort_year = _cohort_year(sid, filename=path.name, row=offset + 1)
        identities[sid] = row.name_kr
        entries.extend(
            _emit_percentile_z_domain(
                student_id=sid,
                cohort_year=cohort_year,
                semester=semester,
                source_id=source_id,
                section_percentile=row.section_percentile,
                cohort_percentile=row.cohort_percentile,
                z_score=row.z_score,
                chapter_correct_rates=row.chapter_correct_rates,
            )
        )

    entries.sort(key=_sort_key)
    return SourceReadResult(
        entries=entries,
        source_record=_source_record(
            source_id=source_id,
            origin_module="immersio",
            path=path,
            source_path=source_path,
            ingested_at=ingested_at,
        ),
        identities=identities,
    )


def read_exam_results(
    result_path: Path,
    item_path: Path,
    *,
    semester: str,
    ingested_at: str,
    source_path: str,
) -> SourceReadResult:
    """Read immersio ``exam_result.parquet`` ⊕ ``exam_item.parquet`` into entries.

    Joins each graded response to its question's chapter on
    ``(semester, course_slug, item_no)`` and emits one ``item_correct`` entry per
    graded item (``value_num`` 1.0/0.0, ``item_ref`` = item_no, ``domain`` =
    chapter or ``None``).  Ungraded items (``is_correct is None``) are skipped.

    Args:
        result_path: Real filesystem path to ``exam_result.parquet``.
        item_path: Real filesystem path to ``exam_item.parquet``.
        semester: Academic semester code embedded in every emitted entry.
        ingested_at: ISO-8601 UTC timestamp for the SourceRecord.
        source_path: Repo-relative path string for the SourceRecord (the
            ``exam_result`` file is the recorded source path).

    Returns:
        A ``SourceReadResult``; identities map every student_id → None (these
        files carry no name).

    Raises:
        LocatedInputError: On unreadable parquet or any row that fails the
            ``ExamResult`` / ``ExamItem`` contract.
    """
    source_id = "immersio:exam_result"
    results = _validate_rows(_read_parquet(result_path), ExamResult, filename=result_path.name)
    items = _validate_rows(_read_parquet(item_path), ExamItem, filename=item_path.name)

    # The natural key encodes only ``item_no``; two courses sharing an item_no in
    # one file would collide. Fail fast rather than silently overwrite.
    distinct_courses = sorted({r.course_slug for r in results})
    if len(distinct_courses) > 1:
        raise LocatedInputError(
            f"exam_result spans multiple course_slug values: {distinct_courses}",
            file=result_path.name,
            expected="a single course_slug per exam_result file",
            actual=", ".join(distinct_courses),
        )

    # Join key → chapter.
    chapter_by_item: dict[tuple[str, str, int], str | None] = {}
    for it in items:
        chapter_by_item[(it.semester, it.course_slug, it.item_no)] = it.chapter

    entries: list[CodexEntry] = []
    identities: dict[str, str | None] = {}
    for offset, row in enumerate(results):
        sid = normalize_student_id(row.student_id, source=result_path.name, row=offset + 1)
        cohort_year = _cohort_year(sid, filename=result_path.name, row=offset + 1)
        identities.setdefault(sid, None)
        if row.is_correct is None:
            continue  # ungraded — skip this item (legitimate absence)
        chapter = chapter_by_item.get((row.semester, row.course_slug, row.item_no))
        entries.append(
            CodexEntry(
                student_id=sid,
                semester=semester,
                cohort_year=cohort_year,
                layer="rich",
                entry_kind=EntryKind.item_correct,
                key=f"item_correct:{row.item_no}",
                value_num=1.0 if row.is_correct else 0.0,
                domain=chapter,
                item_ref=str(row.item_no),
                source_id=source_id,
                observed_at=None,
            )
        )

    entries.sort(key=_sort_key)
    return SourceReadResult(
        entries=entries,
        source_record=_source_record(
            source_id=source_id,
            origin_module="immersio",
            path=result_path,
            source_path=source_path,
            ingested_at=ingested_at,
        ),
        identities=identities,
    )


def read_factor_scores(
    path: Path,
    *,
    semester: str,
    ingested_at: str,
    source_path: str,
) -> SourceReadResult:
    """Read needs-map ``factor_scores.parquet`` into ``axis_score_z`` entries.

    Off-roster rows (``on_roster=False``) are skipped entirely; per-axis None
    z-scores (missing axes) are skipped individually.

    Args:
        path: Real filesystem path to the parquet file.
        semester: Academic semester code embedded in every emitted entry.
        ingested_at: ISO-8601 UTC timestamp for the SourceRecord.
        source_path: Repo-relative path string for the SourceRecord.

    Returns:
        A ``SourceReadResult``; identities map every on-roster student_id → None
        (this file carries no name).

    Raises:
        LocatedInputError: On unreadable parquet or any row that fails the
            ``FactorScoreRow`` contract.
    """
    source_id = "needs-map:factor_scores"
    rows = _validate_rows(_read_parquet(path), FactorScoreRow, filename=path.name)

    entries: list[CodexEntry] = []
    identities: dict[str, str | None] = {}
    for offset, row in enumerate(rows):
        if not row.on_roster:
            continue  # off-roster respondent — not this course's student
        sid = normalize_student_id(row.student_id, source=path.name, row=offset + 1)
        cohort_year = _cohort_year(sid, filename=path.name, row=offset + 1)
        identities[sid] = None
        axis_z = {axis: getattr(row, f"{axis}_z") for axis in STANDARD_AXIS_KEYS}
        entries.extend(
            _emit_axis_z(
                student_id=sid,
                cohort_year=cohort_year,
                semester=semester,
                source_id=source_id,
                axis_z=axis_z,
            )
        )

    entries.sort(key=_sort_key)
    return SourceReadResult(
        entries=entries,
        source_record=_source_record(
            source_id=source_id,
            origin_module="needs-map",
            path=path,
            source_path=source_path,
            ingested_at=ingested_at,
        ),
        identities=identities,
    )


def read_free_text(
    path: Path,
    *,
    semester: str,
    ingested_at: str,
    source_path: str,
) -> SourceReadResult:
    """Read needs-map ``free_text_categorization.parquet`` into freetext entries.

    Emits one ``freetext_category`` entry (``value_text`` = category) per matched
    category.  Rows with ``match_source == 'no_response'`` or an empty
    ``matched_categories`` list emit nothing.

    Args:
        path: Real filesystem path to the parquet file.
        semester: Academic semester code embedded in every emitted entry.
        ingested_at: ISO-8601 UTC timestamp for the SourceRecord.
        source_path: Repo-relative path string for the SourceRecord.

    Returns:
        A ``SourceReadResult``; identities map every student_id → None.

    Raises:
        LocatedInputError: On unreadable parquet or any row that fails the
            ``FreeTextRow`` contract.
    """
    source_id = "needs-map:free_text_categorization"
    rows = _validate_rows(_read_parquet(path), FreeTextRow, filename=path.name)

    entries: list[CodexEntry] = []
    identities: dict[str, str | None] = {}
    for offset, row in enumerate(rows):
        sid = normalize_student_id(row.student_id, source=path.name, row=offset + 1)
        cohort_year = _cohort_year(sid, filename=path.name, row=offset + 1)
        identities.setdefault(sid, None)
        if row.match_source == "no_response" or not row.matched_categories:
            continue
        for category in row.matched_categories:
            entries.append(
                CodexEntry(
                    student_id=sid,
                    semester=semester,
                    cohort_year=cohort_year,
                    layer="rich",
                    entry_kind=EntryKind.freetext_category,
                    key=f"freetext:{row.item_id}:{category}",
                    value_text=category,
                    domain=row.item_id,
                    source_id=source_id,
                    observed_at=None,
                )
            )

    entries.sort(key=_sort_key)
    return SourceReadResult(
        entries=entries,
        source_record=_source_record(
            source_id=source_id,
            origin_module="needs-map",
            path=path,
            source_path=source_path,
            ingested_at=ingested_at,
        ),
        identities=identities,
    )


def read_cluster_assignment(
    assignment_path: Path,
    names_path: Path,
    *,
    semester: str,
    ingested_at: str,
    source_path: str,
) -> SourceReadResult:
    """Read needs-map cluster assignment + names sidecar into label entries.

    Looks up each student's ``cluster_id`` in the ``cluster_names.json`` sidecar
    (int cluster_id → label) and emits one ``cluster_label`` entry per student.

    Args:
        assignment_path: Real filesystem path to ``cluster_assignment.parquet``.
        names_path: Real filesystem path to ``cluster_names.json``.
        semester: Academic semester code embedded in every emitted entry.
        ingested_at: ISO-8601 UTC timestamp for the SourceRecord.
        source_path: Repo-relative path string for the SourceRecord (the
            ``cluster_assignment`` parquet is the recorded source path).

    Returns:
        A ``SourceReadResult``; identities map every student_id → None.

    Raises:
        LocatedInputError: On unreadable parquet, malformed names sidecar, a
            row that fails the ``ClusterAssignmentRow`` contract, or a
            ``cluster_id`` absent from the names sidecar.
    """
    source_id = "needs-map:cluster_assignment"
    rows = _validate_rows(
        _read_parquet(assignment_path), ClusterAssignmentRow, filename=assignment_path.name
    )
    names = _load_cluster_names(names_path)

    entries: list[CodexEntry] = []
    identities: dict[str, str | None] = {}
    for offset, row in enumerate(rows):
        sid = normalize_student_id(row.student_id, source=assignment_path.name, row=offset + 1)
        cohort_year = _cohort_year(sid, filename=assignment_path.name, row=offset + 1)
        identities.setdefault(sid, None)
        if row.cluster_id not in names:
            raise LocatedInputError(
                f"cluster_id {row.cluster_id} has no label in {names_path.name}",
                file=assignment_path.name,
                row=offset + 1,
                expected="cluster_id present in cluster_names.json",
                actual=str(row.cluster_id),
            )
        entries.append(
            _cluster_label_entry(
                student_id=sid,
                cohort_year=cohort_year,
                semester=semester,
                source_id=source_id,
                label=names[row.cluster_id],
            )
        )

    entries.sort(key=_sort_key)
    return SourceReadResult(
        entries=entries,
        source_record=_source_record(
            source_id=source_id,
            origin_module="needs-map",
            path=assignment_path,
            source_path=source_path,
            ingested_at=ingested_at,
        ),
        identities=identities,
    )


def _load_cluster_names(path: Path) -> dict[int, str]:
    """Load the ``cluster_names.json`` sidecar into an int→label map.

    JSON object keys are strings; they are coerced to ints (the cluster ids).

    Args:
        path: Real filesystem path to ``cluster_names.json``.

    Returns:
        Mapping of cluster_id (int) → label (str).

    Raises:
        LocatedInputError: If the file is not valid JSON, not an object, or has
            a non-integer key.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LocatedInputError(
            f"failed to parse cluster names JSON: {exc}",
            file=path.name,
        ) from exc
    if not isinstance(raw, dict):
        raise LocatedInputError(
            "cluster names sidecar must be a JSON object",
            file=path.name,
            expected="object mapping cluster_id → label",
            actual=type(raw).__name__,
        )
    names: dict[int, str] = {}
    for key, label in raw.items():
        try:
            cluster_id = int(key)
        except (TypeError, ValueError) as exc:
            raise LocatedInputError(
                f"non-integer cluster id key {key!r} in cluster names sidecar",
                file=path.name,
                expected="integer cluster id key",
                actual=repr(key),
            ) from exc
        names[cluster_id] = str(label)
    return names


def read_combined_analysis(
    path: Path,
    *,
    semester: str,
    ingested_at: str,
    source_path: str,
) -> SourceReadResult:
    """Read immersio ``진단×시험결합.parquet`` into the superseding entry set.

    Derives ``percentile_section`` / ``percentile_cohort`` / ``z_score`` /
    ``domain_correct_rate`` / ``axis_score_z`` / ``cluster_label`` from the
    Phase 3 master row (which already merges 학생지표 + factor_scores +
    cluster_assignment).  None values are skipped per the same rules as the
    individual readers.

    Args:
        path: Real filesystem path to the parquet file.
        semester: Academic semester code embedded in every emitted entry.
        ingested_at: ISO-8601 UTC timestamp for the SourceRecord.
        source_path: Repo-relative path string for the SourceRecord.

    Returns:
        A ``SourceReadResult``; identities map student_id → name_kr.

    Raises:
        LocatedInputError: On unreadable parquet or any row that fails the
            ``CombinedAnalysisRow`` contract.
    """
    source_id = "immersio:진단×시험결합"
    rows = _validate_rows(_read_parquet(path), CombinedAnalysisRow, filename=path.name)

    entries: list[CodexEntry] = []
    identities: dict[str, str | None] = {}
    for offset, row in enumerate(rows):
        sid = normalize_student_id(row.student_id, source=path.name, row=offset + 1)
        cohort_year = _cohort_year(sid, filename=path.name, row=offset + 1)
        identities[sid] = row.name_kr

        entries.extend(
            _emit_percentile_z_domain(
                student_id=sid,
                cohort_year=cohort_year,
                semester=semester,
                source_id=source_id,
                section_percentile=row.section_percentile,
                cohort_percentile=row.cohort_percentile,
                z_score=row.z_score,
                chapter_correct_rates=row.chapter_correct_rates,
            )
        )
        axis_z = {axis: getattr(row, f"{axis}_z") for axis in STANDARD_AXIS_KEYS}
        entries.extend(
            _emit_axis_z(
                student_id=sid,
                cohort_year=cohort_year,
                semester=semester,
                source_id=source_id,
                axis_z=axis_z,
            )
        )
        if row.cluster_label is not None:
            entries.append(
                _cluster_label_entry(
                    student_id=sid,
                    cohort_year=cohort_year,
                    semester=semester,
                    source_id=source_id,
                    label=row.cluster_label,
                )
            )

    entries.sort(key=_sort_key)
    return SourceReadResult(
        entries=entries,
        source_record=_source_record(
            source_id=source_id,
            origin_module="immersio",
            path=path,
            source_path=source_path,
            ingested_at=ingested_at,
        ),
        identities=identities,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def read_paideia_sources(
    *,
    immersio_silver_dir: Path | None,
    needsmap_silver_dir: Path | None,
    semester: str,
    data_root: Path,
    ingested_at: str,
) -> list[SourceReadResult]:
    """Read all present immersio/needs-map Silver files into rich entries.

    Applies the combined-vs-individual preference rule to avoid double counting:
    when immersio ``진단×시험결합.parquet`` exists it supersedes ``학생지표`` +
    ``factor_scores`` + ``cluster_assignment`` for the percentile/z/domain/
    axis_z/cluster kinds, so those three individual files are NOT read.  The
    per-item layer (``exam_result`` ⊕ ``exam_item``) and the free-text layer
    (``free_text_categorization``) have no combined equivalent and are always
    read when present.

    A missing optional file is a legitimate degrade (that layer is simply
    absent) and never raises; only a present-but-malformed file raises a located
    error.

    Args:
        immersio_silver_dir: Directory holding immersio Silver parquet files, or
            ``None`` if no immersio Silver is available.
        needsmap_silver_dir: Directory holding needs-map Silver parquet files,
            or ``None`` if no needs-map Silver is available.
        semester: Academic semester code embedded in every emitted entry.
        data_root: The ``data/`` root; each file's ``source_path`` is derived as
            ``path.relative_to(data_root)`` for cross-machine determinism.
        ingested_at: ISO-8601 UTC timestamp for every SourceRecord.

    Returns:
        One ``SourceReadResult`` per file actually read, ordered deterministically
        by ``source_id``.

    Raises:
        LocatedInputError: On any present-but-malformed Silver file.
    """
    results: list[SourceReadResult] = []

    def _sp(path: Path) -> str:
        return str(path.relative_to(data_root))

    combined_present = (
        immersio_silver_dir is not None and (immersio_silver_dir / _F_COMBINED).is_file()
    )

    if immersio_silver_dir is not None:
        if combined_present:
            combined = immersio_silver_dir / _F_COMBINED
            results.append(
                read_combined_analysis(
                    combined,
                    semester=semester,
                    ingested_at=ingested_at,
                    source_path=_sp(combined),
                )
            )
        else:
            metrics = immersio_silver_dir / _F_STUDENT_METRICS
            if metrics.is_file():
                results.append(
                    read_student_metrics(
                        metrics,
                        semester=semester,
                        ingested_at=ingested_at,
                        source_path=_sp(metrics),
                    )
                )

        # Per-item layer — always read when both files present.
        exam_result = immersio_silver_dir / _F_EXAM_RESULT
        exam_item = immersio_silver_dir / _F_EXAM_ITEM
        if exam_result.is_file() and exam_item.is_file():
            results.append(
                read_exam_results(
                    exam_result,
                    exam_item,
                    semester=semester,
                    ingested_at=ingested_at,
                    source_path=_sp(exam_result),
                )
            )

    if needsmap_silver_dir is not None:
        if not combined_present:
            factor = needsmap_silver_dir / _F_FACTOR_SCORES
            if factor.is_file():
                results.append(
                    read_factor_scores(
                        factor,
                        semester=semester,
                        ingested_at=ingested_at,
                        source_path=_sp(factor),
                    )
                )
            assignment = needsmap_silver_dir / _F_CLUSTER_ASSIGNMENT
            names = needsmap_silver_dir / _F_CLUSTER_NAMES
            if assignment.is_file() and names.is_file():
                results.append(
                    read_cluster_assignment(
                        assignment,
                        names,
                        semester=semester,
                        ingested_at=ingested_at,
                        source_path=_sp(assignment),
                    )
                )

        # Free-text layer — always read when present.
        free_text = needsmap_silver_dir / _F_FREE_TEXT
        if free_text.is_file():
            results.append(
                read_free_text(
                    free_text,
                    semester=semester,
                    ingested_at=ingested_at,
                    source_path=_sp(free_text),
                )
            )

    results.sort(key=lambda r: r.source_record.source_id)
    return results


__all__ = [
    "read_cluster_assignment",
    "read_combined_analysis",
    "read_exam_results",
    "read_factor_scores",
    "read_free_text",
    "read_paideia_sources",
    "read_student_metrics",
]
