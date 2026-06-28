"""T055 RED — Full pipeline ``build`` command integration test.

Exercises ``metric-codex build`` which chains ingest→generate→distribute→verify
in a single invocation.  Tests:

1. Happy path (Scenario F): a synthetic fixture produces exit 0 and ALL stage
   artifacts exist: Silver parquet store + pseudonym map + manifest; Gold
   학생별/*.md for every student; Gold 지도교수별/{advisor}/…; Gold 미배정.md;
   manifest bundle_summary reflects the real assigned/unassigned counts.

2. First-non-zero stop: a malformed input causes ingest to fail (exit 2); the
   pipeline stops and later-stage artifacts (학생별/, 지도교수별/) are NOT created.
"""

from __future__ import annotations

import json
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

_NOW = "2026-06-20T00:00:00Z"

# ---------------------------------------------------------------------------
# Fixture helpers (mirrored from test_us3_distribute / test_verify_gate)
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
# Helpers
# ---------------------------------------------------------------------------


def _silver(data_root: Path) -> Path:
    return data_root / "silver" / "metric-codex" / _KEY


def _gold(data_root: Path) -> Path:
    return data_root / "gold" / "metric-codex" / _KEY


def _run_build(data_root: Path, extra: list[str] | None = None) -> int:
    """Invoke ``metric-codex build`` with the standard fixture arguments."""
    argv = [
        "build",
        "--semester",
        _SEM,
        "--course",
        _COURSE,
        "--data-root",
        str(data_root),
        "--backend",
        "none",
        "--now",
        _NOW,
    ]
    if extra:
        argv.extend(extra)
    return app(argv)


# ---------------------------------------------------------------------------
# Shared fixture: a fully-wired Bronze tree (happy path)
# ---------------------------------------------------------------------------


@pytest.fixture()
def bronze_root(tmp_path: Path) -> Path:
    """Return a data_root with all required Bronze inputs for 3 students."""
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    bronze.mkdir(parents=True)

    _make_school_excel(bronze / "성적출석.xlsx")
    _make_school_map(bronze / "성적출석_map.yaml")
    _make_question_set(bronze / "question_set.yaml")
    _make_roster(bronze / "지도교수배정.yaml")

    return data_root


# ---------------------------------------------------------------------------
# Happy path: build exits 0
# ---------------------------------------------------------------------------


class TestBuildExitsZero:
    """build exits 0 when all stages succeed."""

    def test_exits_zero(self, bronze_root: Path) -> None:
        rc = _run_build(bronze_root)
        assert rc == 0, f"build should exit 0 on happy path; got rc={rc}"


# ---------------------------------------------------------------------------
# Silver artifacts exist after build
# ---------------------------------------------------------------------------


class TestBuildSilverArtifacts:
    """Silver parquet store, pseudonym map, and manifest written by build."""

    def test_codex_parquet_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_silver(bronze_root) / "codex_entry.parquet").is_file()

    def test_pseudonym_map_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_silver(bronze_root) / "pseudonym_map.parquet").is_file()

    def test_manifest_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_silver(bronze_root) / "manifest_metric-codex.json").is_file()


# ---------------------------------------------------------------------------
# Gold 학생별 artifacts
# ---------------------------------------------------------------------------


class TestBuildGoldStudentMds:
    """Gold 학생별/*.md written for every student after build."""

    def test_student_dir_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_gold(bronze_root) / "학생별").is_dir()

    def test_three_student_mds_exist(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        mds = list((_gold(bronze_root) / "학생별").glob("*.md"))
        assert len(mds) == 3, f"expected 3 student mds; got {len(mds)}"

    def test_sid_a_md_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        # File name is {sid}_{name}.md.
        student_dir = _gold(bronze_root) / "학생별"
        sids = {p.stem.split("_")[0] for p in student_dir.glob("*.md")}
        assert _SID_A in sids, f"{_SID_A} md not found in 학생별/"


# ---------------------------------------------------------------------------
# Gold 지도교수별 artifacts
# ---------------------------------------------------------------------------


class TestBuildGoldAdvisorBundles:
    """Gold 지도교수별/{advisor}/… written for assigned advisors."""

    def test_advisor_dir_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_gold(bronze_root) / "지도교수별").is_dir()

    def test_adv_a_dir_created(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_gold(bronze_root) / "지도교수별" / _ADV_A).is_dir()

    def test_adv_b_dir_created(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_gold(bronze_root) / "지도교수별" / _ADV_B).is_dir()


