"""T046 RED — US3 contract tests: AdvisorRosterEntry + roster loader + summary invariant.

Tests:
  - AdvisorRosterEntry valid construction, extra=forbid, min_length on advisor_id.
  - load_roster happy path returns sorted list.
  - load_roster duplicate student_id → LocatedInputError.
  - load_roster missing 'assignments' key → LocatedInputError.
  - load_roster missing file → LocatedInputError.
  - AdvisorBundleSummary count-invariant violation raises ValidationError.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from metric_codex.errors import LocatedInputError
from paideia_shared.schemas import AdvisorBundleSummary
from paideia_shared.schemas.metric_codex import AdvisorRosterEntry
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# AdvisorRosterEntry contract
# ---------------------------------------------------------------------------


class TestAdvisorRosterEntryValid:
    def test_minimal_fields(self):
        entry = AdvisorRosterEntry(student_id="2026000001", advisor_id="ADV001")
        assert entry.student_id == "2026000001"
        assert entry.advisor_id == "ADV001"
        assert entry.advisor_name is None

    def test_with_advisor_name(self):
        entry = AdvisorRosterEntry(
            student_id="2026000002",
            advisor_id="ADV002",
            advisor_name="홍길동",
        )
        assert entry.advisor_name == "홍길동"

    def test_frozen(self):
        entry = AdvisorRosterEntry(student_id="2026000001", advisor_id="ADV001")
        with pytest.raises((TypeError, ValidationError)):
            entry.advisor_id = "OTHER"  # type: ignore[misc]

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AdvisorRosterEntry(
                student_id="2026000001",
                advisor_id="ADV001",
                unknown_field="x",
            )

    def test_invalid_student_id_too_short(self):
        with pytest.raises(ValidationError):
            AdvisorRosterEntry(student_id="202600001", advisor_id="ADV001")  # 9 digits

    def test_invalid_student_id_non_numeric(self):
        with pytest.raises(ValidationError):
            AdvisorRosterEntry(student_id="ABCDE12345", advisor_id="ADV001")

    def test_empty_advisor_id_rejected(self):
        """min_length=1 on advisor_id must reject empty string."""
        with pytest.raises(ValidationError):
            AdvisorRosterEntry(student_id="2026000001", advisor_id="")


# ---------------------------------------------------------------------------
# load_roster happy path
# ---------------------------------------------------------------------------


def _write_roster(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


class TestLoadRosterHappyPath:
    def test_returns_sorted_list(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            assignments:
              - student_id: "2026000002"
                advisor_id: "ADV_B"
                advisor_name: "이교수"
              - student_id: "2026000001"
                advisor_id: "ADV_A"
                advisor_name: "김교수"
            """,
        )
        entries = load_roster(roster_path)
        # Sorted by student_id ascending.
        assert [e.student_id for e in entries] == ["2026000001", "2026000002"]

    def test_advisor_name_optional(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            assignments:
              - student_id: "2026000001"
                advisor_id: "ADV_A"
            """,
        )
        entries = load_roster(roster_path)
        assert entries[0].advisor_name is None

    def test_single_entry(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            assignments:
              - student_id: "2026000003"
                advisor_id: "ADV_C"
                advisor_name: "박교수"
            """,
        )
        entries = load_roster(roster_path)
        assert len(entries) == 1
        assert entries[0].advisor_id == "ADV_C"


# ---------------------------------------------------------------------------
# load_roster error paths
# ---------------------------------------------------------------------------


class TestLoadRosterErrors:
    def test_missing_file_raises(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        with pytest.raises(LocatedInputError, match="not found"):
            load_roster(tmp_path / "nonexistent.yaml")

    def test_missing_assignments_key_raises(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            wrong_key:
              - student_id: "2026000001"
                advisor_id: "ADV_A"
            """,
        )
        with pytest.raises(LocatedInputError, match="assignments"):
            load_roster(roster_path)

    def test_duplicate_student_id_raises(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            assignments:
              - student_id: "2026000001"
                advisor_id: "ADV_A"
              - student_id: "2026000001"
                advisor_id: "ADV_B"
            """,
        )
        with pytest.raises(LocatedInputError, match="2026000001"):
            load_roster(roster_path)

    def test_invalid_student_id_in_file_raises(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            assignments:
              - student_id: "BAD"
                advisor_id: "ADV_A"
            """,
        )
        with pytest.raises(LocatedInputError):
            load_roster(roster_path)

    def test_assignments_not_a_list_raises(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        _write_roster(
            roster_path,
            """\
            assignments: "not a list"
            """,
        )
        with pytest.raises(LocatedInputError):
            load_roster(roster_path)

    def test_invalid_yaml_raises(self, tmp_path: Path):
        from metric_codex.distribute.roster import load_roster

        roster_path = tmp_path / "지도교수배정.yaml"
        roster_path.write_text("assignments: [\nbad yaml", encoding="utf-8")
        with pytest.raises(LocatedInputError):
            load_roster(roster_path)


# ---------------------------------------------------------------------------
# AdvisorBundleSummary count-invariant
# ---------------------------------------------------------------------------


class TestAdvisorBundleSummaryInvariant:
    def test_violating_triple_raises(self):
        """assigned_count + len(unassigned_sids) != total → ValidationError."""
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=5,
                assigned_count=3,
                unassigned_sids=["2026000001"],  # 3 + 1 = 4 ≠ 5
                advisor_count=1,
                per_advisor_counts={"ADV_A": 3},
            )

    def test_valid_triple_constructs(self):
        summary = AdvisorBundleSummary(
            total_students_with_codex=3,
            assigned_count=2,
            unassigned_sids=["2026000003"],
            advisor_count=1,
            per_advisor_counts={"ADV_A": 2},
        )
        assert summary.total_students_with_codex == 3
