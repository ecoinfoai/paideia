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
