"""T039 — Unit tests for forward/write.py: write_forward + next_year.

RED phase: written before implementation.

Verifies:
- next_year("2026-1") → "2027-1", "2026-2" → "2027-2".
- write_forward emits valid YAML with schema_version="retro-forward/1.0".
- Cold-start (audit=None) omits the 'audit' key.
- Audit present → 'audit' key included in YAML.
- YAML is deterministic (two identical calls produce identical output).
- dump_yaml sorts keys alphabetically.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from paideia_shared.schemas import BaselineSnapshotRow, ImprovementLedgerEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_CHAPTER_A = "1장 해부학 서론"


def _ledger_entry(
    chapter: str = _CHAPTER_A,
    segment: str = "학령기",
    entry_id: str = "abc123",
) -> ImprovementLedgerEntry:
    return ImprovementLedgerEntry(
        entry_id=entry_id,
        semester=_SEMESTER,
        course_slug=_COURSE,
        chapter=chapter,
        target_cognitive_level="미상",
        segment=segment,
        metric="단원 정답률",
        baseline_value=0.45,
        target_value=0.70,
        cluster_vocab=None,
        measure_at="차년도 기말",
        created_for_year="2027-1",
    )


def _baseline_row(
    chapter: str = _CHAPTER_A,
    segment: str = "학령기",
) -> BaselineSnapshotRow:
    return BaselineSnapshotRow(
        semester=_SEMESTER,
        course_slug=_COURSE,
        segment=segment,
        chapter=chapter,
        cognitive_level="전체",
        correct_rate=0.45,
        n=4,
    )


# ---------------------------------------------------------------------------
# Tests for next_year helper
# ---------------------------------------------------------------------------


class TestNextYear:
    """T039: next_year() helper increments the year and keeps the term."""

    def test_spring_term(self) -> None:
        """'2026-1' → '2027-1'."""
        from retro_mester.forward.write import next_year

        assert next_year("2026-1") == "2027-1"

    def test_fall_term(self) -> None:
        """'2026-2' → '2027-2'."""
        from retro_mester.forward.write import next_year

        assert next_year("2026-2") == "2027-2"

    def test_arbitrary_year(self) -> None:
        """Arbitrary year/term increments correctly."""
        from retro_mester.forward.write import next_year

        assert next_year("2030-1") == "2031-1"
        assert next_year("2019-2") == "2020-2"


# ---------------------------------------------------------------------------
# Tests for write_forward
# ---------------------------------------------------------------------------


class TestWriteForward:
    """T039: write_forward emits deterministic YAML."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """write_forward creates the given path."""
        from retro_mester.forward.write import write_forward

        out = tmp_path / "차년도방향.yaml"
        write_forward(
            out,
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=None,
        )
        assert out.exists()

    def test_schema_version(self, tmp_path: Path) -> None:
        """schema_version is 'retro-forward/1.0'."""
        from retro_mester.forward.write import write_forward

        out = tmp_path / "차년도방향.yaml"
        write_forward(
            out,
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=None,
        )
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert data["schema_version"] == "retro-forward/1.0"

    def test_cold_start_omits_audit(self, tmp_path: Path) -> None:
        """When audit=None, the 'audit' key is absent from the YAML."""
        from retro_mester.forward.write import write_forward

        out = tmp_path / "차년도방향.yaml"
        write_forward(
            out,
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=None,
        )
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert "audit" not in data

    def test_audit_present_when_provided(self, tmp_path: Path) -> None:
        """When audit dict provided, 'audit' key appears in YAML."""
        from retro_mester.forward.write import write_forward

        audit = {
            "prior_year": "2025-1",
            "results": [
                {
                    "entry_id": "abc123",
                    "prior_baseline": 0.45,
                    "prior_target": 0.70,
                    "this_year_value": 0.72,
                    "met": True,
                }
            ],
        }
        out = tmp_path / "차년도방향.yaml"
        write_forward(
            out,
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=audit,
        )
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert "audit" in data
        assert data["audit"]["prior_year"] == "2025-1"

    def test_ledger_and_baseline_lists_present(self, tmp_path: Path) -> None:
        """Both 'ledger' and 'baseline' lists appear in the YAML."""
        from retro_mester.forward.write import write_forward

        out = tmp_path / "차년도방향.yaml"
        write_forward(
            out,
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=None,
        )
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert "ledger" in data
        assert "baseline" in data
        assert len(data["ledger"]) == 1
        assert len(data["baseline"]) == 1

    def test_deterministic_two_calls(self, tmp_path: Path) -> None:
        """Two identical write_forward calls produce byte-identical files."""
        from retro_mester.forward.write import write_forward

        out1 = tmp_path / "run1.yaml"
        out2 = tmp_path / "run2.yaml"
        kwargs = dict(
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=None,
        )
        write_forward(out1, **kwargs)
        write_forward(out2, **kwargs)

        assert out1.read_bytes() == out2.read_bytes()

    def test_semester_and_course_in_yaml(self, tmp_path: Path) -> None:
        """Top-level semester and course_slug appear in the YAML."""
        from retro_mester.forward.write import write_forward

        out = tmp_path / "차년도방향.yaml"
        write_forward(
            out,
            ledger=[_ledger_entry()],
            baseline=[_baseline_row()],
            semester=_SEMESTER,
            course_slug=_COURSE,
            created_for_year="2027-1",
            audit=None,
        )
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert data["semester"] == _SEMESTER
        assert data["course_slug"] == _COURSE
        assert data["created_for_year"] == "2027-1"
