"""Unit tests for ``metric_codex.store.codex.accumulate`` (FR-006 / FR-009).

Directly exercises the in-memory accumulation contract without touching the
filesystem:

- idempotent: re-applying identical entries does not grow the result;
- additive: a new natural key appends a row;
- correction: a colliding natural key replaces the old entry in place;
- deterministic order: result sorted by the natural key.
"""

from __future__ import annotations

from metric_codex.ingest.result import SourceReadResult
from metric_codex.store.codex import accumulate
from paideia_shared.schemas import CodexEntry, EntryKind, SourceRecord

_SEMESTER = "2026-1"
_SID_A = "2026000001"
_SID_B = "2026000002"
_SOURCE_ID = "school_excel:성적출석.xlsx"


def _entry(student_id: str, kind: EntryKind, value: float) -> CodexEntry:
    return CodexEntry(
        student_id=student_id,
        semester=_SEMESTER,
        cohort_year=2026,
        layer="minimal",
        entry_kind=kind,
        key=kind.value,
        value_num=value,
        source_id=_SOURCE_ID,
    )


def _record() -> SourceRecord:
    return SourceRecord(
        source_id=_SOURCE_ID,
        origin_module="school",
        origin_layer="bronze",
        source_path="bronze/metric-codex/2026-1-anatomy/성적출석.xlsx",
        sha256="a" * 64,
        ingested_at="2026-06-19T00:00:00Z",
    )


def _result(entries: list[CodexEntry]) -> SourceReadResult:
    return SourceReadResult(entries=entries, source_record=_record(), identities={})


def test_accumulate_additive() -> None:
    """A new natural key is appended to the existing set."""
    existing = [_entry(_SID_A, EntryKind.score_total, 85.0)]
    new = [_entry(_SID_B, EntryKind.score_total, 70.0)]
    entries, _records = accumulate([_result(new)], existing, [])
    assert {e.student_id for e in entries} == {_SID_A, _SID_B}
    assert len(entries) == 2


def test_accumulate_idempotent() -> None:
    """Re-applying an identical entry does not grow the result."""
    existing = [_entry(_SID_A, EntryKind.score_total, 85.0)]
    same = [_entry(_SID_A, EntryKind.score_total, 85.0)]
    entries, _records = accumulate([_result(same)], existing, [])
    assert len(entries) == 1


def test_accumulate_correction_replaces_in_place() -> None:
    """A colliding natural key replaces the old value; count unchanged."""
    existing = [_entry(_SID_A, EntryKind.score_total, 85.0)]
    corrected = [_entry(_SID_A, EntryKind.score_total, 99.0)]
    entries, _records = accumulate([_result(corrected)], existing, [])
    assert len(entries) == 1
    assert entries[0].value_num == 99.0


def test_accumulate_deterministic_order() -> None:
    """Result is sorted by the natural key regardless of input order."""
    new = [
        _entry(_SID_B, EntryKind.score_total, 70.0),
        _entry(_SID_A, EntryKind.attendance, 15.0),
        _entry(_SID_A, EntryKind.score_total, 85.0),
    ]
    entries, _records = accumulate([_result(new)], [], [])
    # Natural key = (student_id, source_id, entry_kind, key, item_ref); single
    # source here so order reduces to (student_id, entry_kind value).
    assert [(e.student_id, e.entry_kind.value) for e in entries] == [
        (_SID_A, "attendance"),
        (_SID_A, "score_total"),
        (_SID_B, "score_total"),
    ]


def test_accumulate_records_merge_by_source_id() -> None:
    """Source records merge by source_id (new replaces old), sorted by source_id."""
    old = _record()
    entries, records = accumulate([_result([])], [], [old])
    assert len(records) == 1
    assert records[0].source_id == _SOURCE_ID
