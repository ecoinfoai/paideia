"""T040 — Unit tests for forward/audit.py: audit_prior.

RED phase: written before implementation.

Verifies:
- met=True when this_year_value >= prior_target.
- met=False when this_year_value < prior_target.
- Missing current baseline row → met=False with note.
- Returns dict with prior_year and results list.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from paideia_shared.schemas import BaselineSnapshotRow
from retro_mester.load.errors import InputError

from tests.fixtures.factories import write_prior_forward_yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEMESTER_PRIOR = "2025-1"
_SEMESTER_CURRENT = "2026-1"
_COURSE = "anatomy"
_CHAPTER_A = "1장 해부학 서론"
_CHAPTER_B = "2장 세포와 조직"


def _prior_yaml(
    tmp_path: Path,
    entries: list[dict],
    baseline_rows: list[dict],
    created_for_year: str = "2026-1",
) -> Path:
    """Write a prior 차년도방향.yaml fixture and return its path."""
    data = {
        "schema_version": "retro-forward/1.0",
        "semester": _SEMESTER_PRIOR,
        "course_slug": _COURSE,
        "created_for_year": created_for_year,
        "ledger": entries,
        "baseline": baseline_rows,
    }
    path = tmp_path / "prior_차년도방향.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path


def _make_ledger_entry_dict(
    entry_id: str,
    chapter: str,
    segment: str,
    baseline_value: float,
    target_value: float,
) -> dict:
    """Return a minimal ImprovementLedgerEntry serialised as a dict."""
    return {
        "entry_id": entry_id,
        "semester": _SEMESTER_PRIOR,
        "course_slug": _COURSE,
        "chapter": chapter,
        "target_cognitive_level": "미상",
        "segment": segment,
        "metric": "단원 정답률",
        "baseline_value": baseline_value,
        "target_value": target_value,
        "cluster_vocab": None,
        "measure_at": "차년도 기말",
        "created_for_year": "2026-1",
    }


def _make_baseline_snap(
    chapter: str,
    segment: str,
    correct_rate: float,
    semester: str = _SEMESTER_CURRENT,
) -> BaselineSnapshotRow:
    return BaselineSnapshotRow(
        semester=semester,
        course_slug=_COURSE,
        segment=segment,
        chapter=chapter,
        cognitive_level="전체",
        correct_rate=correct_rate,
        n=4,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuditPrior:
    """T040: audit_prior loads prior yaml and computes met/not-met."""

    def test_met_true_when_above_target(self, tmp_path: Path) -> None:
        """met=True when this_year_value >= prior_target."""
        from retro_mester.forward.audit import audit_prior

        entry_id = "entry-A"
        prior_path = _prior_yaml(
            tmp_path,
            entries=[_make_ledger_entry_dict(entry_id, _CHAPTER_A, "학령기", 0.45, 0.70)],
            baseline_rows=[],
        )
        current_baseline = [_make_baseline_snap(_CHAPTER_A, "학령기", 0.75)]

        result = audit_prior(prior_path, current_baseline)

        assert result["prior_year"] == _SEMESTER_PRIOR
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["entry_id"] == entry_id
        assert abs(r["this_year_value"] - 0.75) < 1e-9
        assert r["met"] is True

    def test_met_false_when_below_target(self, tmp_path: Path) -> None:
        """met=False when this_year_value < prior_target."""
        from retro_mester.forward.audit import audit_prior

        entry_id = "entry-B"
        prior_path = _prior_yaml(
            tmp_path,
            entries=[_make_ledger_entry_dict(entry_id, _CHAPTER_A, "학령기", 0.45, 0.70)],
            baseline_rows=[],
        )
        current_baseline = [_make_baseline_snap(_CHAPTER_A, "학령기", 0.65)]

        result = audit_prior(prior_path, current_baseline)

        r = result["results"][0]
        assert r["met"] is False
        assert abs(r["this_year_value"] - 0.65) < 1e-9

    def test_met_true_when_equal_to_target(self, tmp_path: Path) -> None:
        """met=True when this_year_value == prior_target (boundary)."""
        from retro_mester.forward.audit import audit_prior

        prior_path = _prior_yaml(
            tmp_path,
            entries=[_make_ledger_entry_dict("entry-C", _CHAPTER_A, "학령기", 0.45, 0.70)],
            baseline_rows=[],
        )
        current_baseline = [_make_baseline_snap(_CHAPTER_A, "학령기", 0.70)]

        result = audit_prior(prior_path, current_baseline)
        assert result["results"][0]["met"] is True

    def test_missing_current_row_met_false(self, tmp_path: Path) -> None:
        """Missing current baseline row → met=False with note."""
        from retro_mester.forward.audit import audit_prior

        prior_path = _prior_yaml(
            tmp_path,
            entries=[_make_ledger_entry_dict("entry-D", _CHAPTER_B, "만학도", 0.40, 0.65)],
            baseline_rows=[],
        )
        # No current baseline for CHAPTER_B/만학도
        current_baseline: list[BaselineSnapshotRow] = []

        result = audit_prior(prior_path, current_baseline)
        r = result["results"][0]
        assert r["met"] is False
        assert "note" in r  # missing row should have an explanatory note

    def test_prior_baseline_and_target_in_result(self, tmp_path: Path) -> None:
        """prior_baseline and prior_target are echoed in each result row."""
        from retro_mester.forward.audit import audit_prior

        prior_path = _prior_yaml(
            tmp_path,
            entries=[_make_ledger_entry_dict("entry-E", _CHAPTER_A, "학령기", 0.42, 0.68)],
            baseline_rows=[],
        )
        current_baseline = [_make_baseline_snap(_CHAPTER_A, "학령기", 0.70)]
        result = audit_prior(prior_path, current_baseline)
        r = result["results"][0]

        assert abs(r["prior_baseline"] - 0.42) < 1e-9
        assert abs(r["prior_target"] - 0.68) < 1e-9

    def test_multiple_entries(self, tmp_path: Path) -> None:
        """Multiple ledger entries produce multiple result rows."""
        from retro_mester.forward.audit import audit_prior

        prior_path = _prior_yaml(
            tmp_path,
            entries=[
                _make_ledger_entry_dict("e1", _CHAPTER_A, "학령기", 0.40, 0.65),
                _make_ledger_entry_dict("e2", _CHAPTER_B, "만학도", 0.35, 0.60),
            ],
            baseline_rows=[],
        )
        current_baseline = [
            _make_baseline_snap(_CHAPTER_A, "학령기", 0.70),
            _make_baseline_snap(_CHAPTER_B, "만학도", 0.55),
        ]
        result = audit_prior(prior_path, current_baseline)

        assert len(result["results"]) == 2
        met_map = {r["entry_id"]: r["met"] for r in result["results"]}
        assert met_map["e1"] is True
        assert met_map["e2"] is False


class TestAuditPriorBoundary:
    """T023: audit_prior fail-fast at the prior-year file boundary (FR-008)."""

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """A non-existent prior yaml path raises InputError naming the path."""
        from retro_mester.forward.audit import audit_prior

        missing = tmp_path / "no-such-차년도방향.yaml"
        with pytest.raises(InputError) as exc_info:
            audit_prior(missing, [])
        assert str(missing) in str(exc_info.value)

    def test_corrupt_yaml_raises_input_error(self, tmp_path: Path) -> None:
        """Malformed YAML raises InputError whose message names the path."""
        from retro_mester.forward.audit import audit_prior

        prior_path = write_prior_forward_yaml(tmp_path, corrupt=True)
        with pytest.raises(InputError) as exc_info:
            audit_prior(prior_path, [])
        assert str(prior_path) in str(exc_info.value)

    def test_non_mapping_top_level_raises_input_error(self, tmp_path: Path) -> None:
        """A YAML whose top level is a list (not a mapping) raises InputError."""
        from retro_mester.forward.audit import audit_prior

        prior_path = tmp_path / "list_차년도방향.yaml"
        prior_path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(InputError) as exc_info:
            audit_prior(prior_path, [])
        assert str(prior_path) in str(exc_info.value)

    def test_missing_required_key_raises_input_error(self, tmp_path: Path) -> None:
        """A prior yaml missing a required top-level key raises InputError."""
        from retro_mester.forward.audit import audit_prior

        prior_path = write_prior_forward_yaml(tmp_path, missing_key="semester")
        with pytest.raises(InputError) as exc_info:
            audit_prior(prior_path, [])
        assert str(prior_path) in str(exc_info.value)

    def test_extra_key_raises_input_error(self, tmp_path: Path) -> None:
        """An unexpected extra top-level key raises InputError (extra=forbid)."""
        from retro_mester.forward.audit import audit_prior

        prior_path = write_prior_forward_yaml(tmp_path)
        data = yaml.safe_load(prior_path.read_text(encoding="utf-8"))
        data["unexpected_key"] = "boom"
        prior_path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")
        with pytest.raises(InputError):
            audit_prior(prior_path, [])

    def test_healthy_prior_still_audits(self, tmp_path: Path) -> None:
        """A healthy prior yaml audits without raising (regression)."""
        from retro_mester.forward.audit import audit_prior

        prior_path = write_prior_forward_yaml(tmp_path)
        # Fixture ledger entry has segment="전체", which never matches a valid
        # BaselineSnapshotRow segment → met=False with a note, but no raise.
        result = audit_prior(prior_path, [])
        assert result["prior_year"] == "2025-1"
        assert len(result["results"]) == 1
        assert result["results"][0]["met"] is False
        assert "note" in result["results"][0]
