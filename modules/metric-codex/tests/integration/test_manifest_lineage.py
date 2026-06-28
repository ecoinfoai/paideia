"""T019/T020 RED — US3 manifest lineage: cross-run hash survival and purge interaction.

T019: ingest A (school-Excel + immersio) → ingest B (immersio-only, Excel removed)
  → manifest.input_hashes must still carry A's school-Excel source_id/sha,
  every codex_entry.source_id must resolve in input_hashes ∪ source_ledger,
  and after distribute the roster identity hash is present in config_ids.

T020: after a supersede-purge (combined-immersio path, US2), the purged individual
  source_id is ABSENT from BOTH codex AND input_hashes, AND check_lineage (T023)
  passes — no false LINEAGE-01 violation for a legitimately purged source.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pandas as pd
import pytest
from metric_codex.cli.main import app
from metric_codex.output.manifest import read_manifest
from metric_codex.output.paths import silver_dir
from metric_codex.output.sha256 import compute_sha256
from paideia_shared.schemas.metric_codex import CodexEntry

from tests.fixtures.scenario_a import (
    COURSE,
    KEY,
    NAME_A,
    SEMESTER,
    SID_A,
    write_school_excel,
    write_school_map,
    write_student_metrics,
)

_NOW_A = "2026-06-19T00:00:00Z"
_NOW_B = "2026-06-19T12:00:00Z"
_NOW_DIST = "2026-06-19T13:00:00Z"

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_bronze(data_root: Path) -> Path:
    """Create and return the bronze directory for the shared semester/course."""
    bronze = data_root / "bronze" / "metric-codex" / KEY
    bronze.mkdir(parents=True, exist_ok=True)
    return bronze


def _make_immersio_silver(data_root: Path) -> Path:
    """Create and return the immersio silver directory."""
    immersio = data_root / "silver" / "immersio" / KEY
    immersio.mkdir(parents=True, exist_ok=True)
    return immersio


def _make_needsmap_silver(data_root: Path) -> Path:
    """Create and return the needs-map silver directory."""
    needsmap = data_root / "silver" / "needs-map" / KEY
    needsmap.mkdir(parents=True, exist_ok=True)
    return needsmap


def _make_roster(path: Path) -> None:
    """Write a minimal advisor roster assigning SID_A to ADV_A."""
    path.write_text(
        textwrap.dedent(f"""\
            assignments:
              - student_id: "{SID_A}"
                advisor_id: "ADV_A"
                advisor_name: "김교수"
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


def _ingest(data_root: Path, *, now: str) -> int:
    return app(
        [
            "ingest",
            "--semester",
            SEMESTER,
            "--course",
            COURSE,
            "--data-root",
            str(data_root),
            "--now",
            now,
        ]
    )


def _distribute(data_root: Path, *, roster_path: Path, now: str) -> int:
    return app(
        [
            "distribute",
            "--semester",
            SEMESTER,
            "--course",
            COURSE,
            "--data-root",
            str(data_root),
            "--roster",
            str(roster_path),
            "--now",
            now,
        ]
    )


def _manifest_path(data_root: Path) -> Path:
    return silver_dir(SEMESTER, COURSE, data_root=data_root) / "manifest_metric-codex.json"


# ---------------------------------------------------------------------------
# T019 — Excel hash survives an immersio-only re-ingest
# ---------------------------------------------------------------------------


