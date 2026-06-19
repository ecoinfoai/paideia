"""T030 — Unit tests for the rich-layer immersio/needs-map Silver readers.

Tests written before implementation per the TDD mandate.

Synthetic parquet fixtures are built with pandas ``to_parquet`` and laid out
in a temporary ``data_root`` mirroring the real Silver directory structure:

    data/silver/immersio/{semester}-{course}/...
    data/silver/needs-map/{semester}-{course}/...

Dict columns (e.g. ``chapter_correct_rates``) are stored as JSON strings, as
the upstream writers emit them.

Covers:
- 학생지표 → percentile_section/cohort/z_score + per-chapter domain_correct_rate
  (JSON dict decoded); exam_taken=False → score entries skipped, identity kept.
- exam_result ⊕ exam_item → item_correct entries (item_ref=item_no, value 1/0,
  domain=chapter from join); ungraded (is_correct None) item skipped.
- factor_scores → axis_score_z for 8 axes; missing/None skipped; off-roster skipped.
- free_text_categorization → one freetext_category per matched category; empty/
  no_response skipped.
- cluster_assignment ⊕ cluster_names.json → cluster_label entries (value_text).
- Preference: 진단×시험결합 present → percentiles/axis_z/cluster come from it and
  학생지표/factor_scores/cluster_assignment are not double-read.
- Degrade: missing optional files → no error, fewer entries.
- Determinism: two reads → equal entries; entries sorted.
- Malformed parquet (row fails the upstream Pydantic contract) → LocatedInputError.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from metric_codex.errors import LocatedInputError
from metric_codex.ingest.paideia_sources import (
    read_cluster_assignment,
    read_combined_analysis,
    read_exam_results,
    read_factor_scores,
    read_free_text,
    read_paideia_sources,
    read_student_metrics,
)
from metric_codex.ingest.result import SourceReadResult
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS
from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEMESTER}-{_COURSE}"
_COURSE_SLUG = "anatomy"
_INGESTED_AT = "2026-06-19T00:00:00Z"

_SID_A = "2026000001"
_SID_B = "2026000002"
_SID_OFF = "2025000099"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _silver_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create the silver directory layout under a fresh data_root.

    Returns:
        ``(data_root, immersio_silver_dir, needsmap_silver_dir)``.
    """
    data_root = tmp_path / "data"
    immersio_dir = data_root / "silver" / "immersio" / _KEY
    needsmap_dir = data_root / "silver" / "needs-map" / _KEY
    immersio_dir.mkdir(parents=True)
    needsmap_dir.mkdir(parents=True)
    return data_root, immersio_dir, needsmap_dir


