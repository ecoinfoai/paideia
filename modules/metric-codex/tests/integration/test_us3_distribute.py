"""T047 RED — US3 Scenario D: per-advisor distribution integration test.

Builds a gold/학생별/ with 3 students, maps 2 to different advisors (A, B),
leaves one student unmapped. Runs 'distribute' and asserts:

  (a) SC-003/FR-019/SKIP-03: cross-leak count == 0 (each advisor dir contains
      ONLY their own advisee files, verified by student_id parsing).
  (b) SC-008/SKIP-02: the unmapped student appears in 미배정.md AND in
      AdvisorBundleSummary.unassigned_sids (no silent drop).
  (c) Count invariant: assigned_count + len(unassigned_sids) == total.
  (d) Constitution V: updated manifest still carries prior input_hashes/config_ids.
  (e) Determinism: re-running produce byte-identical bundle layout.
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
_NAME_A = "김철수"
_SID_B = "2026000002"
_NAME_B = "이영희"
_SID_C = "2026000003"
_NAME_C = "박지수"

_ADV_A = "ADV_A"
_ADV_B = "ADV_B"

# SID_A → ADV_A, SID_B → ADV_B, SID_C → unassigned


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
        """),
        encoding="utf-8",
    )


def _make_roster(path: Path) -> None:
    """Write a roster: SID_A→ADV_A, SID_B→ADV_B, SID_C not listed."""
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


@pytest.fixture()
def generated_data_root(tmp_path: Path) -> Path:
    """Return a data_root after successful ingest + generate runs (3 students)."""
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
    assert rc == 0, f"ingest failed with rc={rc}"

    qs_path = bronze / "question_set.yaml"
    _make_question_set(qs_path)

    rc = app([
        "generate",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--question-set", str(qs_path),
        "--backend", "none",
        "--now", "2026-06-01T01:00:00Z",
    ])
    assert rc == 0, f"generate failed with rc={rc}"

    # Verify student md files were created.
    student_dir = data_root / "gold" / "metric-codex" / _KEY / "학생별"
    mds = list(student_dir.glob("*.md"))
    assert len(mds) == 3, f"expected 3 student mds, got {len(mds)}"

    return data_root


@pytest.fixture()
def roster_path(generated_data_root: Path) -> Path:
    """Write the advisor roster and return its path."""
    bronze = generated_data_root / "bronze" / "metric-codex" / _KEY
    p = bronze / "지도교수배정.yaml"
    _make_roster(p)
    return p


def _run_distribute(data_root: Path, roster: Path) -> int:
    return app([
        "distribute",
        "--semester", _SEM,
        "--course", _COURSE,
        "--data-root", str(data_root),
        "--roster", str(roster),
        "--now", "2026-06-02T00:00:00Z",
    ])


# ---------------------------------------------------------------------------
# Scenario D: basic distribute
# ---------------------------------------------------------------------------


class TestDistributeExitsZero:
    def test_distribute_exits_zero(self, generated_data_root, roster_path):
        rc = _run_distribute(generated_data_root, roster_path)
        assert rc == 0