class TestManifestLineageSurvival:
    """Excel source_id/sha in input_hashes must survive an immersio-only re-ingest.

    Audit defect MC-U03: input_hashes was rebuilt from this-run results only,
    so a second run that omits the school Excel silently dropped its hash.
    """

    @pytest.fixture()
    def two_run_root(self, tmp_path: Path) -> tuple[Path, str]:
        """Run A (Excel + immersio) then run B (immersio-only); return (data_root, excel_source_id)."""
        data_root = tmp_path / "data"
        bronze = _make_bronze(data_root)
        immersio = _make_immersio_silver(data_root)

        # Write Excel + map for run A.
        excel_path = bronze / "성적출석.xlsx"
        write_school_excel(excel_path, rows=[(SID_A, NAME_A, 85, 90.5, 15)])
        write_school_map(bronze / "성적출석_map.yaml")
        write_student_metrics(immersio / "학생지표.parquet")

        # Run A: school-Excel + immersio.
        rc = _ingest(data_root, now=_NOW_A)
        assert rc == 0, f"run A ingest failed rc={rc}"

        # Capture the Excel source_id that run A registered.
        # The school_excel source_id is constructed from the relative path.
        # Read from ledger to get it exactly.
        sd = silver_dir(SEMESTER, COURSE, data_root=data_root)
        ledger_df = pd.read_parquet(sd / "source_ledger.parquet")
        school_rows = ledger_df[ledger_df["origin_module"] == "school"]
        assert len(school_rows) == 1, (
            f"precondition: run A must register exactly one school row; got {len(school_rows)}"
        )
        excel_source_id: str = school_rows.iloc[0]["source_id"]

        # Run B: remove the school Excel — immersio-only.
        excel_path.unlink()
        (bronze / "성적출석_map.yaml").unlink()
        write_student_metrics(immersio / "학생지표.parquet")  # re-write (same content)

        rc = _ingest(data_root, now=_NOW_B)
        assert rc == 0, f"run B ingest failed rc={rc}"

        return data_root, excel_source_id

    def test_excel_source_id_in_input_hashes_after_immersio_only_rerun(
        self, two_run_root: tuple[Path, str]
    ) -> None:
        """After an immersio-only re-ingest, the Excel source_id survives in input_hashes.

        This is the core MC-U03 regression test: the OLD code rebuilt input_hashes
        from this-run results, dropping A's Excel hash on run B.
        """
        data_root, excel_source_id = two_run_root
        manifest = read_manifest(_manifest_path(data_root))
        assert excel_source_id in manifest.input_hashes, (
            f"Excel source_id {excel_source_id!r} was DROPPED from input_hashes "
            f"after immersio-only re-ingest (MC-U03 regression). "
            f"input_hashes keys: {list(manifest.input_hashes)}"
        )

    def test_all_codex_source_ids_resolve_in_hashes_or_ledger(
        self, two_run_root: tuple[Path, str]
    ) -> None:
        """Every codex_entry.source_id must resolve in input_hashes ∪ source_ledger."""
        data_root, _excel_source_id = two_run_root
        sd = silver_dir(SEMESTER, COURSE, data_root=data_root)

        manifest = read_manifest(_manifest_path(data_root))
        codex_df = pd.read_parquet(sd / "codex_entry.parquet")
        ledger_df = pd.read_parquet(sd / "source_ledger.parquet")

        known_ids = set(manifest.input_hashes) | set(ledger_df["source_id"])
        unresolved = set(codex_df["source_id"]) - known_ids
        assert not unresolved, f"codex_entry source_ids not in input_hashes ∪ ledger: {unresolved}"

    def test_roster_hash_in_config_ids_after_distribute(
        self, two_run_root: tuple[Path, str]
    ) -> None:
        """After distribute, roster filename appears in manifest.config_ids (MC-U09)."""
        data_root, _excel_source_id = two_run_root
        bronze = _make_bronze(data_root)

        roster_path = bronze / "지도교수배정.yaml"
        _make_roster(roster_path)
        qs_path = bronze / "question_set.yaml"
        _make_question_set(qs_path)

        # Need generate first so distribute has student mds to copy.
        rc = app(
            [
                "generate",
                "--semester",
                SEMESTER,
                "--course",
                COURSE,
                "--data-root",
                str(data_root),
                "--question-set",
                str(qs_path),
                "--backend",
                "none",
                "--now",
                _NOW_B,
            ]
        )
        assert rc == 0, f"generate failed rc={rc}"

        rc = _distribute(data_root, roster_path=roster_path, now=_NOW_DIST)
        assert rc == 0, f"distribute failed rc={rc}"

        manifest = read_manifest(_manifest_path(data_root))
        assert roster_path.name in manifest.config_ids, (
            f"roster filename {roster_path.name!r} not found in config_ids after distribute. "
            f"config_ids keys: {list(manifest.config_ids)}"
        )
        # The hash value must equal the actual file hash.
        expected_hash = compute_sha256(roster_path)
        assert manifest.config_ids[roster_path.name] == expected_hash, (
            f"roster hash mismatch: manifest has {manifest.config_ids[roster_path.name]!r}, "
            f"expected {expected_hash!r}"
        )


# ---------------------------------------------------------------------------
# T020 — supersede×lineage interaction: purged source absent everywhere,
#         check_lineage must NOT raise a false LINEAGE-01 violation.
# ---------------------------------------------------------------------------


