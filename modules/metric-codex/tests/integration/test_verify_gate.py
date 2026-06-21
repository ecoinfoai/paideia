"""T053 RED — Scenario E: verify gate integration test.

Builds a full pipeline (ingest → generate --backend none → distribute) on a
synthetic fixture, then exercises ``metric-codex verify`` for:

1. Clean pass (Scenario E): exit 0, no violations printed to stderr.
2. Injected violations → exit 3, located message names the invariant:
   - PRIV-01: 10-digit student_id written into a staging bundle after generate.
   - PRIV-03: pseudonym_map.parquet rewritten with a duplicate pseudonym.
   - SKIP-02: manifest JSON hand-edited so count invariant breaks.
   - SKIP-03: a foreign student md dropped into an advisor's 지도교수별 dir.

T055: PRIV-04 git-absent → fail-closed (located violation, not vacuous pass).
T054: EVID-02 per-question sentinel check (not whole-file substring).
T059: unassigned_sids entry absent from 미배정.md → located SKIP-02 violation.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

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
    """Write a question_set with one minimal-layer and one rich-layer question.

    ``q_total`` (score_total) resolves for every student (minimal layer present).
    ``q_zscore`` (z_score) is a rich-layer kind the school-Excel-only students
    lack, so it yields ``no_evidence=True`` and the template emits '근거 없음' —
    this exercises the EVID-02 path through the gate on the happy path.
    """
    path.write_text(
        textwrap.dedent("""\
            questions:
              - id: q_total
                text: "총점을 알려주세요."
                entry_kinds:
                  - score_total
                domain: null
              - id: q_zscore
                text: "표준점수를 알려주세요."
                entry_kinds:
                  - z_score
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

    def test_exits_three_on_korean_name_in_staging(
        self, full_pipeline_root: Path
    ) -> None:
        """A known Korean name (in the pseudonym map) in a staging bundle → PRIV-01.

        Exercises the armed name-scan path (assert_no_pii known_names) which the
        10-digit scan never reaches.  The name must be present in the pseudonym
        map so the gate arms it.
        """
        silver = full_pipeline_root / "silver" / "metric-codex" / _KEY
        staging_dir = silver / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Inject a real name from the pseudonym map (NO 10-digit id, NO email),
        # so only the name-scan path can catch it.
        evil_bundle = staging_dir / "S001.json"
        payload = {
            "pseudonym": "S001",
            "available_layers": ["minimal"],
            "questions": [],
            "leaked_name": _NAME_A,  # 김철수 — present in the pseudonym map
        }
        evil_bundle.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on PRIV-01 Korean-name leak, got rc={rc}"
        )

    def test_korean_name_violation_names_priv01(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        silver = full_pipeline_root / "silver" / "metric-codex" / _KEY
        staging_dir = silver / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        evil_bundle = staging_dir / "S002.json"
        payload = {"leaked_name": _NAME_B}  # 이영희 — present in the map
        evil_bundle.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "PRIV-01" in captured.err, (
            f"Expected PRIV-01 (name scan) in stderr; got: {captured.err!r}"
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
# EVID-01/03: Gold md mutated away from the cited template → exit 3
# ---------------------------------------------------------------------------


class TestVerifyEvid01Mutation:
    """Mutating a Gold 학생별 md away from the deterministic template → EVID-01.

    The template byte-match is the gate's core groundedness guarantee: the md
    must equal exactly the cited, deterministic render.  Appending an uncited
    claim or changing a cited value must be caught.
    """

    def _student_md(self, data_root: Path) -> Path:
        student_dir = (
            data_root / "gold" / "metric-codex" / _KEY / "학생별"
        )
        # Pick SID_A's md deterministically.
        md = student_dir / f"{_SID_A}_{_NAME_A}.md"
        assert md.is_file(), f"precondition: {md} must exist after generate"
        return md

    def test_exits_three_on_appended_uncited_claim(
        self, full_pipeline_root: Path
    ) -> None:
        md = self._student_md(full_pipeline_root)
        original = md.read_text(encoding="utf-8")
        # Append an uncited factual claim (not in any citation).
        md.write_text(
            original + "\n- 출석률: 100% (출처 없음)\n", encoding="utf-8"
        )

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on EVID-01 uncited claim, got rc={rc}"
        )

    def test_exits_three_on_changed_cited_value(
        self, full_pipeline_root: Path
    ) -> None:
        md = self._student_md(full_pipeline_root)
        original = md.read_text(encoding="utf-8")
        # SID_A's score_total is 85; mutate the rendered value to 99.
        mutated = original.replace("85", "99")
        assert mutated != original, "precondition: the md must contain '85' to mutate"
        md.write_text(mutated, encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on EVID-01 changed cited value, got rc={rc}"
        )

    def test_violation_message_names_evid01(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        md = self._student_md(full_pipeline_root)
        original = md.read_text(encoding="utf-8")
        md.write_text(original + "\n- 날조된 사실 (출처 없음)\n", encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "EVID-01" in captured.err, (
            f"Expected EVID-01 in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# EVID-02: no_evidence md must contain '근거 없음' → exit 3 if removed
# ---------------------------------------------------------------------------


class TestVerifyEvid02NoEvidence:
    """A no_evidence question whose md lacks '근거 없음' → EVID-02.

    The fixture question_set includes a rich-layer question (q_zscore) that the
    minimal-only students lack, so the template legitimately emits '근거 없음'.
    Removing it (or replacing it with a fabricated value) must be caught.
    """

    def _student_md(self, data_root: Path) -> Path:
        student_dir = (
            data_root / "gold" / "metric-codex" / _KEY / "학생별"
        )
        md = student_dir / f"{_SID_A}_{_NAME_A}.md"
        assert md.is_file(), f"precondition: {md} must exist after generate"
        return md

    def test_clean_md_contains_no_evidence_sentinel(
        self, full_pipeline_root: Path
    ) -> None:
        """Precondition: the happy-path md actually carries '근거 없음'."""
        md = self._student_md(full_pipeline_root)
        assert "근거 없음" in md.read_text(encoding="utf-8"), (
            "fixture must produce a no_evidence section for the rich question"
        )

    def test_exits_three_when_no_evidence_removed(
        self, full_pipeline_root: Path
    ) -> None:
        md = self._student_md(full_pipeline_root)
        original = md.read_text(encoding="utf-8")
        # Remove the '근거 없음' sentinel and substitute a fabricated value.
        mutated = original.replace("근거 없음", "표준점수: 1.5 (날조)")
        assert mutated != original, "precondition: md must contain '근거 없음'"
        md.write_text(mutated, encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on EVID-02 missing '근거 없음', got rc={rc}"
        )

    def test_violation_message_names_evid02(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        md = self._student_md(full_pipeline_root)
        original = md.read_text(encoding="utf-8")
        md.write_text(
            original.replace("근거 없음", "표준점수: 1.5 (날조)"), encoding="utf-8"
        )

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        # EVID-01 (byte-mismatch) AND EVID-02 (missing sentinel) both fire here;
        # the gate must at minimum name EVID-02 for the no_evidence guarantee.
        assert "EVID-02" in captured.err, (
            f"Expected EVID-02 in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# MANIFEST: empty input_hashes → exit 3
# ---------------------------------------------------------------------------


class TestVerifyManifestEmptyHashes:
    """A manifest with empty input_hashes (but valid bundle_summary) → MANIFEST."""

    def _manifest_path(self, data_root: Path) -> Path:
        return (
            data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )

    def test_exits_three_on_empty_input_hashes(
        self, full_pipeline_root: Path
    ) -> None:
        manifest_path = self._manifest_path(full_pipeline_root)
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Strip provenance; keep bundle_summary intact so the manifest loads.
        raw["input_hashes"] = {}
        manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on MANIFEST empty input_hashes, got rc={rc}"
        )

    def test_violation_message_names_manifest(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        manifest_path = self._manifest_path(full_pipeline_root)
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw["input_hashes"] = {}
        manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "MANIFEST" in captured.err, (
            f"Expected MANIFEST in stderr; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# PRIV-04: data dir gitignored (static repo scan + real tmp-repo gate test)
# ---------------------------------------------------------------------------


class TestVerifyPriv04Gitignored:
    """PRIV-04: output dirs must be git-ignored.

    Two layers:
    (1) static scan of the repo-root .gitignore (documents the production rule).
    (2) a real tmp git repo exercising the gate's violation path directly:
        - no data/ rule → check reports a PRIV-04 violation;
        - data/ ignored → no violation.
    """

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

    def _git_init(self, repo: Path) -> None:
        import subprocess

        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-q"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    def test_check_reports_violation_when_data_not_ignored(
        self, tmp_path: Path
    ) -> None:
        """A real tmp repo WITHOUT a data/ rule → check_priv04_gitignored fires."""
        from metric_codex.verify.checks import check_priv04_gitignored

        repo = tmp_path / "repo"
        self._git_init(repo)
        # No .gitignore at all → data/ output paths are NOT ignored.
        data_root = repo / "data"
        (data_root / "silver").mkdir(parents=True)
        (data_root / "gold").mkdir(parents=True)

        violations = check_priv04_gitignored(data_root)
        assert violations, "expected a PRIV-04 violation when data/ is not ignored"
        assert all(v.invariant_id == "PRIV-04" for v in violations)

    def test_check_passes_when_data_ignored(self, tmp_path: Path) -> None:
        """A real tmp repo WITH a data/ rule → check_priv04_gitignored is clean."""
        from metric_codex.verify.checks import check_priv04_gitignored

        repo = tmp_path / "repo"
        self._git_init(repo)
        (repo / ".gitignore").write_text("data/\n", encoding="utf-8")
        data_root = repo / "data"
        (data_root / "silver").mkdir(parents=True)
        (data_root / "gold").mkdir(parents=True)

        violations = check_priv04_gitignored(data_root)
        assert violations == [], (
            f"expected no PRIV-04 violation when data/ is ignored; got {violations}"
        )

    def test_verify_exits_three_on_priv04_in_real_repo(
        self, tmp_path: Path
    ) -> None:
        """End-to-end: a full pipeline in a real tmp repo with NO data/ rule
        makes ``verify`` report PRIV-04 and exit 3.
        """
        repo = tmp_path / "repo"
        self._git_init(repo)
        # Deliberately do NOT ignore data/.
        data_root = repo / "data"
        bronze = data_root / "bronze" / "metric-codex" / _KEY
        bronze.mkdir(parents=True)

        _make_school_excel(bronze / "성적출석.xlsx")
        _make_school_map(bronze / "성적출석_map.yaml")
        qs_path = bronze / "question_set.yaml"
        _make_question_set(qs_path)

        assert app([
            "ingest", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--now", "2026-06-01T00:00:00Z",
        ]) == 0
        assert app([
            "generate", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--question-set", str(qs_path),
            "--backend", "none", "--now", "2026-06-01T01:00:00Z",
        ]) == 0

        rc = _run_verify(data_root)
        assert rc == 3, (
            f"verify should exit 3 on PRIV-04 (data/ not ignored), got rc={rc}"
        )


# ---------------------------------------------------------------------------
# T028 — present-but-unparseable roster → located Violation, not silent None
# ---------------------------------------------------------------------------


class TestVerifyUnparseableRoster:
    """FR-013 (T033): a present roster that raises on parse must emit a
    SKIP-03 located Violation instead of silently degrading to roster=None.

    Before T033 fix: the except branch sets ``roster = None`` so the
    ``지도교수별`` check cannot run and no violation is emitted about the
    parse failure — the error is swallowed.

    After T033 fix: the LocatedInputError from load_roster is caught and
    appended as a SKIP-03 Violation naming the roster file.
    """

    def _build_pipeline_with_bad_roster(self, tmp_path: Path) -> tuple[Path, Path]:
        """Run ingest+generate+distribute with a valid roster, then corrupt it.

        Returns (data_root, roster_path) so the caller can trigger verify.
        """
        data_root = tmp_path / "data"
        bronze = data_root / "bronze" / "metric-codex" / _KEY
        bronze.mkdir(parents=True)

        _make_school_excel(bronze / "성적출석.xlsx")
        _make_school_map(bronze / "성적출석_map.yaml")
        qs_path = bronze / "question_set.yaml"
        _make_question_set(qs_path)

        assert app([
            "ingest", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--now", "2026-06-01T00:00:00Z",
        ]) == 0

        assert app([
            "generate", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--question-set", str(qs_path),
            "--backend", "none", "--now", "2026-06-01T01:00:00Z",
        ]) == 0

        roster_path = bronze / "지도교수배정.yaml"
        _make_roster(roster_path)

        assert app([
            "distribute", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--roster", str(roster_path),
            "--now", "2026-06-01T02:00:00Z",
        ]) == 0

        # Corrupt the roster AFTER distribute (so 지도교수별/ dir exists).
        roster_path.write_text(
            "assignments: [UNPARSEABLE: {bad yaml {{{\n",
            encoding="utf-8",
        )
        return data_root, roster_path

    def test_unparseable_roster_emits_skip03_violation_with_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A present-but-unparseable roster must emit a SKIP-03 Violation naming the file.

        RED: before T033 fix, the except branch in run_all_checks sets
        ``roster = None`` and re-raises no violation about the parse failure.
        The subsequent check_skip03_no_cross_leak sees roster=None and emits
        the generic "no roster was supplied" message pointing to 지도교수별,
        NOT to the roster file that failed to parse.

        After T033 fix: the LocatedInputError from load_roster is caught and
        appended as a SKIP-03 Violation whose ``.file`` attribute names the
        roster path — the file-parse failure is located, not silent.
        """
        data_root, roster_path = self._build_pipeline_with_bad_roster(tmp_path)

        rc = app([
            "verify",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--roster", str(roster_path),
        ])
        captured = capsys.readouterr()

        # Must exit 3 (violation detected).
        assert rc == 3, (
            f"verify should exit 3 when roster is unparseable; got rc={rc}"
        )
        # Must name SKIP-03 as the invariant category.
        assert "SKIP-03" in captured.err, (
            f"expected SKIP-03 Violation in stderr; got: {captured.err!r}"
        )
        # KEY: the Violation must name the roster FILE (not just 지도교수별 dir).
        # Before fix: the only SKIP-03 message points to the bundle dir and says
        # "no roster was supplied".  After fix: the message points to the roster
        # file itself as the parse failure location.
        roster_name = roster_path.name
        assert roster_name in captured.err or str(roster_path) in captured.err, (
            f"SKIP-03 Violation must name the roster file (not just 지도교수별); "
            f"roster={roster_path.name!r}, stderr={captured.err!r}"
        )

    def test_unparseable_roster_does_not_double_emit_skip03(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Carry-over (c) dedup: a present-but-unparseable roster must emit ONLY the
        located parse-failure SKIP-03, NOT the generic "no roster was supplied" note.

        Pins the ``if not roster_parse_failed:`` guard in run_all_checks: when the
        roster exists but fails to parse, we record one located parse-failure
        Violation naming the file and SKIP the second, redundant cross-leak note
        ("no roster was supplied" → points to 지도교수별).  Without the guard, BOTH
        fire — two SKIP-03 lines for one root cause.

        A future edit deleting the guard would re-introduce the duplicate and this
        test would fail (the sibling
        ``test_unparseable_roster_emits_skip03_violation_with_file`` would NOT,
        since it only asserts *a* SKIP-03 naming the file is present).
        """
        data_root, roster_path = self._build_pipeline_with_bad_roster(tmp_path)

        rc = app([
            "verify",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--roster", str(roster_path),
        ])
        captured = capsys.readouterr()

        assert rc == 3, (
            f"verify should exit 3 when roster is unparseable; got rc={rc}"
        )
        # The redundant generic note must NOT appear (dedup guard active).
        assert "no roster was supplied" not in captured.err, (
            "the generic 'no roster was supplied' SKIP-03 note must be suppressed "
            "when a located parse-failure Violation was already recorded; "
            f"stderr={captured.err!r}"
        )
        # Exactly one SKIP-03 line is emitted (the located parse-failure).
        skip03_lines = [ln for ln in captured.err.splitlines() if "[SKIP-03]" in ln]
        assert len(skip03_lines) == 1, (
            f"expected exactly one SKIP-03 line (the located parse failure), "
            f"got {len(skip03_lines)}: {skip03_lines!r}"
        )
        # And that single line is the located parse failure naming the roster file.
        assert "could not be parsed" in skip03_lines[0], (
            f"the sole SKIP-03 line must be the located parse failure; "
            f"got: {skip03_lines[0]!r}"
        )


# ---------------------------------------------------------------------------
# T035 RED — PRIV-01: PII in cache/*.json and staging_responses/*.json
# ---------------------------------------------------------------------------


class TestVerifyPriv01CacheAndStagingResponsesPii:
    """T035 RED: PII in cache/*.json or staging_responses/*.json raw_text
    must be detected by check_priv01_no_staging_pii → exit 3.

    Before fix: check only scans staging/*.json — cache and staging_responses
    are unchecked so PII planted there passes vacuously (exit 0).
    After fix: all three subdirs are scanned; a hit in raw_text raises PRIV-01.
    """

    def _silver(self, data_root: Path) -> Path:
        return data_root / "silver" / "metric-codex" / _KEY

    def test_exits_three_on_sid_in_cache_json(
        self, full_pipeline_root: Path
    ) -> None:
        """T035 RED: a 10-digit student_id in cache/*.json raw_text → exit 3."""
        silver = self._silver(full_pipeline_root)
        cache_dir = silver / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        evil = cache_dir / "evil_cache.json"
        payload = {"raw_text": f"학생 {_SID_A} 점수 85점"}
        evil.write_text(json.dumps(payload), encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on PRIV-01 in cache/raw_text, got rc={rc}"
        )

    def test_violation_priv01_names_cache_file(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        silver = self._silver(full_pipeline_root)
        cache_dir = silver / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        evil = cache_dir / "leak.json"
        payload = {"raw_text": f"student: {_SID_B}"}
        evil.write_text(json.dumps(payload), encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "PRIV-01" in captured.err, (
            f"Expected PRIV-01 in stderr for cache PII; got: {captured.err!r}"
        )

    def test_exits_three_on_sid_in_staging_responses_json(
        self, full_pipeline_root: Path
    ) -> None:
        """T035 RED: a 10-digit student_id in staging_responses/*.json raw_text → exit 3."""
        silver = self._silver(full_pipeline_root)
        sr_dir = silver / "staging_responses"
        sr_dir.mkdir(parents=True, exist_ok=True)

        evil = sr_dir / "S001_response.json"
        payload = {"raw_text": f"학번 {_SID_A} 이름 홍길동"}
        evil.write_text(json.dumps(payload), encoding="utf-8")

        rc = _run_verify(full_pipeline_root)
        assert rc == 3, (
            f"verify should exit 3 on PRIV-01 in staging_responses/raw_text, got rc={rc}"
        )

    def test_violation_priv01_names_staging_responses_file(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        silver = self._silver(full_pipeline_root)
        sr_dir = silver / "staging_responses"
        sr_dir.mkdir(parents=True, exist_ok=True)

        evil = sr_dir / "S002_response.json"
        payload = {"raw_text": f"id={_SID_C}"}
        evil.write_text(json.dumps(payload), encoding="utf-8")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "PRIV-01" in captured.err, (
            f"Expected PRIV-01 in stderr for staging_responses PII; got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# T036 RED — EVID: LLM backend Gold → report-only note, exit 0
# ---------------------------------------------------------------------------


class TestVerifyEvid03LlmReportOnly:
    """T036 RED: when llm_backend != 'none(template)', verify must emit an
    informational 'not grounding-verified (template-only)' note and exit 0.

    Before fix: the else branch in check_evidence_grounding is a bare ``pass``
    — no note is emitted.  After fix: a non-fatal note line is printed (not a
    Violation that triggers exit 3).
    """

    def _manifest_path(self, data_root: Path) -> Path:
        return (
            data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )

    def _set_llm_backend(self, manifest_path: Path, backend: str) -> None:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw["llm_backend"] = backend
        manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def test_exits_zero_for_api_backend_gold(
        self, full_pipeline_root: Path
    ) -> None:
        """T036 RED: llm_backend='api' in manifest → verify exits 0 (non-fatal)."""
        manifest_path = self._manifest_path(full_pipeline_root)
        self._set_llm_backend(manifest_path, "api")

        rc = _run_verify(full_pipeline_root)
        assert rc == 0, (
            f"verify must exit 0 for LLM-rendered Gold (non-fatal note only), got rc={rc}"
        )

    def test_note_contains_not_grounding_verified(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """T036 RED: a 'not grounding-verified (template-only)' line must appear."""
        manifest_path = self._manifest_path(full_pipeline_root)
        self._set_llm_backend(manifest_path, "api")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "not grounding-verified" in combined, (
            f"Expected 'not grounding-verified' note in output; "
            f"stdout={captured.out!r} stderr={captured.err!r}"
        )

    def test_exits_zero_for_subscription_backend_gold(
        self, full_pipeline_root: Path
    ) -> None:
        """subscription backend is also a non-template path → exit 0."""
        manifest_path = self._manifest_path(full_pipeline_root)
        self._set_llm_backend(manifest_path, "subscription")

        rc = _run_verify(full_pipeline_root)
        assert rc == 0, (
            f"verify must exit 0 for subscription-rendered Gold, got rc={rc}"
        )

    def test_note_goes_to_stderr_not_stdout(
        self,
        full_pipeline_root: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """T-E carry-over (a): after refactor the note must go to stderr, not stdout.

        The old implementation printed to sys.stdout via print(..., file=sys.stdout).
        After the refactor, the note is emitted to stderr by run_all_checks so that
        it stays on the same stream as real violations (stderr) while remaining
        exit 0 (report-only, no Violation object).
        """
        manifest_path = self._manifest_path(full_pipeline_root)
        self._set_llm_backend(manifest_path, "api")

        _run_verify(full_pipeline_root)
        captured = capsys.readouterr()
        assert "not grounding-verified" in captured.err, (
            f"note must appear on stderr after refactor; "
            f"stdout={captured.out!r} stderr={captured.err!r}"
        )
        # The note must NOT appear on stdout (it was the old behaviour).
        assert "not grounding-verified" not in captured.out, (
            f"note must NOT appear on stdout after refactor; "
            f"stdout={captured.out!r}"
        )


# ---------------------------------------------------------------------------
# T055 RED — PRIV-04 git-absent → fail-closed (FR-022 / MC-U19)
# ---------------------------------------------------------------------------


class TestVerifyPriv04GitAbsent:
    """T055 RED: when git binary is absent (FileNotFoundError), PRIV-04 must
    fail CLOSED — emit a located Violation stating the check could not be
    determined — instead of the old fail-OPEN behaviour (return True → silent pass).

    The old behaviour: _is_git_ignored catches FileNotFoundError and returns True
    (treated as "ignored") so check_priv04_gitignored finds no violations even
    though it cannot actually verify gitignore status.

    After fix: FileNotFoundError → a PRIV-04 Violation("cannot determine gitignore
    status") is surfaced, making the gate fail closed.
    """

    def _git_init(self, repo: Path) -> None:
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-q"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    def test_git_absent_emits_priv04_violation(self, tmp_path: Path) -> None:
        """T055 RED: patching PATH so git is not found → PRIV-04 Violation fired."""
        from metric_codex.verify.checks import check_priv04_gitignored

        repo = tmp_path / "repo"
        self._git_init(repo)
        # Add .gitignore so the check would normally pass — this proves the
        # failure is from git-absent, not from a missing gitignore rule.
        (repo / ".gitignore").write_text("data/\n", encoding="utf-8")
        data_root = repo / "data"
        (data_root / "silver").mkdir(parents=True)
        (data_root / "gold").mkdir(parents=True)

        # Strip PATH so subprocess.run(["git", ...]) raises FileNotFoundError.
        with (
            patch.dict(os.environ, {"PATH": ""}, clear=False),
            patch("metric_codex.verify.checks.subprocess.run", side_effect=FileNotFoundError),
        ):
            violations = check_priv04_gitignored(data_root)

        assert violations, (
            "expected a PRIV-04 violation when git is absent (fail-closed), "
            "got no violations"
        )
        assert all(v.invariant_id == "PRIV-04" for v in violations), (
            f"all violations must be PRIV-04; got {violations}"
        )
        # The message must communicate that the status CANNOT BE DETERMINED,
        # not that the path is definitively not-ignored.
        combined_msg = " ".join(v.message for v in violations)
        assert any(
            phrase in combined_msg
            for phrase in ("cannot determine", "unavailable", "git not found", "git binary")
        ), (
            f"violation message must say git check could not run; got: {combined_msg!r}"
        )

    def test_git_absent_exits_three_end_to_end(self, tmp_path: Path) -> None:
        """T055 RED: end-to-end verify in a real git repo with git unavailable → exit 3.

        Without the fix: check_priv04_gitignored(data_root) called inside
        run_all_checks returns [] (fail-open) so verify exits 0.
        After fix: at least one PRIV-04 violation is collected → exit 3.
        """
        repo = tmp_path / "repo"
        self._git_init(repo)
        (repo / ".gitignore").write_text("data/\n", encoding="utf-8")
        data_root = repo / "data"
        bronze = data_root / "bronze" / "metric-codex" / _KEY
        bronze.mkdir(parents=True)

        _make_school_excel(bronze / "성적출석.xlsx")
        _make_school_map(bronze / "성적출석_map.yaml")
        qs_path = bronze / "question_set.yaml"
        _make_question_set(qs_path)

        assert app([
            "ingest", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--now", "2026-06-01T00:00:00Z",
        ]) == 0
        assert app([
            "generate", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--question-set", str(qs_path),
            "--backend", "none", "--now", "2026-06-01T01:00:00Z",
        ]) == 0

        # Simulate git binary absent during verify.
        with patch("metric_codex.verify.checks.subprocess.run", side_effect=FileNotFoundError):
            rc = app([
                "verify", "--semester", _SEM, "--course", _COURSE,
                "--data-root", str(data_root),
            ])

        assert rc == 3, (
            f"verify must exit 3 when git is absent (fail-closed); got rc={rc}"
        )


# ---------------------------------------------------------------------------
# T054 RED — EVID-02 per-question sentinel (FR-024 / MC-U17)
# ---------------------------------------------------------------------------


class TestVerifyEvid02PerQuestion:
    """T054 RED: the EVID-02 check must verify '근거 없음' PER no-evidence
    question, not as a single whole-file substring.

    The old behaviour:
        for bq in bundle.questions:
            if bq.answer.no_evidence and "근거 없음" not in on_disk:
                violations.append(...)
                break
    This means: if the file contains "근거 없음" at all (from ANY question),
    the check passes for ALL — a second no-evidence question that is missing
    its sentinel is silently skipped.

    After fix: the check counts how many times "근거 없음" appears and compares
    it to the number of no_evidence questions (or does per-question section
    matching).  A Gold file that has one sentinel but should have two must emit
    exactly one EVID-02 violation for the missing question.
    """

    def _make_question_set_two_no_evidence(self, path: Path) -> None:
        """Write a question_set with TWO rich-layer questions (both → no_evidence).

        q_zscore (z_score) and q_pctile (percentile_cohort) are both rich-layer
        kinds that the school-Excel-only students lack → both yield no_evidence=True
        in the bundle → the template emits '근거 없음' TWICE.
        """
        path.write_text(
            textwrap.dedent("""\
                questions:
                  - id: q_total
                    text: "총점을 알려주세요."
                    entry_kinds:
                      - score_total
                    domain: null
                  - id: q_zscore
                    text: "표준점수를 알려주세요."
                    entry_kinds:
                      - z_score
                    domain: null
                  - id: q_pctile
                    text: "전체 백분위를 알려주세요."
                    entry_kinds:
                      - percentile_cohort
                    domain: null
            """),
            encoding="utf-8",
        )

    def _build_pipeline_two_no_evidence(self, tmp_path: Path) -> Path:
        """Run ingest + generate with a question_set that has 2 no_evidence questions."""
        data_root = tmp_path / "data"
        bronze = data_root / "bronze" / "metric-codex" / _KEY
        bronze.mkdir(parents=True)

        _make_school_excel(bronze / "성적출석.xlsx")
        _make_school_map(bronze / "성적출석_map.yaml")
        qs_path = bronze / "question_set.yaml"
        self._make_question_set_two_no_evidence(qs_path)

        assert app([
            "ingest", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--now", "2026-06-01T00:00:00Z",
        ]) == 0
        assert app([
            "generate", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root), "--question-set", str(qs_path),
            "--backend", "none", "--now", "2026-06-01T01:00:00Z",
        ]) == 0
        return data_root

    def _student_md(self, data_root: Path) -> Path:
        student_dir = data_root / "gold" / "metric-codex" / _KEY / "학생별"
        md = student_dir / f"{_SID_A}_{_NAME_A}.md"
        assert md.is_file(), f"precondition: {md} must exist after generate"
        return md

    def test_precondition_two_sentinels_in_clean_gold(
        self, tmp_path: Path
    ) -> None:
        """Precondition: the clean template emits '근거 없음' TWICE for 2 no_evidence questions."""
        data_root = self._build_pipeline_two_no_evidence(tmp_path)
        md = self._student_md(data_root)
        content = md.read_text(encoding="utf-8")
        count = content.count("근거 없음")
        assert count == 2, (
            f"precondition: expect 2 occurrences of '근거 없음' for 2 no_evidence "
            f"questions, got {count}; md content:\n{content}"
        )

    def test_one_missing_sentinel_emits_evid02_violation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """T054 RED: Gold has 2 no_evidence questions; only 1 '근거 없음' in file.

        Before fix: whole-file check finds one '근거 없음' → passes vacuously.
        After fix: per-question check detects second question is missing → EVID-02.
        """
        data_root = self._build_pipeline_two_no_evidence(tmp_path)
        md = self._student_md(data_root)
        content = md.read_text(encoding="utf-8")

        # Remove exactly ONE occurrence of '근거 없음', leaving the other intact.
        # This preserves the EVID-01 byte-match violation too, but we also need
        # EVID-02 — the key test is that *per-question* detection fires.
        first_pos = content.index("근거 없음")
        mutated = content[:first_pos] + "데이터 없음" + content[first_pos + len("근거 없음"):]
        assert mutated.count("근거 없음") == 1, (
            "precondition: after mutation exactly 1 '근거 없음' must remain"
        )
        md.write_text(mutated, encoding="utf-8")

        manifest_path = (
            data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )
        # Use template backend so byte-match also fires — but EVID-02 must ALSO fire.
        rc = app([
            "verify", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root),
        ])
        captured = capsys.readouterr()

        assert rc == 3, (
            f"verify must exit 3 on EVID-02 missing per-question sentinel; got rc={rc}"
        )
        assert "EVID-02" in captured.err, (
            f"EVID-02 must appear in stderr; got: {captured.err!r}"
        )

    def test_inline_phrase_does_not_mask_missing_standalone_sentinel(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Issue 2: an inline '근거 없음' must NOT compensate for a missing standalone one.

        render_template emits the sentinel ONLY as a standalone line.  A free-text
        citation value/key that literally contained the phrase inline would inflate
        a whole-file substring count and mask a genuinely-missing standalone sentinel.

        Here we remove ONE of the two standalone sentinels and inject the phrase
        INLINE inside another line (simulating a free-text value containing it).
        With the OLD substring ``.count`` the total stays 2 → EVID-02 would PASS
        vacuously.  With the exact-line-match, the standalone count is 1 → EVID-02
        must still fire for the missing question.
        """
        data_root = self._build_pipeline_two_no_evidence(tmp_path)
        md = self._student_md(data_root)
        content = md.read_text(encoding="utf-8")

        # Remove the FIRST standalone sentinel, then embed the phrase inline on a
        # NON-standalone line so a substring count would still see two occurrences.
        first_pos = content.index("근거 없음")
        without_first = (
            content[:first_pos] + "데이터 없음" + content[first_pos + len("근거 없음"):]
        )
        # Inject an inline occurrence (the phrase is part of a longer line, not standalone).
        mutated = without_first + "\n- 메모: 군집 라벨 '근거 없음 후보군' (출처: x, rich)\n"

        # Sanity: a naive substring count still finds 2, but standalone lines == 1.
        assert mutated.count("근거 없음") == 2, (
            "precondition: substring count must remain 2 (one standalone + one inline)"
        )
        standalone = sum(1 for ln in mutated.splitlines() if ln.strip() == "근거 없음")
        assert standalone == 1, (
            f"precondition: exactly 1 standalone sentinel line must remain, got {standalone}"
        )
        md.write_text(mutated, encoding="utf-8")

        rc = app([
            "verify", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root),
        ])
        captured = capsys.readouterr()

        assert rc == 3, (
            f"verify must exit 3 — the inline phrase must not mask the missing "
            f"standalone sentinel; got rc={rc}"
        )
        assert "EVID-02" in captured.err, (
            f"EVID-02 must fire despite the inline occurrence; got: {captured.err!r}"
        )

    def test_both_sentinels_present_exits_zero(self, tmp_path: Path) -> None:
        """When both sentinels are present the gate is clean (no EVID-02)."""
        data_root = self._build_pipeline_two_no_evidence(tmp_path)
        # Do not mutate anything — clean pipeline must exit 0.
        rc = app([
            "verify", "--semester", _SEM, "--course", _COURSE,
            "--data-root", str(data_root),
        ])
        assert rc == 0, (
            f"clean 2-no_evidence pipeline must exit 0; got rc={rc}"
        )


# ---------------------------------------------------------------------------
# T059 RED — unassigned_sids missing from 미배정.md (FR-024 / MC-U33)
# ---------------------------------------------------------------------------


class TestVerifyUnassignedInMibajeong:
    """T059 RED: every student_id in manifest.bundle_summary.unassigned_sids
    must appear in the 미배정.md Gold file.

    Before fix: verify checks the count invariant (SKIP-02) but never confirms
    that each unassigned SID is actually mentioned in 미배정.md — a manifest
    that lists a SID as unassigned but omits it from 미배정.md is silently
    accepted.

    After fix: a SKIP-02 (or dedicated) Violation is raised for each
    unassigned SID that is absent from 미배정.md.
    """

    def _manifest_path(self, data_root: Path) -> Path:
        return (
            data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )

    def _gold_dir(self, data_root: Path) -> Path:
        return data_root / "gold" / "metric-codex" / _KEY

    def test_precondition_mibajeong_md_contains_unassigned_sid(
        self, full_pipeline_root: Path
    ) -> None:
        """Precondition: after distribute, 미배정.md contains SID_C (the unassigned student)."""
        gold_dir = self._gold_dir(full_pipeline_root)
        mibaj_md = gold_dir / "미배정.md"
        assert mibaj_md.is_file(), f"precondition: {mibaj_md} must exist after distribute"
        content = mibaj_md.read_text(encoding="utf-8")
        assert _SID_C in content, (
            f"precondition: 미배정.md must contain unassigned SID {_SID_C!r}; "
            f"content:\n{content}"
        )

    def test_missing_unassigned_sid_emits_violation(
        self, full_pipeline_root: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """T059 RED: inject a ghost SID into unassigned_sids that is NOT in 미배정.md.

        The manifest lists '2026000099' as unassigned (a valid-format 10-digit SID
        that sorts after the real SID_C='2026000003', so all Pydantic validators
        on AdvisorBundleSummary still pass), but 미배정.md only contains SID_C.

        Before fix: no violation emitted — the gate checks the count invariant
        (SKIP-02) but never confirms each unassigned_sids entry is present in
        미배정.md.
        After fix: a located violation names the ghost SID.
        """
        manifest_path = self._manifest_path(full_pipeline_root)
        gold_dir = self._gold_dir(full_pipeline_root)
        mibaj_md = gold_dir / "미배정.md"

        # Inject a ghost unassigned SID that passes Pydantic validators:
        #   - matches ^[0-9]{10}$ (CanonicalStudentId)
        #   - sorts after '2026000003' (ASC-sorted invariant)
        #   - total_students_with_codex bumped to keep count invariant
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        ghost_sid = "2026000099"
        raw["bundle_summary"]["unassigned_sids"].append(ghost_sid)
        raw["bundle_summary"]["total_students_with_codex"] += 1
        manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        # Confirm 미배정.md does NOT mention the ghost SID (it shouldn't).
        assert ghost_sid not in mibaj_md.read_text(encoding="utf-8"), (
            f"precondition: {ghost_sid!r} must NOT be in 미배정.md"
        )

        rc = _run_verify(full_pipeline_root)
        captured = capsys.readouterr()

        assert rc == 3, (
            f"verify must exit 3 when an unassigned_sids entry is absent from "
            f"미배정.md; got rc={rc}"
        )
        # The violation message must name the missing SID.
        assert ghost_sid in captured.err, (
            f"violation message must name the missing SID {ghost_sid!r}; "
            f"stderr={captured.err!r}"
        )

    def test_all_unassigned_sids_present_exits_zero(
        self, full_pipeline_root: Path
    ) -> None:
        """Clean pipeline: all unassigned SIDs are in 미배정.md → exit 0."""
        rc = _run_verify(full_pipeline_root)
        assert rc == 0, (
            f"clean pipeline with unassigned SID properly in 미배정.md must "
            f"exit 0; got rc={rc}"
        )