def _write_student_metrics(path: Path) -> None:
    rows = [
        {
            "student_id": _SID_A,
            "name_kr": "김철수",
            "section": "A",
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "exam_taken": True,
            "total_score": 80.0,
            "score_percent": 80.0,
            "section_percentile": 75.0,
            "cohort_percentile": 70.0,
            "z_score": 1.2,
            "chapter_correct_rates": json.dumps(
                {"순환": 0.9, "호흡": 0.5}, ensure_ascii=False, sort_keys=True
            ),
            "source_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "difficulty_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
            "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
            "interest_chapters_correct_rate": None,
            "aversion_chapters_correct_rate": None,
        },
        {
            "student_id": _SID_B,
            "name_kr": "이영희",
            "section": "A",
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "exam_taken": False,  # absent → score fields None → those entries skipped
            "total_score": None,
            "score_percent": None,
            "section_percentile": None,
            "cohort_percentile": None,
            "z_score": None,
            "chapter_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "source_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "difficulty_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
            "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
            "interest_chapters_correct_rate": None,
            "aversion_chapters_correct_rate": None,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)


def _write_exam_result(path: Path) -> None:
    rows = [
        {
            "student_id": _SID_A,
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 1,
            "response": "3",
            "is_correct": True,
            "score": 1.0,
        },
        {
            "student_id": _SID_A,
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 2,
            "response": "1",
            "is_correct": False,
            "score": 0.0,
        },
        {
            "student_id": _SID_A,
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 3,
            "response": None,  # ungraded → is_correct None → skipped
            "is_correct": None,
            "score": None,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)


def _write_exam_item(path: Path) -> None:
    rows = [
        {
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 1,
            "chapter": "순환",
            "source": "textbook",
            "expected_difficulty": "easy",
            "bloom": "knowledge",
            "answer_key": "3",
            "points": 1.0,
            "text": None,
            "distractors": None,
        },
        {
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 2,
            "chapter": None,  # no chapter → domain None
            "source": "quiz",
            "expected_difficulty": "medium",
            "bloom": "comprehension",
            "answer_key": "2",
            "points": 1.0,
            "text": None,
            "distractors": None,
        },
        {
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 3,
            "chapter": "호흡",
            "source": "textbook",
            "expected_difficulty": "hard",
            "bloom": "analysis",
            "answer_key": "4",
            "points": 1.0,
            "text": None,
            "distractors": None,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)


def _factor_row(student_id: str, *, on_roster: bool, with_scores: bool) -> dict:
    row: dict[str, object] = {
        "student_id": student_id,
        "on_roster": on_roster,
        "responded": with_scores,
        "section": "A" if on_roster else None,
    }
    for i, axis in enumerate(STANDARD_AXIS_KEYS):
        if with_scores and axis != "feedback_seeking":
            row[axis] = float(i)
            row[f"{axis}_z"] = float(i) * 0.5
            row[f"{axis}_missing"] = False
        else:
            # feedback_seeking missing for A even when responded → that axis skipped
            row[axis] = None
            row[f"{axis}_z"] = None
            row[f"{axis}_missing"] = True
    return row


def _write_factor_scores(path: Path) -> None:
    rows = [
        _factor_row(_SID_A, on_roster=True, with_scores=True),
        _factor_row(_SID_OFF, on_roster=False, with_scores=True),  # off-roster → skipped
    ]
    pd.DataFrame(rows).to_parquet(path)


def _write_free_text(path: Path) -> None:
    rows = [
        {
            "student_id": _SID_A,
            "item_id": "q9",
            "matched_categories": ["health", "career"],
            "match_source": "dictionary",
            "raw_length": 42,
        },
        {
            "student_id": _SID_A,
            "item_id": "q10",
            "matched_categories": [],  # empty → nothing emitted
            "match_source": "uncategorized",
            "raw_length": 5,
        },
        {
            "student_id": _SID_B,
            "item_id": "q9",
            "matched_categories": [],  # no_response → nothing emitted
            "match_source": "no_response",
            "raw_length": 0,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)


def _write_cluster_assignment(path: Path) -> None:
    rows = [
        {"student_id": _SID_A, "cluster_id": 0, "distance_to_centroid": 0.3},
        {"student_id": _SID_B, "cluster_id": 1, "distance_to_centroid": 0.5},
    ]
    pd.DataFrame(rows).to_parquet(path)


def _write_cluster_names(path: Path) -> None:
    path.write_text(
        json.dumps({"0": "성실형", "1": "도전형"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _combined_row(student_id: str, *, exam_taken: bool, with_axes: bool) -> dict:
    row: dict[str, object] = {
        "student_id": student_id,
        "name_kr": "김철수" if student_id == _SID_A else "이영희",
        "on_roster": True,
        "section": "A",
        "semester": _SEMESTER,
        "course_slug": _COURSE_SLUG,
    }
    for axis in STANDARD_AXIS_KEYS:
        if with_axes and axis != "feedback_seeking":
            row[f"{axis}_raw"] = 1.0
            row[f"{axis}_z"] = 0.7
            row[f"{axis}_missing"] = False
        else:
            row[f"{axis}_raw"] = None
            row[f"{axis}_z"] = None
            row[f"{axis}_missing"] = True
    row["cluster_id"] = 0 if with_axes else None
    row["cluster_label"] = "성실형" if with_axes else None
    row["cluster_distance"] = 0.3 if with_axes else None
    row["exam_taken"] = exam_taken
    row["total_score"] = 80.0 if exam_taken else None
    row["score_percent"] = 80.0 if exam_taken else None
    row["section_percentile"] = 75.0 if exam_taken else None
    row["cohort_percentile"] = 70.0 if exam_taken else None
    row["z_score"] = 1.2 if exam_taken else None
    row["chapter_correct_rates"] = json.dumps(
        {"순환": 0.9} if exam_taken else {}, ensure_ascii=False, sort_keys=True
    )
    for col in (
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
    ):
        row[col] = json.dumps({}, ensure_ascii=False, sort_keys=True)
    row["interest_chapters_correct_rate"] = None
    row["aversion_chapters_correct_rate"] = None
    for col in (
        "prior_readiness_q5",
        "prior_readiness_q6",
        "time_pattern_q21",
        "time_pattern_q22",
        "time_pattern_q23",
        "interest_topics_q9",
        "interest_topics_q10",
        "interest_topics_q11",
        "categorical_intent_q12",
        "categorical_intent_q13",
    ):
        row[col] = None
    row["진단응답"] = with_axes
    row["시험응시"] = exam_taken
    row["needs_map_schema_version"] = "1.1.0"
    row["immersio_phase2_schema_version"] = "1.0.0"
    return row


def _write_combined(path: Path) -> None:
    rows = [
        _combined_row(_SID_A, exam_taken=True, with_axes=True),
    ]
    pd.DataFrame(rows).to_parquet(path)


# ---------------------------------------------------------------------------
# Per-file reader tests
# ---------------------------------------------------------------------------


def _by_kind(entries: list[CodexEntry], kind: EntryKind) -> list[CodexEntry]:
    return [e for e in entries if e.entry_kind == kind]


def test_student_metrics_percentiles_and_domain(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "학생지표.parquet"
    _write_student_metrics(path)

    result = read_student_metrics(
        path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(path.relative_to(data_root)),
    )
    assert isinstance(result, SourceReadResult)
    entries = result.entries

    # Student A: percentile_section, percentile_cohort, z_score, 2 domain rates.
    sec = _by_kind(entries, EntryKind.percentile_section)
    assert [e.value_num for e in sec] == [75.0]
    assert sec[0].layer == "rich"
    assert sec[0].cohort_year == 2026
    assert sec[0].key == "percentile_section"
    assert sec[0].domain is None
    assert sec[0].observed_at is None

    coh = _by_kind(entries, EntryKind.percentile_cohort)
    assert [e.value_num for e in coh] == [70.0]
    z = _by_kind(entries, EntryKind.z_score)
    assert [e.value_num for e in z] == [1.2]

    domain = _by_kind(entries, EntryKind.domain_correct_rate)
    by_dom = {e.domain: e for e in domain}
    assert by_dom.keys() == {"순환", "호흡"}
    assert by_dom["순환"].value_num == 0.9
    assert by_dom["순환"].key == "chapter_correct_rate:순환"

    # Student B absent → no percentile/z entries.
    b_entries = [e for e in entries if e.student_id == _SID_B]
    assert all(
        e.entry_kind
        not in (
            EntryKind.percentile_section,
            EntryKind.percentile_cohort,
            EntryKind.z_score,
        )
        for e in b_entries
    )
    # But identity for B is still captured.
    assert result.identities[_SID_B] == "이영희"
    assert result.identities[_SID_A] == "김철수"

    # SourceRecord shape.
    sr = result.source_record
    assert sr.origin_module == "immersio"
    assert sr.origin_layer == "silver"
    assert sr.source_id == "immersio:학생지표"
    assert sr.source_path == "silver/immersio/2026-1-anatomy/학생지표.parquet"
    assert sr.ingested_at == _INGESTED_AT
    assert all(e.source_id == "immersio:학생지표" for e in entries)


def test_exam_results_item_correct_with_chapter_join(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    res_path = immersio_dir / "exam_result.parquet"
    item_path = immersio_dir / "exam_item.parquet"
    _write_exam_result(res_path)
    _write_exam_item(item_path)

    result = read_exam_results(
        res_path,
        item_path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(res_path.relative_to(data_root)),
    )
    entries = result.entries
    items = _by_kind(entries, EntryKind.item_correct)
    by_ref = {e.item_ref: e for e in items}

    # item 3 ungraded → skipped.
    assert set(by_ref.keys()) == {"1", "2"}
    assert by_ref["1"].value_num == 1.0
    assert by_ref["1"].domain == "순환"
    assert by_ref["1"].key == "item_correct:1"
    assert by_ref["1"].layer == "rich"
    assert by_ref["2"].value_num == 0.0
    assert by_ref["2"].domain is None  # exam_item chapter None

    assert result.source_record.source_id == "immersio:exam_result"
    # exam_result has no name → identity maps to None.
    assert result.identities[_SID_A] is None


def test_factor_scores_axis_z(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    path = needsmap_dir / "factor_scores.parquet"
    _write_factor_scores(path)

    result = read_factor_scores(
        path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(path.relative_to(data_root)),
    )
    entries = result.entries
    axis_entries = _by_kind(entries, EntryKind.axis_score_z)

    # Off-roster student fully skipped.
    assert all(e.student_id == _SID_A for e in axis_entries)
    # feedback_seeking missing → skipped; 7 axes remain.
    domains = {e.domain for e in axis_entries}
    assert "feedback_seeking" not in domains
    assert len(axis_entries) == len(STANDARD_AXIS_KEYS) - 1
    mot = next(e for e in axis_entries if e.domain == "motivation")
    assert mot.key == "axis_z:motivation"
    assert mot.layer == "rich"
    assert mot.value_num == 0.5  # i=1 → 1*0.5

    assert result.source_record.source_id == "needs-map:factor_scores"
    assert result.source_record.origin_module == "needs-map"


def test_free_text_categories(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    path = needsmap_dir / "free_text_categorization.parquet"
    _write_free_text(path)

    result = read_free_text(
        path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(path.relative_to(data_root)),
    )
    entries = _by_kind(result.entries, EntryKind.freetext_category)
    # A:q9 → 2 categories; empty/no_response emit nothing.
    assert len(entries) == 2
    texts = {e.value_text for e in entries}
    assert texts == {"health", "career"}
    health = next(e for e in entries if e.value_text == "health")
    assert health.domain == "q9"
    assert health.key == "freetext:q9:health"
    assert health.value_num is None
    assert health.layer == "rich"


def test_cluster_assignment_labels(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    assign_path = needsmap_dir / "cluster_assignment.parquet"
    names_path = needsmap_dir / "cluster_names.json"
    _write_cluster_assignment(assign_path)
    _write_cluster_names(names_path)

    result = read_cluster_assignment(
        assign_path,
        names_path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(assign_path.relative_to(data_root)),
    )
    entries = _by_kind(result.entries, EntryKind.cluster_label)
    by_sid = {e.student_id: e for e in entries}
    assert by_sid[_SID_A].value_text == "성실형"
    assert by_sid[_SID_B].value_text == "도전형"
    assert by_sid[_SID_A].key == "cluster_label"
    assert by_sid[_SID_A].domain is None
    assert by_sid[_SID_A].layer == "rich"


def test_combined_analysis_derives_all(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "진단×시험결합.parquet"
    _write_combined(path)

    result = read_combined_analysis(
        path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(path.relative_to(data_root)),
    )
    entries = result.entries
    kinds = {e.entry_kind for e in entries}
    assert EntryKind.percentile_section in kinds
    assert EntryKind.z_score in kinds
    assert EntryKind.domain_correct_rate in kinds
    assert EntryKind.axis_score_z in kinds
    assert EntryKind.cluster_label in kinds
    # No item_correct / freetext from combined.
    assert EntryKind.item_correct not in kinds
    assert EntryKind.freetext_category not in kinds

    cl = _by_kind(entries, EntryKind.cluster_label)
    assert cl[0].value_text == "성실형"
    assert result.source_record.source_id == "immersio:진단×시험결합"
    assert result.identities[_SID_A] == "김철수"


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


def _write_all_individual(immersio_dir: Path, needsmap_dir: Path) -> None:
    _write_student_metrics(immersio_dir / "학생지표.parquet")
    _write_exam_result(immersio_dir / "exam_result.parquet")
    _write_exam_item(immersio_dir / "exam_item.parquet")
    _write_factor_scores(needsmap_dir / "factor_scores.parquet")
    _write_free_text(needsmap_dir / "free_text_categorization.parquet")
    _write_cluster_assignment(needsmap_dir / "cluster_assignment.parquet")
    _write_cluster_names(needsmap_dir / "cluster_names.json")


def test_orchestrator_individual_path(tmp_path: Path) -> None:
    data_root, immersio_dir, needsmap_dir = _silver_dirs(tmp_path)
    _write_all_individual(immersio_dir, needsmap_dir)

    results = read_paideia_sources(
        immersio_silver_dir=immersio_dir,
        needsmap_silver_dir=needsmap_dir,
        semester=_SEMESTER,
        data_root=data_root,
        ingested_at=_INGESTED_AT,
    )
    source_ids = {r.source_record.source_id for r in results}
    assert source_ids == {
        "immersio:학생지표",
        "immersio:exam_result",
        "needs-map:factor_scores",
        "needs-map:free_text_categorization",
        "needs-map:cluster_assignment",
    }
    # 진단×시험결합 absent → not read.
    assert "immersio:진단×시험결합" not in source_ids

    # Assert real emitted content, not just provenance presence.
    all_entries = [e for r in results for e in r.entries]
    assert all_entries  # something was emitted
    assert all(e.semester == _SEMESTER for e in all_entries)
    metrics = next(r for r in results if r.source_record.source_id == "immersio:학생지표")
    sec = _by_kind(metrics.entries, EntryKind.percentile_section)
    assert [e.value_num for e in sec] == [75.0]


def test_orchestrator_combined_preference(tmp_path: Path) -> None:
    data_root, immersio_dir, needsmap_dir = _silver_dirs(tmp_path)
    # Present BOTH combined and the individual files it supersedes.
    _write_all_individual(immersio_dir, needsmap_dir)
    _write_combined(immersio_dir / "진단×시험결합.parquet")

    results = read_paideia_sources(
        immersio_silver_dir=immersio_dir,
        needsmap_silver_dir=needsmap_dir,
        semester=_SEMESTER,
        data_root=data_root,
        ingested_at=_INGESTED_AT,
    )
    source_ids = {r.source_record.source_id for r in results}
    # Combined supersedes 학생지표 / factor_scores / cluster_assignment.
    assert "immersio:진단×시험결합" in source_ids
    assert "immersio:학생지표" not in source_ids
    assert "needs-map:factor_scores" not in source_ids
    assert "needs-map:cluster_assignment" not in source_ids
    # Always-read files still present.
    assert "immersio:exam_result" in source_ids
    assert "needs-map:free_text_categorization" in source_ids

    # No duplicate (student_id, key) across the superseded kinds.
    keyed: dict[tuple[str, str], int] = {}
    for r in results:
        for e in r.entries:
            if e.entry_kind in (
                EntryKind.percentile_section,
                EntryKind.percentile_cohort,
                EntryKind.z_score,
                EntryKind.domain_correct_rate,
                EntryKind.axis_score_z,
                EntryKind.cluster_label,
            ):
                k = (e.student_id, e.key)
                keyed[k] = keyed.get(k, 0) + 1
    assert all(v == 1 for v in keyed.values()), keyed


def test_orchestrator_degrade_missing_files(tmp_path: Path) -> None:
    data_root, immersio_dir, needsmap_dir = _silver_dirs(tmp_path)
    # Only student metrics present.
    _write_student_metrics(immersio_dir / "학생지표.parquet")

    results = read_paideia_sources(
        immersio_silver_dir=immersio_dir,
        needsmap_silver_dir=needsmap_dir,
        semester=_SEMESTER,
        data_root=data_root,
        ingested_at=_INGESTED_AT,
    )
    source_ids = {r.source_record.source_id for r in results}
    assert source_ids == {"immersio:학생지표"}


def test_orchestrator_none_dirs(tmp_path: Path) -> None:
    data_root, _, _ = _silver_dirs(tmp_path)
    results = read_paideia_sources(
        immersio_silver_dir=None,
        needsmap_silver_dir=None,
        semester=_SEMESTER,
        data_root=data_root,
        ingested_at=_INGESTED_AT,
    )
    assert results == []


def test_determinism_two_reads(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "학생지표.parquet"
    _write_student_metrics(path)
    sp = str(path.relative_to(data_root))

    r1 = read_student_metrics(path, semester=_SEMESTER, ingested_at=_INGESTED_AT, source_path=sp)
    r2 = read_student_metrics(path, semester=_SEMESTER, ingested_at=_INGESTED_AT, source_path=sp)
    assert r1.entries == r2.entries
    # Sorted by (student_id, entry_kind, key).
    keys = [(e.student_id, e.entry_kind.value, e.key) for e in r1.entries]
    assert keys == sorted(keys)


def test_malformed_parquet_raises_located(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "학생지표.parquet"
    # score_percent out of contract range (>100) → Pydantic ValidationError.
    bad = {
        "student_id": _SID_A,
        "name_kr": "X",
        "section": "A",
        "semester": _SEMESTER,
        "course_slug": _COURSE_SLUG,
        "exam_taken": True,
        "total_score": 80.0,
        "score_percent": 250.0,  # invalid
        "section_percentile": 75.0,
        "cohort_percentile": 70.0,
        "z_score": 1.0,
        "chapter_correct_rates": json.dumps({}, ensure_ascii=False),
        "source_correct_rates": json.dumps({}, ensure_ascii=False),
        "difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
        "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
        "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
    }
    pd.DataFrame([bad]).to_parquet(path)

    with pytest.raises(LocatedInputError) as exc:
        read_student_metrics(
            path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(path.relative_to(data_root)),
        )
    assert "학생지표.parquet" in str(exc.value)


# ---------------------------------------------------------------------------
# I-1 — _coerce_cell stays inside the located-error boundary
# ---------------------------------------------------------------------------


def test_freetext_braced_category_is_not_json_decoded(tmp_path: Path) -> None:
    """A matched category that happens to look like ``{health}`` (not valid JSON)
    must be emitted verbatim, never crash the reader.
    """
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    path = needsmap_dir / "free_text_categorization.parquet"
    rows = [
        {
            "student_id": _SID_A,
            "item_id": "q9",
            "matched_categories": ["{health}"],
            "match_source": "dictionary",
            "raw_length": 10,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)

    result = read_free_text(
        path,
        semester=_SEMESTER,
        ingested_at=_INGESTED_AT,
        source_path=str(path.relative_to(data_root)),
    )
    entries = _by_kind(result.entries, EntryKind.freetext_category)
    assert [e.value_text for e in entries] == ["{health}"]
    assert entries[0].key == "freetext:q9:{health}"


def test_corrupted_dict_cell_raises_located(tmp_path: Path) -> None:
    """A ``chapter_correct_rates`` cell that looks like a dict but is not valid
    JSON must surface as LocatedInputError (file + row), not a bare
    json.JSONDecodeError.
    """
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "학생지표.parquet"
    bad = {
        "student_id": _SID_A,
        "name_kr": "X",
        "section": "A",
        "semester": _SEMESTER,
        "course_slug": _COURSE_SLUG,
        "exam_taken": True,
        "total_score": 80.0,
        "score_percent": 80.0,
        "section_percentile": 75.0,
        "cohort_percentile": 70.0,
        "z_score": 1.0,
        "chapter_correct_rates": "{not valid json}",  # corrupted dict cell (braced, bad JSON)
        "source_correct_rates": json.dumps({}, ensure_ascii=False),
        "difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
        "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
        "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
    }
    pd.DataFrame([bad]).to_parquet(path)

    with pytest.raises(LocatedInputError) as exc:
        read_student_metrics(
            path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(path.relative_to(data_root)),
        )
    msg = str(exc.value)
    assert "학생지표.parquet" in msg


# ---------------------------------------------------------------------------
# I-3 — per-reader malformed-row + sidecar error coverage
# ---------------------------------------------------------------------------


def test_exam_results_malformed_row_raises_located(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    res_path = immersio_dir / "exam_result.parquet"
    item_path = immersio_dir / "exam_item.parquet"
    _write_exam_item(item_path)
    # item_no=0 violates ExamResult ge=1.
    rows = [
        {
            "student_id": _SID_A,
            "semester": _SEMESTER,
            "course_slug": _COURSE_SLUG,
            "item_no": 0,
            "response": "3",
            "is_correct": True,
            "score": 1.0,
        },
    ]
    pd.DataFrame(rows).to_parquet(res_path)

    with pytest.raises(LocatedInputError) as exc:
        read_exam_results(
            res_path,
            item_path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(res_path.relative_to(data_root)),
        )
    assert "exam_result.parquet" in str(exc.value)


def test_factor_scores_malformed_row_raises_located(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    path = needsmap_dir / "factor_scores.parquet"
    # missing=True but score not None violates FactorScoreRow V2.
    row = _factor_row(_SID_A, on_roster=True, with_scores=True)
    row["motivation_missing"] = True  # but motivation score is set → V2 breach
    pd.DataFrame([row]).to_parquet(path)

    with pytest.raises(LocatedInputError) as exc:
        read_factor_scores(
            path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(path.relative_to(data_root)),
        )
    assert "factor_scores.parquet" in str(exc.value)


def test_free_text_malformed_row_raises_located(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    path = needsmap_dir / "free_text_categorization.parquet"
    # match_source='no_response' with non-empty matched_categories → V1 breach.
    rows = [
        {
            "student_id": _SID_A,
            "item_id": "q9",
            "matched_categories": ["health"],
            "match_source": "no_response",
            "raw_length": 5,
        },
    ]
    pd.DataFrame(rows).to_parquet(path)

    with pytest.raises(LocatedInputError) as exc:
        read_free_text(
            path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(path.relative_to(data_root)),
        )
    assert "free_text_categorization.parquet" in str(exc.value)


def test_cluster_assignment_malformed_row_raises_located(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    assign_path = needsmap_dir / "cluster_assignment.parquet"
    names_path = needsmap_dir / "cluster_names.json"
    _write_cluster_names(names_path)
    # cluster_id=-1 violates ClusterAssignmentRow ge=0.
    rows = [{"student_id": _SID_A, "cluster_id": -1, "distance_to_centroid": 0.3}]
    pd.DataFrame(rows).to_parquet(assign_path)

    with pytest.raises(LocatedInputError) as exc:
        read_cluster_assignment(
            assign_path,
            names_path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(assign_path.relative_to(data_root)),
        )
    assert "cluster_assignment.parquet" in str(exc.value)


def test_cluster_id_absent_from_names_raises_located(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    assign_path = needsmap_dir / "cluster_assignment.parquet"
    names_path = needsmap_dir / "cluster_names.json"
    # names only cover cluster 0; assignment references cluster 5.
    names_path.write_text(json.dumps({"0": "성실형"}, ensure_ascii=False), encoding="utf-8")
    rows = [{"student_id": _SID_A, "cluster_id": 5, "distance_to_centroid": 0.3}]
    pd.DataFrame(rows).to_parquet(assign_path)

    with pytest.raises(LocatedInputError) as exc:
        read_cluster_assignment(
            assign_path,
            names_path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(assign_path.relative_to(data_root)),
        )
    msg = str(exc.value)
    assert "cluster_assignment.parquet" in msg
    assert "5" in msg


def test_cluster_names_non_dict_raises_located(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    assign_path = needsmap_dir / "cluster_assignment.parquet"
    names_path = needsmap_dir / "cluster_names.json"
    _write_cluster_assignment(assign_path)
    names_path.write_text(json.dumps(["성실형", "도전형"]), encoding="utf-8")  # array, not object

    with pytest.raises(LocatedInputError) as exc:
        read_cluster_assignment(
            assign_path,
            names_path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(assign_path.relative_to(data_root)),
        )
    assert "cluster_names.json" in str(exc.value)


def test_cluster_names_non_int_key_raises_located(tmp_path: Path) -> None:
    data_root, _, needsmap_dir = _silver_dirs(tmp_path)
    assign_path = needsmap_dir / "cluster_assignment.parquet"
    names_path = needsmap_dir / "cluster_names.json"
    _write_cluster_assignment(assign_path)
    names_path.write_text(json.dumps({"abc": "성실형"}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(LocatedInputError) as exc:
        read_cluster_assignment(
            assign_path,
            names_path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(assign_path.relative_to(data_root)),
        )
    assert "cluster_names.json" in str(exc.value)


def test_combined_malformed_row_raises_located(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "진단×시험결합.parquet"
    row = _combined_row(_SID_A, exam_taken=True, with_axes=True)
    row["진단응답"] = False  # contradicts axes present → V5 breach
    pd.DataFrame([row]).to_parquet(path)

    with pytest.raises(LocatedInputError) as exc:
        read_combined_analysis(
            path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(path.relative_to(data_root)),
        )
    assert "진단×시험결합.parquet" in str(exc.value)


def test_non_parquet_file_raises_located(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    path = immersio_dir / "학생지표.parquet"
    path.write_text("this is not a parquet file", encoding="utf-8")

    with pytest.raises(LocatedInputError) as exc:
        read_student_metrics(
            path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(path.relative_to(data_root)),
        )
    assert "학생지표.parquet" in str(exc.value)


# ---------------------------------------------------------------------------
# I-4 — exam_result must not span multiple course_slug values (key collision)
# ---------------------------------------------------------------------------


def test_exam_results_mixed_course_slug_raises_located(tmp_path: Path) -> None:
    data_root, immersio_dir, _ = _silver_dirs(tmp_path)
    res_path = immersio_dir / "exam_result.parquet"
    item_path = immersio_dir / "exam_item.parquet"
    _write_exam_item(item_path)
    # Two rows sharing item_no=1 but distinct course_slug → key collision risk.
    rows = [
        {
            "student_id": _SID_A,
            "semester": _SEMESTER,
            "course_slug": "anatomy",
            "item_no": 1,
            "response": "3",
            "is_correct": True,
            "score": 1.0,
        },
        {
            "student_id": _SID_A,
            "semester": _SEMESTER,
            "course_slug": "physiology",
            "item_no": 1,
            "response": "2",
            "is_correct": False,
            "score": 0.0,
        },
    ]
    pd.DataFrame(rows).to_parquet(res_path)

    with pytest.raises(LocatedInputError) as exc:
        read_exam_results(
            res_path,
            item_path,
            semester=_SEMESTER,
            ingested_at=_INGESTED_AT,
            source_path=str(res_path.relative_to(data_root)),
        )
    msg = str(exc.value)
    assert "exam_result.parquet" in msg
    assert "course_slug" in msg
