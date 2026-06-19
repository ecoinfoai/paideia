"""T045 RED — Unit tests for metric-codex CLI 'query' and 'dry-run' handlers.

Tests (written first per TDD mandate):
- query: both-layers student → exit 0, output cites evidence.
- query: minimal-only student + rich question-id → prints "근거 없음".
- query: unknown --student → exit 2.
- query: --reveal shows name only when set.
- query: --text freeform search works.
- query: missing --student (required) → argparse exit 2.
- dry-run: writes staging files, exits 0.
- dry-run: no NotImplementedError any more (handler is wired).
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import openpyxl
import pandas as pd
from metric_codex.cli.main import app

# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEM}-{_COURSE}"
_SID_BOTH = "2026000001"  # has minimal + rich
_SID_MIN = "2026000002"   # minimal only
_NAME_BOTH = "김철수"
_NAME_MIN = "이영희"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_school_excel(path: Path, rows: list[tuple]) -> None:
    """Write a minimal school grade/attendance workbook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점", "환산점수", "출석"])
    for row in rows:
        ws.append(list(row))
    wb.save(path)


def _make_school_map(path: Path) -> None:
    text = (
        f"semester: {_SEM}\n"
        f"course_slug: {_COURSE}\n"
        "sheet: 0\n"
        "header_row: 1\n"
        "columns:\n"
        "  student_id: 학번\n"
        "  name_kr: 이름\n"
        "  score_total: 총점\n"
        "  score_percent: 환산점수\n"
        "  attendance: 출석\n"
    )
    path.write_text(text, encoding="utf-8")


def _make_question_set_yaml(path: Path) -> None:
    """Write a question_set.yaml with a minimal + rich question."""
    text = textwrap.dedent("""\
        questions:
          - id: q_total
            text: "총점을 알려주세요."
            entry_kinds:
              - score_total
            domain: null
          - id: q_domain
            text: "도메인별 정답률을 알려주세요."
            entry_kinds:
              - domain_correct_rate
            domain: null
    """)
    path.write_text(text, encoding="utf-8")


def _make_immersio_silver(immersio_dir: Path) -> None:
    """Write immersio 학생지표.parquet for _SID_BOTH only."""
    rows = [
        {
            "student_id": _SID_BOTH,
            "name_kr": _NAME_BOTH,
            "section": "A",
            "semester": _SEM,
            "course_slug": _COURSE,
            "exam_taken": True,
            "total_score": 80.0,
            "score_percent": 80.0,
            "section_percentile": 75.0,
            "cohort_percentile": 70.0,
            "z_score": 1.2,
            "chapter_correct_rates": json.dumps({"순환": 0.9}, ensure_ascii=False, sort_keys=True),
            "source_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "difficulty_correct_rates": json.dumps({}, ensure_ascii=False, sort_keys=True),
            "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
            "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
            "interest_chapters_correct_rate": None,
            "aversion_chapters_correct_rate": None,
        }
    ]
    pd.DataFrame(rows).to_parquet(immersio_dir / "학생지표.parquet")


def _build_ingested_data_root(tmp_path: Path) -> Path:
    """Build a full data_root with ingested Silver store and pseudonym map.

    Runs ``metric-codex ingest`` via app() to produce real Silver fixtures.
    """
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    immersio = data_root / "silver" / "immersio" / _KEY
    bronze.mkdir(parents=True)
    immersio.mkdir(parents=True)

    _make_school_excel(
        bronze / "성적출석.xlsx",
        rows=[
            (int(_SID_BOTH), _NAME_BOTH, 85, 90.5, 15),
            (int(_SID_MIN), _NAME_MIN, 70, 75.0, 12),
        ],
    )
    _make_school_map(bronze / "성적출석_map.yaml")
    _make_immersio_silver(immersio)

    rc = app([
        "ingest",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--now", "2026-06-01T00:00:00Z",
    ])
    assert rc == 0, "ingest must succeed to set up query tests"
    return data_root


def _qs_path(data_root: Path) -> Path:
    """Write and return a question_set.yaml in Bronze."""
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    qs_path = bronze / "question_set.yaml"
    _make_question_set_yaml(qs_path)
    return qs_path


# ---------------------------------------------------------------------------
# TestQueryBothLayersStudent
# ---------------------------------------------------------------------------


class TestQueryBothLayersStudent:
    """query with both-layer student → exit 0, output contains evidence."""

    def test_exit_zero_with_question_id(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--question-set", str(qs_path),
        ])
        assert rc == 0

    def test_output_contains_citation(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--question-set", str(qs_path),
        ])
        captured = capsys.readouterr()
        # Should contain the citation key or source
        assert "score_total" in captured.out or "school_excel" in captured.out

    def test_query_by_pseudonym(self, tmp_path, capsys):
        """--student S001 (pseudonym) should resolve correctly."""
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        # S001 is the smaller student_id (SID_BOTH=2026000001 < SID_MIN=2026000002)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", "S001",
            "--question-id", "q_total",
            "--question-set", str(qs_path),
        ])
        assert rc == 0

    def test_freeform_text_query(self, tmp_path, capsys):
        """--text freeform search returns exit 0 and output."""
        data_root = _build_ingested_data_root(tmp_path)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--text", "score_total",
        ])
        assert rc == 0


# ---------------------------------------------------------------------------
# TestQueryMinimalOnlyStudent
# ---------------------------------------------------------------------------