def _write_combined_parquet(path: Path, *, sid: str, name: str) -> None:
    """Write a minimal 진단×시험결합.parquet row for one student."""
    axis_fields: dict[str, object] = {}
    for axis in [
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    ]:
        axis_fields[f"{axis}_raw"] = 1.0
        axis_fields[f"{axis}_z"] = 0.1
        axis_fields[f"{axis}_missing"] = False

    rows = [
        {
            "student_id": sid,
            "name_kr": name,
            "on_roster": True,
            "section": "A",
            "semester": SEMESTER,
            "course_slug": COURSE,
            **axis_fields,
            "cluster_id": 1,
            "cluster_label": "표준형",
            "cluster_distance": 0.5,
            "exam_taken": True,
            "total_score": 80.0,
            "score_percent": 80.0,
            "section_percentile": 75.0,
            "cohort_percentile": 70.0,
            "z_score": 1.2,
            "chapter_correct_rates": json.dumps({"순환": 0.9}, ensure_ascii=False),
            "source_correct_rates": json.dumps({}, ensure_ascii=False),
            "difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
            "expected_difficulty_correct_rates": json.dumps({}, ensure_ascii=False),
            "item_type_correct_rates": json.dumps({}, ensure_ascii=False),
            "interest_chapters_correct_rate": None,
            "aversion_chapters_correct_rate": None,
            "prior_readiness_q5": None,
            "prior_readiness_q6": None,
            "time_pattern_q21": None,
            "time_pattern_q22": None,
            "time_pattern_q23": None,
            "interest_topics_q9": None,
            "interest_topics_q10": None,
            "interest_topics_q11": None,
            "categorical_intent_q12": None,
            "categorical_intent_q13": None,
            "진단응답": True,
            "시험응시": True,
            "needs_map_schema_version": "0.1.0",
            "immersio_phase2_schema_version": "0.1.0",
        }
    ]
    pd.DataFrame(rows).to_parquet(path)


class TestSupersedeLineageInteraction:
    """After a supersede-purge, purged source must be absent from codex AND
    input_hashes, and check_lineage must NOT fire a false violation.

    This guards the US1×US3 interaction: US2 evicts purged sources from the
    accumulated ledger; building input_hashes from that ledger correctly
    omits the purged source — so LINEAGE-01 has nothing to complain about.
    """

    _INDIVIDUAL_SOURCE_IDS = frozenset(
        {
            "immersio:학생지표",
            "needs-map:factor_scores",
            "needs-map:cluster_assignment",
        }
    )
    _COMBINED_SOURCE_ID = "immersio:진단×시험결합"

    @pytest.fixture()
    def post_supersede_root(self, tmp_path: Path) -> Path:
        """Run 1 (individual sources) then run 2 (combined supersedes). Return data_root."""
        data_root = tmp_path / "data"
        bronze = _make_bronze(data_root)
        immersio = _make_immersio_silver(data_root)
        needsmap = _make_needsmap_silver(data_root)

        write_school_excel(bronze / "성적출석.xlsx", rows=[(SID_A, NAME_A, 85, 90.5, 15)])
        write_school_map(bronze / "성적출석_map.yaml")
        write_student_metrics(immersio / "학생지표.parquet")

        from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

        axis_fields: dict[str, object] = {}
        for axis in STANDARD_AXIS_KEYS:
            axis_fields[axis] = 1.0
            axis_fields[f"{axis}_z"] = 0.1
            axis_fields[f"{axis}_missing"] = False

        factor_rows = [
            {
                "student_id": SID_A,
                "on_roster": True,
                "responded": True,
                "section": "A",
                **axis_fields,
            }
        ]
        pd.DataFrame(factor_rows).to_parquet(needsmap / "factor_scores.parquet")

        cluster_rows = [{"student_id": SID_A, "cluster_id": 1, "distance_to_centroid": 0.5}]
        pd.DataFrame(cluster_rows).to_parquet(needsmap / "cluster_assignment.parquet")
        (needsmap / "cluster_names.json").write_text(json.dumps({"1": "표준형"}), encoding="utf-8")

        # Run 1: individual sources.
        rc = _ingest(data_root, now=_NOW_A)
        assert rc == 0, f"run 1 ingest failed rc={rc}"

        # Run 2: add the combined source (supersedes individual ones).
        _write_combined_parquet(immersio / "진단×시험결합.parquet", sid=SID_A, name=NAME_A)
        rc = _ingest(data_root, now=_NOW_B)
        assert rc == 0, f"run 2 ingest failed rc={rc}"

        return data_root

    def test_purged_source_absent_from_codex(self, post_supersede_root: Path) -> None:
        """After supersede-purge, individual source_ids must not appear in the codex."""
        sd = silver_dir(SEMESTER, COURSE, data_root=post_supersede_root)
        codex_df = pd.read_parquet(sd / "codex_entry.parquet")
        still_individual = codex_df[codex_df["source_id"].isin(self._INDIVIDUAL_SOURCE_IDS)]
        assert len(still_individual) == 0, (
            f"superseded entries still in codex: {still_individual['source_id'].unique().tolist()}"
        )

    def test_purged_source_absent_from_input_hashes(self, post_supersede_root: Path) -> None:
        """After supersede-purge, individual source_ids must not appear in input_hashes.

        The ledger-based build (T021 fix) correctly excludes evicted records,
        so purged sources are absent from input_hashes.
        """
        manifest = read_manifest(_manifest_path(post_supersede_root))
        for sid in self._INDIVIDUAL_SOURCE_IDS:
            assert sid not in manifest.input_hashes, (
                f"purged source_id {sid!r} still present in input_hashes after supersede-purge; "
                f"input_hashes keys: {list(manifest.input_hashes)}"
            )

    def test_combined_source_present_in_input_hashes(self, post_supersede_root: Path) -> None:
        """After supersede, the combined source_id must be in input_hashes."""
        manifest = read_manifest(_manifest_path(post_supersede_root))
        assert self._COMBINED_SOURCE_ID in manifest.input_hashes, (
            f"combined source_id {self._COMBINED_SOURCE_ID!r} not found in input_hashes. "
            f"input_hashes keys: {list(manifest.input_hashes)}"
        )

    def test_check_lineage_no_false_violation_after_supersede(
        self, post_supersede_root: Path
    ) -> None:
        """check_lineage must NOT raise a false LINEAGE-01 for legitimately purged sources.

        After supersede-purge the codex has NO entries with individual source_ids,
        so LINEAGE-01 has nothing to check for them — the check must pass cleanly.
        """
        from metric_codex.verify.checks import check_lineage

        sd = silver_dir(SEMESTER, COURSE, data_root=post_supersede_root)
        manifest = read_manifest(_manifest_path(post_supersede_root))

        from metric_codex.store.codex import read_existing_store

        entries, records = read_existing_store(sd)

        violations = check_lineage(
            codex_entries=entries,
            input_hashes=manifest.input_hashes,
            source_records=records,
        )
        assert violations == [], (
            f"check_lineage reported false LINEAGE-01 violations after supersede-purge: "
            f"{[str(v) for v in violations]}"
        )