# ---------------------------------------------------------------------------
# Gold 미배정.md
# ---------------------------------------------------------------------------


class TestBuildGoldUnassigned:
    """미배정.md written and contains SID_C (only unassigned student)."""

    def test_mibaejeong_exists(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert (_gold(bronze_root) / "미배정.md").is_file()

    def test_sid_c_in_mibaejeong(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        text = (_gold(bronze_root) / "미배정.md").read_text(encoding="utf-8")
        assert _SID_C in text, f"{_SID_C} not found in 미배정.md"


# ---------------------------------------------------------------------------
# Manifest bundle_summary reflects real counts (verify ran clean inside build)
# ---------------------------------------------------------------------------


class TestBuildManifestSummary:
    """Final manifest bundle_summary reflects the distribute stage's counts.

    The bundle_summary (assigned/unassigned/advisor counts) is written by
    distribute; verify runs last and is read-only, so it does not alter these
    values — it only confirms they are internally consistent on a clean pass.
    """

    def _summary(self, data_root: Path) -> dict:
        raw = json.loads(
            (_silver(data_root) / "manifest_metric-codex.json").read_text(encoding="utf-8")
        )
        return raw["bundle_summary"]

    def test_total_students_is_three(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert self._summary(bronze_root)["total_students_with_codex"] == 3

    def test_assigned_count_is_two(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert self._summary(bronze_root)["assigned_count"] == 2

    def test_advisor_count_is_two(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert self._summary(bronze_root)["advisor_count"] == 2

    def test_unassigned_contains_sid_c(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        assert _SID_C in self._summary(bronze_root)["unassigned_sids"]

    def test_count_invariant(self, bronze_root: Path) -> None:
        _run_build(bronze_root)
        s = self._summary(bronze_root)
        total = s["total_students_with_codex"]
        assigned = s["assigned_count"]
        unassigned = len(s["unassigned_sids"])
        assert assigned + unassigned == total, f"{assigned} + {unassigned} != {total}"


# ---------------------------------------------------------------------------
# First-non-zero stop: ingest failure stops pipeline (no later-stage artifacts)
# ---------------------------------------------------------------------------


class TestBuildFirstNonZeroStop:
    """A bad ingest input exits 2 and prevents later-stage artifacts from appearing."""

    @pytest.fixture()
    def bad_bronze_root(self, tmp_path: Path) -> Path:
        """Bronze tree missing the school map → ingest fails with exit 2."""
        data_root = tmp_path / "data"
        bronze = data_root / "bronze" / "metric-codex" / _KEY
        bronze.mkdir(parents=True)

        _make_school_excel(bronze / "성적출석.xlsx")
        # Deliberately write an invalid school map (empty YAML → schema error).
        (bronze / "성적출석_map.yaml").write_text("# intentionally blank\n", encoding="utf-8")
        _make_question_set(bronze / "question_set.yaml")
        _make_roster(bronze / "지도교수배정.yaml")

        return data_root

    def test_exits_two_on_ingest_failure(self, bad_bronze_root: Path) -> None:
        rc = _run_build(bad_bronze_root)
        assert rc == 2, f"build should propagate ingest exit 2; got rc={rc}"

    def test_student_dir_not_created(self, bad_bronze_root: Path) -> None:
        _run_build(bad_bronze_root)
        student_dir = _gold(bad_bronze_root) / "학생별"
        assert not student_dir.exists(), "학생별/ must NOT exist when pipeline stops at ingest"

    def test_advisor_dir_not_created(self, bad_bronze_root: Path) -> None:
        _run_build(bad_bronze_root)
        advisor_dir = _gold(bad_bronze_root) / "지도교수별"
        assert not advisor_dir.exists(), "지도교수별/ must NOT exist when pipeline stops at ingest"
