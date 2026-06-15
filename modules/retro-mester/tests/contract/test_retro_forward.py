"""Contract tests for ImprovementLedgerEntry and BaselineSnapshotRow (M6, T010).

RED → GREEN: written before schema; ensure valid construction and
field constraints fire correctly.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import BaselineSnapshotRow, ImprovementLedgerEntry
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# ImprovementLedgerEntry helpers
# ---------------------------------------------------------------------------

def _ledger_kwargs() -> dict:
    return {
        "entry_id": "retro-2026-1-anatomy-ch8-이해",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "chapter": "8장 호흡계통",
        "target_cognitive_level": "이해",
        "segment": "만학도",
        "metric": "chapter_correct_rate",
        "baseline_value": 0.52,
        "target_value": 0.65,
        "cluster_vocab": None,
        "measure_at": "2026-2 기말",
        "created_for_year": "2026-2",
    }


# ---------------------------------------------------------------------------
# ImprovementLedgerEntry — valid construction
# ---------------------------------------------------------------------------

def test_ledger_valid_construction() -> None:
    """A fully specified ImprovementLedgerEntry is accepted."""
    entry = ImprovementLedgerEntry(**_ledger_kwargs())
    assert entry.entry_id == "retro-2026-1-anatomy-ch8-이해"
    assert entry.baseline_value == pytest.approx(0.52)
    assert entry.cluster_vocab is None


def test_ledger_with_cluster_vocab() -> None:
    """cluster_vocab may be a non-None string."""
    kw = _ledger_kwargs()
    kw["cluster_vocab"] = "고동기-저시간"
    entry = ImprovementLedgerEntry(**kw)
    assert entry.cluster_vocab == "고동기-저시간"


# ---------------------------------------------------------------------------
# ImprovementLedgerEntry — extra / frozen
# ---------------------------------------------------------------------------

def test_ledger_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields on ImprovementLedgerEntry."""
    with pytest.raises(ValidationError):
        ImprovementLedgerEntry(**_ledger_kwargs(), unknown_field="bad")


def test_ledger_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place mutation on ImprovementLedgerEntry."""
    entry = ImprovementLedgerEntry(**_ledger_kwargs())
    with pytest.raises(Exception):
        entry.target_value = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BaselineSnapshotRow helpers
# ---------------------------------------------------------------------------

def _snapshot_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "segment": "만학도",
        "chapter": "8장 호흡계통",
        "cognitive_level": "이해",
        "correct_rate": 0.61,
        "n": 15,
    }


# ---------------------------------------------------------------------------
# BaselineSnapshotRow — valid construction
# ---------------------------------------------------------------------------

def test_snapshot_valid_construction() -> None:
    """A fully specified BaselineSnapshotRow is accepted."""
    row = BaselineSnapshotRow(**_snapshot_kwargs())
    assert row.correct_rate == pytest.approx(0.61)
    assert row.n == 15


def test_snapshot_n_zero_accepted() -> None:
    """n=0 is valid (no students measured for this cell)."""
    kw = _snapshot_kwargs()
    kw["n"] = 0
    row = BaselineSnapshotRow(**kw)
    assert row.n == 0


# ---------------------------------------------------------------------------
# BaselineSnapshotRow — constraints
# ---------------------------------------------------------------------------

def test_snapshot_negative_n_rejected() -> None:
    """n < 0 raises ValidationError."""
    kw = _snapshot_kwargs()
    kw["n"] = -1
    with pytest.raises(ValidationError):
        BaselineSnapshotRow(**kw)


# ---------------------------------------------------------------------------
# BaselineSnapshotRow — extra / frozen
# ---------------------------------------------------------------------------

def test_snapshot_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields on BaselineSnapshotRow."""
    with pytest.raises(ValidationError):
        BaselineSnapshotRow(**_snapshot_kwargs(), unknown_field="bad")


def test_snapshot_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place mutation on BaselineSnapshotRow."""
    row = BaselineSnapshotRow(**_snapshot_kwargs())
    with pytest.raises(Exception):
        row.correct_rate = 0.99  # type: ignore[misc]
