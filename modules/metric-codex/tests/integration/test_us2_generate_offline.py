"""T036 RED — US2 dry-run integration test: pseudonymized staging (PRIV-01/SC-004).

Exercises the 'dry-run' CLI path end-to-end:
  ingest → (Silver codex_entry.parquet + pseudonym_map.parquet)
  dry-run → silver/staging/{S001,S002,...}.json

SC-004: every staging file must contain 0 PII
  - no 10-digit student ID
  - no Korean name from the pseudonym map
  - no email-shaped string

The generate --backend none path (U2b-2) is NOT tested here.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import openpyxl
import pytest
from metric_codex.cli.main import app

# ---------------------------------------------------------------------------
# Scenario constants
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEM}-{_COURSE}"

_SID_A = "2026000001"
_SID_B = "2026000002"
_NAME_A = "김철수"
_NAME_B = "이영희"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_school_excel(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점", "환산점수", "출석"])
    ws.append([int(_SID_A), _NAME_A, 85, 90.5, 15])
    ws.append([int(_SID_B), _NAME_B, 70, 75.0, 12])
    wb.save(path)


def _make_school_map(path: Path) -> None:
    path.write_text(
        f"semester: {_SEM}\n"
        f"course_slug: {_COURSE}\n"
        "sheet: 0\n"
        "header_row: 1\n"
        "columns:\n"
        "  student_id: 학번\n"
        "  name_kr: 이름\n"
        "  score_total: 총점\n"
        "  score_percent: 환산점수\n"
        "  attendance: 출석\n",
        encoding="utf-8",
    )


def _make_question_set(path: Path) -> None:
    path.write_text(
        textwrap.dedent("""\
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
        """),
        encoding="utf-8",
    )


@pytest.fixture()
def ingested_data_root(tmp_path: Path) -> Path:
    """Return a data_root after a successful ingest run."""
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    bronze.mkdir(parents=True)

    _make_school_excel(bronze / "성적출석.xlsx")
    _make_school_map(bronze / "성적출석_map.yaml")

    rc = app([
        "ingest",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--now", "2026-06-01T00:00:00Z",
    ])
    assert rc == 0
    return data_root


@pytest.fixture()
def question_set_path(ingested_data_root: Path) -> Path:
    """Write a question_set.yaml and return its path."""
    bronze = ingested_data_root / "bronze" / "metric-codex" / _KEY
    qs_path = bronze / "question_set.yaml"
    _make_question_set(qs_path)
    return qs_path


# ---------------------------------------------------------------------------
# SC-004: dry-run end-to-end PII boundary
# ---------------------------------------------------------------------------


class TestDryRunOfflineNoPii:
    """PRIV-01/SC-004: dry-run writes staging files with zero PII."""

    def test_dry_run_exits_zero(self, ingested_data_root, question_set_path):
        rc = app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        assert rc == 0

    def test_staging_dir_created(self, ingested_data_root, question_set_path):
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        assert staging.is_dir()

    def test_one_staging_file_per_student(self, ingested_data_root, question_set_path):
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        json_files = sorted(staging.glob("*.json"))
        # 2 students ingested → 2 staging files
        assert len(json_files) == 2

    def test_staging_files_named_by_pseudonym(self, ingested_data_root, question_set_path):
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        names = {f.name for f in staging.glob("*.json")}
        # S001 and S002 (SID_A < SID_B)
        assert "S001.json" in names
        assert "S002.json" in names

    def test_no_10digit_student_id_in_any_staging_file(
        self, ingested_data_root, question_set_path
    ):
        """PRIV-01: 10-digit student IDs must not appear in any staging JSON."""
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        sid_re = re.compile(r"\b\d{10}\b")
        for f in staging.glob("*.json"):
            text = f.read_text(encoding="utf-8")
            m = sid_re.search(text)
            assert m is None, (
                f"PRIV-01 violated: 10-digit student_id {m.group()!r} found in {f.name}"
            )

    def test_no_korean_name_in_any_staging_file(
        self, ingested_data_root, question_set_path
    ):
        """PRIV-01: Korean student names must not appear in any staging JSON."""
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        for f in staging.glob("*.json"):
            text = f.read_text(encoding="utf-8")
            assert _NAME_A not in text, f"Name {_NAME_A!r} in {f.name}"
            assert _NAME_B not in text, f"Name {_NAME_B!r} in {f.name}"

    def test_staging_json_is_valid_and_has_pseudonym(
        self, ingested_data_root, question_set_path
    ):
        """Each staging JSON parses correctly and contains a pseudonym field."""
        app([
            "dry-run",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(ingested_data_root),
            "--question-set", str(question_set_path),
        ])
        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        for f in staging.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            assert "pseudonym" in data
            assert re.fullmatch(r"S\d{3,}", data["pseudonym"]), (
                f"pseudonym {data['pseudonym']!r} does not match ^S\\d{{3,}}$"
            )

    def test_staging_deterministic_second_run(
        self, ingested_data_root, question_set_path
    ):
        """Two consecutive dry-runs produce byte-identical staging files."""
        def _run():
            rc = app([
                "dry-run",
                "--semester", _SEM,
                "--course", _COURSE,
                "--data-root", str(ingested_data_root),
                "--question-set", str(question_set_path),
            ])
            assert rc == 0

        staging = (
            ingested_data_root / "silver" / "metric-codex" / _KEY / "staging"
        )
        _run()
        contents_1 = {f.name: f.read_bytes() for f in staging.glob("*.json")}
        _run()
        contents_2 = {f.name: f.read_bytes() for f in staging.glob("*.json")}
        assert contents_1 == contents_2, "dry-run is not deterministic"


# ---------------------------------------------------------------------------
# TODO(U2b-2): generate --backend none tests go here.
# When implement: test that Gold md/yaml are produced without LLM.
# ---------------------------------------------------------------------------

# TODO(U2b-2): add TestGenerateBackendNone class here when implementing
# the generate handler.  This file currently covers dry-run only.
