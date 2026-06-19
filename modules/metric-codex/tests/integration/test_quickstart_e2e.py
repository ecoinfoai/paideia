"""T059 RED — End-to-end quickstart validation: Scenarios A–E, SC-001..SC-009.

Canonical 3-student synthetic fixture (one invocation per SC group):

  Student FULL        (2026000001): school Excel + immersio Silver + needs-map Silver
  Student MINIMAL-ONLY (2026000002): school Excel ONLY (no rich Silver)
  Student UNASSIGNED   (2026000003): school Excel + NOT in advisor roster

Bronze files:
  성적출석.xlsx / 성적출석_map.yaml (all 3 students)
  지도교수배정.yaml             (FULL → ADV_A, MINIMAL → ADV_B; UNASSIGNED absent)
  question_set.yaml             (one minimal question + one rich question)

Rich Silver (immersio + needs-map) covers FULL only, so MINIMAL-ONLY degrades
gracefully and yields no_evidence=True for the rich-layer question.

Every SC must be asserted directly; if a real defect causes one to fail it is
reported as a bug, NOT papered over.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from metric_codex.cli.main import app

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEM}-{_COURSE}"

_SID_FULL = "2026000001"    # present in school Excel + immersio + needs-map
_NAME_FULL = "김철수"
_SID_MINIMAL = "2026000002"  # present in school Excel ONLY
_NAME_MINIMAL = "이영희"
_SID_UNAS = "2026000003"     # in school Excel, NOT in roster
_NAME_UNAS = "박지수"

_ADV_A = "ADV_A"
_ADV_B = "ADV_B"

# Fixed timestamp for deterministic runs.
_NOW_INGEST = "2026-06-19T00:00:00Z"
_NOW_GEN = "2026-06-19T01:00:00Z"
_NOW_DIST = "2026-06-19T02:00:00Z"

# Question IDs used in assertions.
_QID_MINIMAL = "q_total"          # entry_kind: score_total  (minimal layer — all students)
_QID_RICH = "q_domain"            # entry_kind: domain_correct_rate (rich only — FULL student)


# ---------------------------------------------------------------------------
# Bronze fixture builders
# ---------------------------------------------------------------------------


def _make_school_excel(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점", "환산점수", "출석"])
    ws.append([int(_SID_FULL),    _NAME_FULL,    85, 90.5, 15])
    ws.append([int(_SID_MINIMAL), _NAME_MINIMAL, 70, 75.0, 12])
    ws.append([int(_SID_UNAS),    _NAME_UNAS,    60, 65.0, 10])
    wb.save(path)


def _make_school_map(path: Path) -> None:
    path.write_text(
        textwrap.dedent(f"""\
            semester: {_SEM}
            course_slug: {_COURSE}
            sheet: 0
            header_row: 1
            columns:
              student_id: 학번
              name_kr: 이름
              score_total: 총점
              score_percent: 환산점수
              attendance: 출석
        """),
        encoding="utf-8",
    )


def _make_question_set(path: Path) -> None:
    """Write question_set with one minimal-layer and one rich-layer question."""
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


def _make_roster(path: Path) -> None:
    """Roster: FULL → ADV_A, MINIMAL → ADV_B; UNASSIGNED absent (no entry)."""
    path.write_text(
        textwrap.dedent(f"""\
            assignments:
              - student_id: "{_SID_FULL}"
                advisor_id: "{_ADV_A}"
                advisor_name: "김교수"
              - student_id: "{_SID_MINIMAL}"
                advisor_id: "{_ADV_B}"
                advisor_name: "이교수"
        """),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Rich Silver builders (immersio + needs-map) — FULL student only
# ---------------------------------------------------------------------------


def _make_immersio_silver(path: Path) -> None:
    """Write immersio 학생지표.parquet for FULL student with rich percentiles."""
    rows = [
        {
            "student_id": _SID_FULL,
            "name_kr": _NAME_FULL,
            "section": "A",
            "semester": _SEM,
            "course_slug": _COURSE,
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
        }
    ]
    pd.DataFrame(rows).to_parquet(path)


def _make_needsmap_silver(path: Path) -> None:
    """Write needs-map free_text_categorization.parquet for FULL student."""
    rows = [
        {
            "student_id": _SID_FULL,
            "item_id": "q9",
            "matched_categories": ["health", "career"],
            "match_source": "dictionary",
            "raw_length": 42,
        }
    ]
    pd.DataFrame(rows).to_parquet(path)


# ---------------------------------------------------------------------------
# Shared path helpers
# ---------------------------------------------------------------------------


def _silver(data_root: Path) -> Path:
    return data_root / "silver" / "metric-codex" / _KEY


def _gold(data_root: Path) -> Path:
    return data_root / "gold" / "metric-codex" / _KEY


# ---------------------------------------------------------------------------
# Shared fixture: full 3-student data_root with Bronze + upstream Silver
# ---------------------------------------------------------------------------


@pytest.fixture()
def full_data_root(tmp_path: Path) -> Path:
    """3-student data_root wired with Bronze inputs + rich upstream Silver.

    Layout:
      bronze/metric-codex/{key}/성적출석.xlsx       (3 students)
      bronze/metric-codex/{key}/성적출석_map.yaml
      bronze/metric-codex/{key}/question_set.yaml   (minimal + rich questions)
      bronze/metric-codex/{key}/지도교수배정.yaml   (FULL+MINIMAL assigned; UNAS absent)
      silver/immersio/{key}/학생지표.parquet         (FULL only)
      silver/needs-map/{key}/free_text_categorization.parquet (FULL only)
    """
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    immersio = data_root / "silver" / "immersio" / _KEY
    needsmap = data_root / "silver" / "needs-map" / _KEY
    for d in (bronze, immersio, needsmap):
        d.mkdir(parents=True)

    _make_school_excel(bronze / "성적출석.xlsx")
    _make_school_map(bronze / "성적출석_map.yaml")
    _make_question_set(bronze / "question_set.yaml")
    _make_roster(bronze / "지도교수배정.yaml")
    _make_immersio_silver(immersio / "학생지표.parquet")
    _make_needsmap_silver(needsmap / "free_text_categorization.parquet")

    return data_root


# ---------------------------------------------------------------------------
# Helper: run CLI stages
# ---------------------------------------------------------------------------


def _ingest(data_root: Path) -> int:
    return app([
        "ingest",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--now", _NOW_INGEST,
    ])


def _dry_run(data_root: Path) -> int:
    qs = data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
    return app([
        "dry-run",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--question-set", str(qs),
    ])


def _generate(data_root: Path) -> int:
    qs = data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
    return app([
        "generate",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--question-set", str(qs),
        "--backend", "none",
        "--now", _NOW_GEN,
    ])


def _distribute(data_root: Path) -> int:
    roster = data_root / "bronze" / "metric-codex" / _KEY / "지도교수배정.yaml"
    return app([
        "distribute",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--roster", str(roster),
        "--now", _NOW_DIST,
    ])


def _verify(data_root: Path) -> int:
    qs = data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
    roster = data_root / "bronze" / "metric-codex" / _KEY / "지도교수배정.yaml"
    return app([
        "verify",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--question-set", str(qs),
        "--roster", str(roster),
    ])


# ---------------------------------------------------------------------------
# SC-001 / Scenario A: FULL student has both minimal value_num + rich entries
# ---------------------------------------------------------------------------


class TestSC001MultiLayerCoexist:
    """SC-001: FULL student's codex_entry.parquet combines ≥2 source layers."""

    def test_ingest_exits_zero(self, full_data_root: Path) -> None:
        rc = _ingest(full_data_root)
        assert rc == 0, f"ingest failed rc={rc}"

    def test_codex_parquet_exists(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        assert (_silver(full_data_root) / "codex_entry.parquet").is_file()

    def test_full_student_has_minimal_value_num(self, full_data_root: Path) -> None:
        """FULL student carries minimal value_num (score_total) from school Excel."""
        _ingest(full_data_root)
        df = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        full_rows = df[df["student_id"] == _SID_FULL]
        minimal = full_rows[full_rows["layer"] == "minimal"]
        assert not minimal.empty, "FULL student must have minimal-layer rows"
        assert minimal["value_num"].notna().any(), "minimal rows must have value_num"

    def test_full_student_has_rich_value_text(self, full_data_root: Path) -> None:
        """FULL student carries rich value_text (freetext_category) from needs-map."""
        _ingest(full_data_root)
        df = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        full_rows = df[df["student_id"] == _SID_FULL]
        rich_text = full_rows[
            (full_rows["layer"] == "rich") & (full_rows["value_text"].notna())
        ]
        assert not rich_text.empty, (
            "SC-001: FULL student must have rich value_text entries (freetext_category)"
        )

    def test_both_layers_under_one_student_id(self, full_data_root: Path) -> None:
        """SC-001: minimal value_num AND rich value_text coexist under one student_id."""
        _ingest(full_data_root)
        df = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        full_rows = df[df["student_id"] == _SID_FULL]
        layers = set(full_rows["layer"].unique())
        assert "minimal" in layers and "rich" in layers, (
            f"SC-001: expected both layers for FULL student; got {layers}"
        )

    def test_three_students_in_store(self, full_data_root: Path) -> None:
        """All 3 students appear in the store after ingest."""
        _ingest(full_data_root)
        df = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        sids = set(df["student_id"].unique())
        assert {_SID_FULL, _SID_MINIMAL, _SID_UNAS}.issubset(sids), (
            f"expected all 3 students; got {sids}"
        )


# ---------------------------------------------------------------------------
# SC-002 / Scenario B: query on FULL student — citations resolve to real entries
# ---------------------------------------------------------------------------


class TestSC002CitedAnswer:
    """SC-002: query answer's every EvidenceCitation matches a real codex_entry row."""

    def test_query_full_student_rich_exits_zero(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        qs = full_data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(full_data_root),
            "--student", _SID_FULL,
            "--question-id", _QID_RICH,
            "--question-set", str(qs),
        ])
        assert rc == 0, "SC-002: query for FULL student (rich question) must exit 0"

    def test_query_full_json_citations_resolve(
        self, full_data_root: Path, tmp_path: Path
    ) -> None:
        """Every EvidenceCitation key/source_id in the JSON output traces to a real row."""
        _ingest(full_data_root)
        qs = full_data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
        json_out = tmp_path / "answer.json"
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(full_data_root),
            "--student", _SID_FULL,
            "--question-id", _QID_RICH,
            "--question-set", str(qs),
            "--json", str(json_out),
        ])
        assert rc == 0
        assert json_out.is_file(), "JSON output must be written"

        answer = json.loads(json_out.read_text(encoding="utf-8"))
        assert answer.get("no_evidence") is False, (
            "SC-002: FULL student rich question must not be no_evidence"
        )
        citations = answer.get("citations", [])
        assert len(citations) > 0, "SC-002: expected ≥1 citation for FULL student"

        # Every citation must resolve to a real codex_entry row.
        df = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        full_rows = df[df["student_id"] == _SID_FULL]
        entry_index = {
            (row["key"], row["source_id"])
            for _, row in full_rows.iterrows()
        }
        for c in citations:
            key = (c["key"], c["source_id"])
            assert key in entry_index, (
                f"SC-002: citation {key!r} does not resolve to any codex_entry row"
            )