class TestQueryMinimalOnlyStudent:
    """Minimal-only student + rich question → '근거 없음' in output."""

    def test_prints_no_evidence_sentinel(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_MIN,
            "--question-id", "q_domain",
            "--question-set", str(qs_path),
        ])
        captured = capsys.readouterr()
        assert "근거 없음" in captured.out

    def test_exit_zero_even_for_no_evidence(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_MIN,
            "--question-id", "q_domain",
            "--question-set", str(qs_path),
        ])
        assert rc == 0


# ---------------------------------------------------------------------------
# TestQueryUnknownStudent
# ---------------------------------------------------------------------------


class TestQueryUnknownStudent:
    """Unknown --student value → exit 2."""

    def test_unknown_student_id_exits_two(self, tmp_path):
        data_root = _build_ingested_data_root(tmp_path)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", "9999999999",  # not in store
            "--text", "score",
        ])
        assert rc == 2

    def test_unknown_pseudonym_exits_two(self, tmp_path):
        data_root = _build_ingested_data_root(tmp_path)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", "S999",  # not in map
            "--text", "score",
        ])
        assert rc == 2


# ---------------------------------------------------------------------------
# TestQueryReveal
# ---------------------------------------------------------------------------


class TestQueryReveal:
    """--reveal shows name; without it, name is absent from output."""

    def test_reveal_shows_name(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--question-set", str(qs_path),
            "--reveal",
        ])
        captured = capsys.readouterr()
        assert _NAME_BOTH in captured.out

    def test_no_reveal_hides_name(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--question-set", str(qs_path),
        ])
        captured = capsys.readouterr()
        assert _NAME_BOTH not in captured.out

    def test_reveal_also_shows_student_id(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--question-set", str(qs_path),
            "--reveal",
        ])
        captured = capsys.readouterr()
        assert _SID_BOTH in captured.out


# ---------------------------------------------------------------------------
# TestQueryArgparseBoundaries
# ---------------------------------------------------------------------------


class TestQueryArgparseBoundaries:
    """Argparse-level validation for the query subcommand."""

    def test_missing_student_flag_exits_two(self, tmp_path):
        """--student is required; omitting it should exit 2."""
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(tmp_path),
            "--text", "score",
            # --student missing
        ])
        assert rc == 2

    def test_question_id_and_text_mutually_exclusive(self, tmp_path):
        """--question-id and --text are mutually exclusive."""
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--text", "score",
            "--question-set", str(qs_path),
        ])
        # Should exit 2 (argparse mutual exclusion)
        assert rc == 2


# ---------------------------------------------------------------------------
# TestQueryJsonOutput
# ---------------------------------------------------------------------------


class TestQueryJsonOutput:
    """--json <path> writes the QueryAnswer JSON."""

    def test_json_output_written(self, tmp_path, capsys):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        json_out = tmp_path / "answer.json"
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--student", _SID_BOTH,
            "--question-id", "q_total",
            "--question-set", str(qs_path),
            "--json", str(json_out),
        ])
        assert rc == 0
        assert json_out.is_file()
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert "student_pseudonym" in data


# ---------------------------------------------------------------------------
# TestDryRunHandler
# ---------------------------------------------------------------------------


class TestDryRunHandler:
    """dry-run: writes staging bundles, exits 0, no PII in staging files."""

    def test_dry_run_exits_zero(self, tmp_path):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        rc = app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--question-set", str(qs_path),
        ])
        assert rc == 0

    def test_dry_run_not_not_implemented(self, tmp_path):
        """dry-run must no longer be a stub (not exit 3)."""
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        rc = app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--question-set", str(qs_path),
        ])
        assert rc != 3

    def test_dry_run_creates_staging_files(self, tmp_path):
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--question-set", str(qs_path),
        ])
        own_silver = data_root / "silver" / "metric-codex" / _KEY
        staging_dir = own_silver / "staging"
        assert staging_dir.is_dir()
        json_files = list(staging_dir.glob("*.json"))
        assert len(json_files) > 0

    def test_dry_run_staging_count_matches_students(self, tmp_path):
        """One staging file per student in the store."""
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--question-set", str(qs_path),
        ])
        own_silver = data_root / "silver" / "metric-codex" / _KEY
        json_files = list((own_silver / "staging").glob("*.json"))
        # 2 students in the scenario
        assert len(json_files) == 2

    def test_dry_run_no_pii_in_staging_files(self, tmp_path):
        """PRIV-01/SC-004: staging files must contain no 10-digit ids or names."""
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--question-set", str(qs_path),
        ])
        own_silver = data_root / "silver" / "metric-codex" / _KEY
        sid_pattern = re.compile(r"\b\d{10}\b")
        for f in (own_silver / "staging").glob("*.json"):
            text = f.read_text(encoding="utf-8")
            m = sid_pattern.search(text)
            assert m is None, f"10-digit student_id in {f.name}: {m.group()!r}"
            assert _NAME_BOTH not in text, f"Name found in {f.name}"
            assert _NAME_MIN not in text, f"Name found in {f.name}"

    def test_dry_run_prints_count_and_paths(self, tmp_path, capsys):
        """dry-run prints the staging file count and paths."""
        data_root = _build_ingested_data_root(tmp_path)
        qs_path = _qs_path(data_root)
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--question-set", str(qs_path),
        ])
        captured = capsys.readouterr()
        # Some indication of count or path should appear
        assert "staging" in captured.out or "S001" in captured.out or "2" in captured.out