# ---------------------------------------------------------------------------
# T023 (true positive) — check_lineage fires on an unresolved source.
#
# Every other LINEAGE-01 test asserts the pass/empty path; without this a
# future no-op regression of check_lineage would pass silently, defeating a
# NON-NEGOTIABLE Principle V (audit trail) invariant.  Called directly because
# the full verify-gate path can't reach LINEAGE-01 with empty provenance — the
# MANIFEST check fires first on an empty input_hashes.
# ---------------------------------------------------------------------------


class TestCheckLineageTruePositive:
    """check_lineage must report a located LINEAGE-01 for an unresolved source_id."""

    @staticmethod
    def _bogus_entry() -> CodexEntry:
        """Build a minimal valid CodexEntry whose source_id resolves nowhere."""
        return CodexEntry(
            student_id=SID_A,
            semester=SEMESTER,
            cohort_year=2026,
            layer="minimal",
            entry_kind="score_total",
            key="score_total",
            value_num=85.0,
            source_id="bogus:x",
        )

    def test_unresolved_source_yields_exactly_one_lineage_violation(self) -> None:
        """A codex entry whose source_id is in neither input_hashes nor ledger fails."""
        from metric_codex.verify.checks import check_lineage

        violations = check_lineage(
            codex_entries=[self._bogus_entry()],
            input_hashes={},
            source_records=[],
        )
        assert len(violations) == 1, (
            f"expected exactly one LINEAGE-01 violation for an unresolved source; "
            f"got {[str(v) for v in violations]}"
        )
        v = violations[0]
        assert v.invariant_id == "LINEAGE-01", (
            f"expected invariant_id LINEAGE-01; got {v.invariant_id!r}"
        )
        # The offending source_id must be named in the located output (detail + message).
        assert "bogus:x" in str(v), (
            f"offending source_id 'bogus:x' not named in violation: {str(v)!r}"
        )
        assert v.detail is not None and "bogus:x" in v.detail, (
            f"offending source_id 'bogus:x' not in detail: {v.detail!r}"
        )