# ---------------------------------------------------------------------------
# SC-005 / Scenario B degrade: MINIMAL-ONLY student + rich question → no_evidence
# ---------------------------------------------------------------------------


class TestSC005NoEvidenceDegrade:
    """SC-005: MINIMAL-ONLY student asked a RICH question → no_evidence, no fabrication."""

    def test_query_minimal_only_rich_no_evidence(
        self, full_data_root: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _ingest(full_data_root)
        qs = full_data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
        rc = app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(full_data_root),
            "--student", _SID_MINIMAL,
            "--question-id", _QID_RICH,
            "--question-set", str(qs),
        ])
        assert rc == 0, "SC-005: query should exit 0 even with no_evidence"
        captured = capsys.readouterr()
        assert "근거 없음" in captured.out, (
            "SC-005: output must contain '근거 없음' for minimal-only student + rich question"
        )

    def test_query_minimal_json_no_evidence_true(
        self, full_data_root: Path, tmp_path: Path
    ) -> None:
        """SC-005: JSON output has no_evidence=True and available_layers==['minimal']."""
        _ingest(full_data_root)
        qs = full_data_root / "bronze" / "metric-codex" / _KEY / "question_set.yaml"
        json_out = tmp_path / "minimal_answer.json"
        app([
            "query",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(full_data_root),
            "--student", _SID_MINIMAL,
            "--question-id", _QID_RICH,
            "--question-set", str(qs),
            "--json", str(json_out),
        ])
        answer = json.loads(json_out.read_text(encoding="utf-8"))
        assert answer.get("no_evidence") is True, (
            "SC-005: no_evidence must be True for minimal-only student + rich question"
        )
        assert answer.get("citations", []) == [], (
            "SC-005: citations must be empty (no fabricated value)"
        )
        assert answer.get("available_layers") == ["minimal"], (
            f"SC-005: available_layers must be ['minimal']; got {answer.get('available_layers')}"
        )


