"""T053 RED — Scenario E: verify gate integration test.

Builds a full pipeline (ingest → generate --backend none → distribute) on a
synthetic fixture, then exercises ``metric-codex verify`` for:

1. Clean pass (Scenario E): exit 0, no violations printed to stderr.
2. Injected violations → exit 3, located message names the invariant:
   - PRIV-01: 10-digit student_id written into a staging bundle after generate.
   - PRIV-03: pseudonym_map.parquet rewritten with a duplicate pseudonym.
   - SKIP-02: manifest JSON hand-edited so count invariant breaks.
   - SKIP-03: a foreign student md dropped into an advisor's 지도교수별 dir.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from metric_codex.cli.main import app

# ---------------------------------------------------------------------------
# Scenario constants
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEM}-{_COURSE}"

_SID_A = "2026000001"
_NAME_A = "김철수"
_SID_B = "2026000002"
_NAME_B = "이영희"
_SID_C = "2026000003"
_NAME_C = "박지수"

_ADV_A = "ADV_A"
_ADV_B = "ADV_B"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_school_excel(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점", "환산점수", "출석"])
    ws.append([int(_SID_A), _NAME_A, 85, 90.5, 15])
    ws.append([int(_SID_B), _NAME_B, 70, 75.0, 12])
    ws.append([int(_SID_C), _NAME_C, 60, 65.0, 10])
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
    path.write_text(
        textwrap.dedent("""\
            questions:
              - id: q_total
                text: "총점을 알려주세요."
                entry_kinds:
                  - score_total
                domain: null
        """),
        encoding="utf-8",
    )


def _make_roster(path: Path) -> None:
    """Write a roster: SID_A → ADV_A, SID_B → ADV_B, SID_C unassigned."""
    path.write_text(
        textwrap.dedent(f"""\
            assignments:
              - student_id: "{_SID_A}"
                advisor_id: "{_ADV_A}"
                advisor_name: "김교수"
              - student_id: "{_SID_B}"
                advisor_id: "{_ADV_B}"
                advisor_name: "이교수"
        """),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Shared fixture: full pipeline (ingest → generate → distribute)
# ---------------------------------------------------------------------------


@pytest.fixture()
def full_pipeline_root(tmp_path: Path) -> Path:
    """Return a data_root after successful ingest + generate + distribute.

    Three students (A, B, C). A→ADV_A, B→ADV_B, C unassigned.
    """
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    bronze.mkdir(parents=True)

    _make_school_excel(bronze / "성적출석.xlsx")
    _make_school_map(bronze / "성적출석_map.yaml")
    qs_path = bronze / "question_set.yaml"
    _make_question_set(qs_path)

    rc = app([
        "ingest",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--now", "2026-06-01T00:00:00Z",
    ])
    assert rc == 0, f"ingest failed rc={rc}"

    rc = app([
        "generate",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--question-set", str(qs_path),
        "--backend", "none",
        "--now", "2026-06-01T01:00:00Z",
    ])
    assert rc == 0, f"generate failed rc={rc}"

    roster_path = bronze / "지도교수배정.yaml"
    _make_roster(roster_path)

    rc = app([
        "distribute",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--roster", str(roster_path),
        "--now", "2026-06-01T02:00:00Z",
    ])
    assert rc == 0, f"distribute failed rc={rc}"

    return data_root


# ---------------------------------------------------------------------------
# Helper: run verify
# ---------------------------------------------------------------------------


def _run_verify(data_root: Path) -> int:
    return app([
        "verify",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
    ])


# ---------------------------------------------------------------------------
# Scenario E: clean pipeline → exit 0
# ---------------------------------------------------------------------------


class TestVerifyCleanPass:
    """A fully-run pipeline with no injected violations must exit 0."""

    def test_exits_zero(self, full_pipeline_root: Path) -> None:
        rc = _run_verify(full_pipeline_root)
        assert rc == 0, (
            "verify should exit 0 on a clean pipeline but got "
            f"rc={rc}"
        )


# ---------------------------------------------------------------------------
# PRIV-01: staging PII injection → exit 3
# ---------------------------------------------------------------------------


class TestVerifyPriv01StagingPii:
    """A 10-digit student_id injected into a staging bundle → PRIV-01 violation."""

    def test_exits_three_on_sid_in_staging(self, full_pipeline_root: Path) -> None:
        # Write a PII-containing file into the staging directory after generate.
        silver = (
            full_pipeline_root / "silver" / "metric-codex" / _KEY
        )
        staging_dir = silver / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Inject a 10-digit student_id into a staging JSON file.
        evil_bundle = staging_dir / "S001.json"
        payload = {
            "pseudonym": "S001",
            "available_layers": ["minimal"],
            "questions": [],
            "student_id_leak": _SID_A,  # deliberate PII injection
        }
        evil_bundle.write_text(json.dumps(payload), encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on PRIV-01 staging PII, got rc={rc}"
        )

    def test_violation_message_names_priv01(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        silver = (
            full_pipeline_root / "silver" / "metric-codex" / _KEY
        )
        staging_dir = silver / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        evil_bundle = staging_dir / "S002.json"
        payload = {"student_id_leak": _SID_B}
        evil_bundle.write_text(json.dumps(payload), encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "PRIV-01" in captured.err, (
            f"Expected PRIV-01 in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# PRIV-03: non-bijective pseudonym map → exit 3
# ---------------------------------------------------------------------------


class TestVerifyPriv03NonBijective:
    """Rewriting pseudonym_map.parquet with a duplicate pseudonym → PRIV-03."""

    def _silver(self, data_root: Path) -> Path:
        return data_root / "silver" / "metric-codex" / _KEY

    def test_exits_three_on_duplicate_pseudonym(self, full_pipeline_root: Path) -> None:
        pseudonym_path = self._silver(full_pipeline_root) / "pseudonym_map.parquet"

        # Read the existing valid map.
        df = pd.read_parquet(pseudonym_path)
        # Corrupt: set all pseudonyms to the same value (duplicate → non-bijective).
        df["pseudonym"] = "S001"
        df.to_parquet(pseudonym_path, index=False)

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on PRIV-03 non-bijective map, got rc={rc}"
        )

    def test_violation_message_names_priv03(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        pseudonym_path = self._silver(full_pipeline_root) / "pseudonym_map.parquet"
        df = pd.read_parquet(pseudonym_path)
        df["pseudonym"] = "S001"
        df.to_parquet(pseudonym_path, index=False)

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "PRIV-03" in captured.err or "PRIV-05" in captured.err, (
            f"Expected PRIV-03 or PRIV-05 in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# SKIP-02: hand-edited manifest count invariant broken → exit 3
# ---------------------------------------------------------------------------


class TestVerifySkip02CountInvariant:
    """Hand-editing the manifest so assigned + unassigned != total → SKIP-02."""

    def _manifest_path(self, data_root: Path) -> Path:
        return (
            data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )

    def test_exits_three_on_broken_count(self, full_pipeline_root: Path) -> None:
        manifest_path = self._manifest_path(full_pipeline_root)
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Break the count invariant: bump total without updating assigned/unassigned.
        raw["bundle_summary"]["total_students_with_codex"] = 999
        manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on SKIP-02 broken count invariant, got rc={rc}"
        )

    def test_violation_message_names_skip02(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        manifest_path = self._manifest_path(full_pipeline_root)
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw["bundle_summary"]["total_students_with_codex"] = 999
        manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "SKIP-02" in captured.err, (
            f"Expected SKIP-02 in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# SKIP-03: foreign student md in advisor bundle → exit 3
# ---------------------------------------------------------------------------


class TestVerifySkip03CrossLeak:
    """Dropping a foreign student md into an advisor's 지도교수별 dir → SKIP-03."""

    def _adv_dir(self, data_root: Path) -> Path:
        return (
            data_root / "gold" / "metric-codex" / _KEY / "지도교수별" / _ADV_A
        )

    def test_exits_three_on_cross_leak(self, full_pipeline_root: Path) -> None:
        adv_a_dir = self._adv_dir(full_pipeline_root)
        assert adv_a_dir.is_dir(), "precondition: ADV_A dir must exist after distribute"

        # Drop SID_B's md (belongs to ADV_B) into ADV_A's dir — cross-leak.
        foreign_md = adv_a_dir / f"{_SID_B}_{_NAME_B}.md"
        foreign_md.write_text("# 무단침입 학생\n\n근거 없음\n", encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on SKIP-03 cross-leak, got rc={rc}"
        )

    def test_violation_message_names_skip03(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        adv_a_dir = self._adv_dir(full_pipeline_root)
        foreign_md = adv_a_dir / f"{_SID_B}_{_NAME_B}.md"
        foreign_md.write_text("# 무단침입\n\n근거 없음\n", encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "SKIP-03" in captured.err, (
            f"Expected SKIP-03 in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# PRIV-04: data dir gitignored (static test against repo .gitignore)
# ---------------------------------------------------------------------------


class TestVerifyPriv04Gitignored:
    """The repo-root .gitignore must include data/ (PRIV-04)."""

    def test_gitignore_excludes_data(self) -> None:
        repo_root = Path(__file__).parents[4]  # climb: integration → tests → metric-codex → modules → paideia
        gitignore = repo_root / ".gitignore"
        assert gitignore.exists(), f"No .gitignore at {gitignore}"

        lines = [
            ln.strip()
            for ln in gitignore.read_text(encoding="utf-8").splitlines()
        ]
        data_excluded = any(
            ln in ("data/", "data") or ln.startswith("data/")
            for ln in lines
            if not ln.startswith("#") and ln
        )
        assert data_excluded, (
            f"data/ is not excluded in {gitignore} — "
            "PRIV-04: PII-bearing artifacts must be gitignored."
        )