class TestDistributeNoCrossLeak:
    """SC-003/FR-017/SKIP-03: each advisor dir ONLY contains their advisee files."""

    def _advisor_dir(self, data_root: Path, advisor_id: str) -> Path:
        return data_root / "gold" / "metric-codex" / _KEY / "지도교수별" / advisor_id

    def _sid_from_filename(self, name: str) -> str:
        """Parse the leading 10-char student_id from a file stem."""
        stem = Path(name).stem
        m = re.match(r"^(\d{10})", stem)
        assert m is not None, f"Cannot parse student_id from filename: {name!r}"
        return m.group(1)

    def test_adv_a_dir_created(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        assert self._advisor_dir(generated_data_root, _ADV_A).is_dir()

    def test_adv_b_dir_created(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        assert self._advisor_dir(generated_data_root, _ADV_B).is_dir()

    def test_adv_a_contains_only_sid_a(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        adv_a_dir = self._advisor_dir(generated_data_root, _ADV_A)
        md_files = [f for f in adv_a_dir.glob("*.md") if not f.name.startswith("_")]
        sids = {self._sid_from_filename(f.name) for f in md_files}
        assert sids == {_SID_A}, (
            f"ADV_A dir contains unexpected students: {sids}"
        )

    def test_adv_b_contains_only_sid_b(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        adv_b_dir = self._advisor_dir(generated_data_root, _ADV_B)
        md_files = [f for f in adv_b_dir.glob("*.md") if not f.name.startswith("_")]
        sids = {self._sid_from_filename(f.name) for f in md_files}
        assert sids == {_SID_B}, (
            f"ADV_B dir contains unexpected students: {sids}"
        )

    def test_cross_leak_count_zero(self, generated_data_root, roster_path):
        """SC-003: zero files belong to a wrong advisor."""
        _run_distribute(generated_data_root, roster_path)
        expected_map = {_ADV_A: {_SID_A}, _ADV_B: {_SID_B}}
        leaks = 0
        for advisor_id, expected_sids in expected_map.items():
            adv_dir = self._advisor_dir(generated_data_root, advisor_id)
            md_files = [f for f in adv_dir.glob("*.md") if not f.name.startswith("_")]
            for f in md_files:
                sid = self._sid_from_filename(f.name)
                if sid not in expected_sids:
                    leaks += 1
        assert leaks == 0, f"Cross-leak detected: {leaks} file(s) in wrong advisor dir"


class TestDistributeUnassigned:
    """SC-008/SKIP-02: unassigned students are reported, never dropped."""

    def _gold(self, data_root: Path) -> Path:
        return data_root / "gold" / "metric-codex" / _KEY

    def test_mibaejeong_written(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        assert (self._gold(generated_data_root) / "미배정.md").is_file()

    def test_sid_c_in_mibaejeong(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        text = (self._gold(generated_data_root) / "미배정.md").read_text(encoding="utf-8")
        assert _SID_C in text, f"{_SID_C} not found in 미배정.md"

    def test_unassigned_in_manifest_summary(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        manifest_path = (
            generated_data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = manifest["bundle_summary"]
        assert _SID_C in summary["unassigned_sids"]


class TestDistributeCountInvariant:
    """Count invariant: assigned + unassigned == total."""

    def test_count_invariant(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        manifest_path = (
            generated_data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = manifest["bundle_summary"]
        total = summary["total_students_with_codex"]
        assigned = summary["assigned_count"]
        unassigned = len(summary["unassigned_sids"])
        assert assigned + unassigned == total, (
            f"{assigned} + {unassigned} != {total}"
        )


class TestDistributeProvenancePreserved:
    """Constitution V: distribute must not clobber ingest/generate provenance."""

    def test_input_hashes_preserved(self, generated_data_root, roster_path):
        manifest_path = (
            generated_data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior_input_hashes = prior["input_hashes"]
        prior_config_ids = prior["config_ids"]
        assert prior_input_hashes  # sanity

        _run_distribute(generated_data_root, roster_path)

        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert after["input_hashes"] == prior_input_hashes
        assert after["config_ids"] == prior_config_ids

    def test_bundle_summary_updated(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        manifest_path = (
            generated_data_root / "silver" / "metric-codex" / _KEY
            / "manifest_metric-codex.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = manifest["bundle_summary"]
        # 2 assigned (ADV_A + ADV_B have one each), 1 unassigned, 3 total.
        assert summary["total_students_with_codex"] == 3
        assert summary["assigned_count"] == 2
        assert summary["advisor_count"] == 2
        assert summary["unassigned_sids"] == [_SID_C]


class TestDistributeDeterminism:
    """Same roster + same --now → byte-identical bundle layout on re-run."""

    def _bundle_dir(self, data_root: Path) -> Path:
        return data_root / "gold" / "metric-codex" / _KEY / "지도교수별"

    def test_deterministic_rerun(self, generated_data_root, roster_path):
        def _run():
            rc = _run_distribute(generated_data_root, roster_path)
            assert rc == 0

        _run()
        bundle_dir = self._bundle_dir(generated_data_root)
        contents_1 = {
            str(f.relative_to(bundle_dir)): f.read_bytes()
            for f in sorted(bundle_dir.rglob("*.md"))
        }
        _run()
        contents_2 = {
            str(f.relative_to(bundle_dir)): f.read_bytes()
            for f in sorted(bundle_dir.rglob("*.md"))
        }
        assert contents_1 == contents_2, "distribute is not deterministic"


class TestDistributeInvalidRoster:
    """Malformed roster → exit 2."""

    def test_missing_roster_exits_2(self, generated_data_root):
        rc = app([
            "distribute",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(generated_data_root),
            "--roster", str(generated_data_root / "nonexistent.yaml"),
            "--now", "2026-06-02T00:00:00Z",
        ])
        assert rc == 2

    def test_duplicate_sid_in_roster_exits_2(self, generated_data_root, tmp_path):
        bad_roster = tmp_path / "bad.yaml"
        bad_roster.write_text(
            textwrap.dedent(f"""\
                assignments:
                  - student_id: "{_SID_A}"
                    advisor_id: "{_ADV_A}"
                  - student_id: "{_SID_A}"
                    advisor_id: "{_ADV_B}"
            """),
            encoding="utf-8",
        )
        rc = app([
            "distribute",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(generated_data_root),
            "--roster", str(bad_roster),
            "--now", "2026-06-02T00:00:00Z",
        ])
        assert rc == 2


class TestDistributeIndexFile:
    """Each advisor dir has a _index.md listing their advisees."""

    def test_adv_a_index_exists(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        index = (
            generated_data_root / "gold" / "metric-codex" / _KEY
            / "지도교수별" / _ADV_A / "_index.md"
        )
        assert index.is_file()

    def test_adv_a_index_contains_sid_a(self, generated_data_root, roster_path):
        _run_distribute(generated_data_root, roster_path)
        index = (
            generated_data_root / "gold" / "metric-codex" / _KEY
            / "지도교수별" / _ADV_A / "_index.md"
        )
        text = index.read_text(encoding="utf-8")
        assert _SID_A in text


class TestDistributePathTraversal:
    """CRITICAL: advisor_id='../evil' must NOT escape 지도교수별/ into rmtree."""

    def test_path_traversal_roster_exits_2(self, generated_data_root, tmp_path):
        """A roster with advisor_id='../evil' → exit 2 (LocatedInputError)."""
        evil_roster = tmp_path / "evil.yaml"
        evil_roster.write_text(
            textwrap.dedent(f"""\
                assignments:
                  - student_id: "{_SID_A}"
                    advisor_id: "../evil"
            """),
            encoding="utf-8",
        )
        rc = app([
            "distribute",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(generated_data_root),
            "--roster", str(evil_roster),
            "--now", "2026-06-02T00:00:00Z",
        ])
        assert rc == 2

    def test_path_traversal_does_not_delete_sibling(self, generated_data_root, tmp_path):
        """The destructive rmtree must NOT touch 학생별/ or 미배정.md siblings."""
        gold = generated_data_root / "gold" / "metric-codex" / _KEY
        student_dir = gold / "학생별"
        before = sorted(p.name for p in student_dir.glob("*.md"))
        assert before, "precondition: 학생별 has md files before the evil run"

        evil_roster = tmp_path / "evil.yaml"
        evil_roster.write_text(
            textwrap.dedent(f"""\
                assignments:
                  - student_id: "{_SID_A}"
                    advisor_id: "../evil"
            """),
            encoding="utf-8",
        )
        app([
            "distribute",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(generated_data_root),
            "--roster", str(evil_roster),
            "--now", "2026-06-02T00:00:00Z",
        ])

        # 학생별/ untouched (no destructive escape).
        after = sorted(p.name for p in student_dir.glob("*.md"))
        assert after == before, "학생별/ was modified by a path-traversal advisor_id"
        # No 'evil' directory created as a sibling of 지도교수별/.
        assert not (gold / "evil").exists()


class TestDistributeStaleRemovedAdvisor:
    """I-2: an advisor in a prior roster but not the new one must not linger."""

    def test_removed_advisor_dir_gone(self, generated_data_root, tmp_path):
        bundle_root = (
            generated_data_root / "gold" / "metric-codex" / _KEY / "지도교수별"
        )

        # First run: roster {A, B}.
        roster_ab = tmp_path / "roster_ab.yaml"
        _make_roster(roster_ab)
        rc = _run_distribute(generated_data_root, roster_ab)
        assert rc == 0
        assert (bundle_root / _ADV_B).is_dir(), "B should exist after first run"

        # Second run: roster {A only} — B is removed.
        roster_a = tmp_path / "roster_a.yaml"
        roster_a.write_text(
            textwrap.dedent(f"""\
                assignments:
                  - student_id: "{_SID_A}"
                    advisor_id: "{_ADV_A}"
            """),
            encoding="utf-8",
        )
        rc = _run_distribute(generated_data_root, roster_a)
        assert rc == 0

        # B's stale bundle must be gone (FR-017: no cross-leak across runs).
        assert not (bundle_root / _ADV_B).exists(), (
            "removed advisor B's stale bundle lingered"
        )
        assert (bundle_root / _ADV_A).is_dir()


class TestDistributeNoNameStudent:
    """M-4: a {student_id}.md (no name) student distributes + reports correctly."""

    def test_no_name_student_unassigned_reported(self, generated_data_root, tmp_path):
        """A bare {sid}.md student absent from the roster appears in 미배정.md."""
        gold = generated_data_root / "gold" / "metric-codex" / _KEY
        student_dir = gold / "학생별"
        # Add a no-name student md (bare student_id stem).
        bare_sid = "2026000099"
        (student_dir / f"{bare_sid}.md").write_text(
            "# 무명 학생\n\n근거 없음\n", encoding="utf-8"
        )

        roster_a = tmp_path / "roster_a.yaml"
        roster_a.write_text(
            textwrap.dedent(f"""\
                assignments:
                  - student_id: "{_SID_A}"
                    advisor_id: "{_ADV_A}"
            """),
            encoding="utf-8",
        )
        rc = _run_distribute(generated_data_root, roster_a)
        assert rc == 0

        mibaejeong = (gold / "미배정.md").read_text(encoding="utf-8")
        assert bare_sid in mibaejeong

    def test_no_name_student_assigned_in_bundle(self, generated_data_root, tmp_path):
        """A bare {sid}.md student in the roster lands in the advisor bundle."""
        gold = generated_data_root / "gold" / "metric-codex" / _KEY
        student_dir = gold / "학생별"
        bare_sid = "2026000099"
        (student_dir / f"{bare_sid}.md").write_text(
            "# 무명 학생\n\n근거 없음\n", encoding="utf-8"
        )

        roster = tmp_path / "roster.yaml"
        roster.write_text(
            textwrap.dedent(f"""\
                assignments:
                  - student_id: "{bare_sid}"
                    advisor_id: "{_ADV_A}"
            """),
            encoding="utf-8",
        )
        rc = _run_distribute(generated_data_root, roster)
        assert rc == 0

        adv_dir = gold / "지도교수별" / _ADV_A
        assert (adv_dir / f"{bare_sid}.md").is_file()
        index = (adv_dir / "_index.md").read_text(encoding="utf-8")
        assert bare_sid in index


class TestDistributeMissingStudentDir:
    """M-5: missing 학생별/ → LocatedInputError (exit 2), not silent empty bundles."""

    def test_missing_student_dir_exits_2(self, tmp_path):
        data_root = tmp_path / "data"
        bronze = data_root / "bronze" / "metric-codex" / _KEY
        bronze.mkdir(parents=True)
        roster = bronze / "지도교수배정.yaml"
        _make_roster(roster)

        # No generate run → no gold/학생별/.
        rc = app([
            "distribute",
            "--semester", _SEM,
            "--course", _COURSE,
            "--data-root", str(data_root),
            "--roster", str(roster),
            "--now", "2026-06-02T00:00:00Z",
        ])
        assert rc == 2