# ---------------------------------------------------------------------------
# SC-004 / Scenario C: dry-run staging files contain 0 PII
# ---------------------------------------------------------------------------


class TestSC004StagingNoPii:
    """SC-004: every staging/*.json after dry-run contains 0 PII."""

    def test_dry_run_exits_zero(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        rc = _dry_run(full_data_root)
        assert rc == 0, "SC-004: dry-run must exit 0"

    def test_staging_dir_created(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        _dry_run(full_data_root)
        assert (_silver(full_data_root) / "staging").is_dir()

    def test_staging_count_equals_student_count(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        _dry_run(full_data_root)
        staging = _silver(full_data_root) / "staging"
        jsons = list(staging.glob("*.json"))
        assert len(jsons) == 3, (
            f"expected 3 staging files (one per student); got {len(jsons)}"
        )

    def test_no_10digit_id_in_staging(self, full_data_root: Path) -> None:
        """PRIV-01/SC-004: no 10-digit student_id appears in any staging file."""
        _ingest(full_data_root)
        _dry_run(full_data_root)
        staging = _silver(full_data_root) / "staging"
        sid_re = re.compile(r"\b\d{10}\b")
        for f in staging.glob("*.json"):
            text = f.read_text(encoding="utf-8")
            m = sid_re.search(text)
            assert m is None, (
                f"SC-004 PRIV-01: 10-digit id {m.group()!r} found in {f.name}"
            )

    def test_no_korean_name_in_staging(self, full_data_root: Path) -> None:
        """PRIV-01/SC-004: no Korean student name appears in any staging file."""
        _ingest(full_data_root)
        _dry_run(full_data_root)
        staging = _silver(full_data_root) / "staging"
        for f in staging.glob("*.json"):
            text = f.read_text(encoding="utf-8")
            for name in (_NAME_FULL, _NAME_MINIMAL, _NAME_UNAS):
                assert name not in text, (
                    f"SC-004 PRIV-01: name {name!r} found in {f.name}"
                )

    def test_no_email_shape_in_staging(self, full_data_root: Path) -> None:
        """PRIV-01/SC-004: no email-shaped string in any staging file."""
        _ingest(full_data_root)
        _dry_run(full_data_root)
        staging = _silver(full_data_root) / "staging"
        email_re = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
        for f in staging.glob("*.json"):
            text = f.read_text(encoding="utf-8")
            m = email_re.search(text)
            assert m is None, (
                f"SC-004 PRIV-01: email {m.group()!r} found in {f.name}"
            )


# ---------------------------------------------------------------------------
# SC-009 / DET-02 (Scenario C offline): generate --backend none → Gold md for all
# ---------------------------------------------------------------------------


class TestSC009GenerateOffline:
    """SC-009/DET-02: generate --backend none writes Gold md for every student, exit 0."""

    def test_generate_exits_zero(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        rc = _generate(full_data_root)
        assert rc == 0, "SC-009: generate --backend none must exit 0"

    def test_gold_student_dir_created(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        _generate(full_data_root)
        assert (_gold(full_data_root) / "학생별").is_dir()

    def test_one_md_per_student(self, full_data_root: Path) -> None:
        """SC-009: generate writes exactly one md per student — all 3."""
        _ingest(full_data_root)
        _generate(full_data_root)
        mds = list((_gold(full_data_root) / "학생별").glob("*.md"))
        assert len(mds) == 3, (
            f"SC-009: expected 3 student md files; got {len(mds)}"
        )

    def test_each_md_has_citation_or_no_evidence(self, full_data_root: Path) -> None:
        """SC-009/DET-02: each Gold md contains cited evidence OR '근거 없음'."""
        _ingest(full_data_root)
        _generate(full_data_root)
        student_dir = _gold(full_data_root) / "학생별"
        for f in student_dir.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            has_citation = "출처:" in text
            has_no_evidence = "근거 없음" in text
            assert has_citation or has_no_evidence, (
                f"SC-009: {f.name} has neither '출처:' nor '근거 없음'"
            )


# ---------------------------------------------------------------------------
# SC-006: every entry has source_id resolving to source_ledger with ingested_at
# ---------------------------------------------------------------------------


class TestSC006Provenance:
    """SC-006: every codex entry's source_id resolves to a source_ledger row w/ ingested_at."""

    def test_source_ledger_exists(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        assert (_silver(full_data_root) / "source_ledger.parquet").is_file()

    def test_every_entry_source_resolves(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        silver = _silver(full_data_root)
        entries = pd.read_parquet(silver / "codex_entry.parquet")
        ledger = pd.read_parquet(silver / "source_ledger.parquet")
        ledger_ids = set(ledger["source_id"])
        orphan_sources = set(entries["source_id"]) - ledger_ids
        assert not orphan_sources, (
            f"SC-006: codex entries reference unknown source_ids: {orphan_sources}"
        )

    def test_every_ledger_row_has_ingested_at(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        ledger = pd.read_parquet(_silver(full_data_root) / "source_ledger.parquet")
        assert ledger["ingested_at"].notna().all(), (
            "SC-006: every source_ledger row must carry ingested_at (time-order reconstructable)"
        )
        assert (ledger["ingested_at"] == _NOW_INGEST).all(), (
            f"SC-006: expected ingested_at == {_NOW_INGEST!r}"
        )


# ---------------------------------------------------------------------------
# SC-007 / DET-01: re-running ingest with same --now → byte-identical parquet
# ---------------------------------------------------------------------------


class TestSC007Idempotent:
    """SC-007/DET-01: re-running ingest with same --now leaves codex_entry.parquet identical."""

    def test_codex_parquet_byte_identical_on_rerun(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        first_bytes = (_silver(full_data_root) / "codex_entry.parquet").read_bytes()
        _ingest(full_data_root)
        second_bytes = (_silver(full_data_root) / "codex_entry.parquet").read_bytes()
        assert first_bytes == second_bytes, (
            "SC-007/DET-01: codex_entry.parquet is not byte-identical on second ingest"
        )

    def test_entry_count_unchanged_on_rerun(self, full_data_root: Path) -> None:
        _ingest(full_data_root)
        df1 = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        count1 = len(df1)
        _ingest(full_data_root)
        df2 = pd.read_parquet(_silver(full_data_root) / "codex_entry.parquet")
        count2 = len(df2)
        assert count1 == count2, (
            f"SC-007: entry_count changed on re-ingest: {count1} → {count2}"
        )


# ---------------------------------------------------------------------------
# SC-003 / Scenario D: per-advisor dirs contain ONLY their advisees
# ---------------------------------------------------------------------------


class TestSC003NoAdvisorCrossLeak:
    """SC-003: each 지도교수별/{advisor}/ contains ONLY that advisor's advisees."""

    def _student_ids_in_advisor_dir(self, advisor_dir: Path) -> set[str]:
        """Parse the leading 10-char student_id from all non-index md file stems."""
        sids = set()
        for f in advisor_dir.glob("*.md"):
            if f.name.startswith("_"):
                continue
            m = re.match(r"^(\d{10})", f.stem)
            if m:
                sids.add(m.group(1))
        return sids

    def _run_full_pipeline(self, data_root: Path) -> None:
        assert _ingest(data_root) == 0
        assert _generate(data_root) == 0
        assert _distribute(data_root) == 0

    def test_adv_a_dir_created(self, full_data_root: Path) -> None:
        self._run_full_pipeline(full_data_root)
        assert (_gold(full_data_root) / "지도교수별" / _ADV_A).is_dir()

    def test_adv_b_dir_created(self, full_data_root: Path) -> None:
        self._run_full_pipeline(full_data_root)
        assert (_gold(full_data_root) / "지도교수별" / _ADV_B).is_dir()

    def test_adv_a_contains_only_full_student(self, full_data_root: Path) -> None:
        """SC-003: ADV_A's dir contains ONLY the FULL student (SID_FULL)."""
        self._run_full_pipeline(full_data_root)
        sids = self._student_ids_in_advisor_dir(
            _gold(full_data_root) / "지도교수별" / _ADV_A
        )
        assert sids == {_SID_FULL}, (
            f"SC-003: ADV_A dir must contain only {_SID_FULL}; got {sids}"
        )

    def test_adv_b_contains_only_minimal_student(self, full_data_root: Path) -> None:
        """SC-003: ADV_B's dir contains ONLY the MINIMAL student (SID_MINIMAL)."""
        self._run_full_pipeline(full_data_root)
        sids = self._student_ids_in_advisor_dir(
            _gold(full_data_root) / "지도교수별" / _ADV_B
        )
        assert sids == {_SID_MINIMAL}, (
            f"SC-003: ADV_B dir must contain only {_SID_MINIMAL}; got {sids}"
        )

    def test_cross_leak_zero(self, full_data_root: Path) -> None:
        """SC-003: zero files belong to the wrong advisor."""
        self._run_full_pipeline(full_data_root)
        expected = {_ADV_A: {_SID_FULL}, _ADV_B: {_SID_MINIMAL}}
        leaks = 0
        for advisor_id, expected_sids in expected.items():
            advisor_dir = _gold(full_data_root) / "지도교수별" / advisor_id
            for sid in self._student_ids_in_advisor_dir(advisor_dir):
                if sid not in expected_sids:
                    leaks += 1
        assert leaks == 0, f"SC-003: {leaks} cross-leak(s) detected"


# ---------------------------------------------------------------------------
# SC-008 / Scenario D: UNASSIGNED student in 미배정.md + manifest.unassigned_sids
# ---------------------------------------------------------------------------


class TestSC008UnassignedReporting:
    """SC-008: UNASSIGNED student appears in 미배정.md and manifest.unassigned_sids."""

    def _run_full_pipeline(self, data_root: Path) -> None:
        assert _ingest(data_root) == 0
        assert _generate(data_root) == 0
        assert _distribute(data_root) == 0

    def test_mibaejeong_written(self, full_data_root: Path) -> None:
        self._run_full_pipeline(full_data_root)
        assert (_gold(full_data_root) / "미배정.md").is_file(), (
            "SC-008: 미배정.md must exist after distribute"
        )

    def test_unassigned_student_in_mibaejeong(self, full_data_root: Path) -> None:
        self._run_full_pipeline(full_data_root)
        text = (_gold(full_data_root) / "미배정.md").read_text(encoding="utf-8")
        assert _SID_UNAS in text, (
            f"SC-008: {_SID_UNAS} must appear in 미배정.md"
        )

    def test_unassigned_in_manifest(self, full_data_root: Path) -> None:
        self._run_full_pipeline(full_data_root)
        manifest = json.loads(
            (_silver(full_data_root) / "manifest_metric-codex.json").read_text(
                encoding="utf-8"
            )
        )
        unassigned = manifest["bundle_summary"]["unassigned_sids"]
        assert _SID_UNAS in unassigned, (
            f"SC-008: {_SID_UNAS} must be in manifest.bundle_summary.unassigned_sids"
        )

    def test_assigned_plus_unassigned_equals_total(self, full_data_root: Path) -> None:
        """SC-008: assigned + unassigned == total (count invariant)."""
        self._run_full_pipeline(full_data_root)
        manifest = json.loads(
            (_silver(full_data_root) / "manifest_metric-codex.json").read_text(
                encoding="utf-8"
            )
        )
        summary = manifest["bundle_summary"]
        total = summary["total_students_with_codex"]
        assigned = summary["assigned_count"]
        unassigned = len(summary["unassigned_sids"])
        assert assigned + unassigned == total, (
            f"SC-008: {assigned} + {unassigned} != {total}"
        )


# ---------------------------------------------------------------------------
# Scenario E: verify on fully-produced artifacts → exit 0 (all invariants pass)
# ---------------------------------------------------------------------------


class TestScenarioEVerifyGate:
    """Scenario E: verify on the fully-produced pipeline artifacts → exit 0."""

    def _run_full_pipeline(self, data_root: Path) -> None:
        assert _ingest(data_root) == 0
        assert _generate(data_root) == 0
        assert _distribute(data_root) == 0

    def test_verify_exits_zero_after_full_pipeline(self, full_data_root: Path) -> None:
        """Scenario E: verify must pass all invariants on a clean pipeline."""
        self._run_full_pipeline(full_data_root)
        rc = _verify(full_data_root)
        assert rc == 0, (
            "Scenario E: verify should exit 0 on a clean pipeline; "
            f"got rc={rc} — check stderr for violated invariants"
        )
