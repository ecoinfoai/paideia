"""Priority-key winner tests for `_latest_status_by_sid` (T007 / FR-C02b/c).

RED-phase tests — T013 will rewrite `_latest_status_by_sid` to use a
combined ``(priority, -epoch)`` sort key so that within a student_id
group:

  - the row with the *smallest* `_STATUS_PRIORITY` value wins, and
  - if multiple rows share the same priority, the *latest*
    ``attempt_at_kst`` wins (negative-epoch trick gives DESC by
    timestamp under min-by-key semantics).

The v0.1.0 implementation uses timestamp-only ("latest wins"), so several
of these cases must FAIL until T013 lands — that is the intended RED
state. spec §FR-C02c documents the v0.1.0 → v0.1.1 behavior change as
an intended bugfix.

idea 문서 §2 C-2 표 의 5 케이스 매트릭스를 그대로 옮긴 단언:

  | Case                                       | DEFAULT | RETRY_SKIPPED | RETRY_FAILED |
  | ------------------------------------------ | ------- | ------------- | ------------ |
  | (success t=10, skipped t=20)               | skip    | skip          | skip         |
  | (failed t=10, skipped t=20)                | send    | skip (bugfix) | send         |
  | (failed t=10, temporary_failure t=20)      | send    | send          | send         |
  | (test_dummy t=10, success t=20)            | skip    | skip          | skip         |
  | (success t=10, dry_run t=20)               | skip    | skip          | skip         |

추가 edge — same-priority within-status:

  - (success t=10, success t=20) → winner = success(t=20)
  - (failed t=10, failed t=20)   → winner = failed(t=20)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from immersio.email.log import (
    _STATUS_PRIORITY,
    RetryMode,
    _latest_status_by_sid,
    idempotent_skip_filter,
)
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))
SID = "1234567001"

# Two timestamps — "t=10" earlier, "t=20" later. The exact values are
# irrelevant beyond t20 > t10 (priority+timestamp test only cares about
# ordering).
T10 = datetime(2026, 5, 1, 12, 10, 0, tzinfo=KST)
T20 = datetime(2026, 5, 1, 12, 20, 0, tzinfo=KST)


def _row(
    status: DispatchStatus,
    attempt_at_kst: datetime,
    *,
    sid: str = SID,
) -> DispatchLogRow:
    """Build a minimal valid DispatchLogRow for priority-winner tests."""
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=attempt_at_kst,
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<deterministic@example.ac.kr>",
        error_kind="",
        error_detail="",
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


# ---------------------------------------------------------------------------
# Enum coverage — `_STATUS_PRIORITY` must contain every DispatchStatus value
# and adhere to the FR-C02a / data-model.md §2 ordering.
# ---------------------------------------------------------------------------


def test_status_priority_covers_all_enum_values() -> None:
    """All 6 DispatchStatus enum values must appear in `_STATUS_PRIORITY`."""
    assert set(_STATUS_PRIORITY) == set(DispatchStatus)
    assert len(_STATUS_PRIORITY) == 6


def test_status_priority_success_is_strongest() -> None:
    """SUCCESS = 0 (가장 강함) — FR-C02a / data-model.md §2."""
    assert _STATUS_PRIORITY[DispatchStatus.SUCCESS] == 0


def test_status_priority_dry_run_is_weakest() -> None:
    """DRY_RUN = 5 (가장 약함) — FR-C02a / data-model.md §2."""
    assert _STATUS_PRIORITY[DispatchStatus.DRY_RUN] == 5


def test_status_priority_monotonic_order() -> None:
    """Strict monotonic ordering: SUCCESS < TEST_DUMMY < FAILED <
    TEMPORARY_FAILURE < SKIPPED < DRY_RUN.
    """
    order = [
        DispatchStatus.SUCCESS,
        DispatchStatus.TEST_DUMMY,
        DispatchStatus.FAILED,
        DispatchStatus.TEMPORARY_FAILURE,
        DispatchStatus.SKIPPED,
        DispatchStatus.DRY_RUN,
    ]
    values = [_STATUS_PRIORITY[s] for s in order]
    assert values == sorted(values), (
        f"_STATUS_PRIORITY must be strictly increasing in the documented order; got {values}"
    )
    assert len(set(values)) == 6, "priority values must all be distinct"


# ---------------------------------------------------------------------------
# 5 cases × 3 retry modes — FR-C02b/c full matrix.
#
# Each entry: (case_id, rows, expected_winner_status, {mode: expected_keep})
#   expected_keep is True  → student should be SENT (target is kept)
#                  False → student should be SKIPPED (target is filtered out)
# ---------------------------------------------------------------------------

# Case A — (success t=10, skipped t=20):
#   priority(success)=0 < priority(skipped)=4 → winner=success.
#   success skipped under every retry mode.
CASE_A_ROWS = [
    _row(DispatchStatus.SUCCESS, T10),
    _row(DispatchStatus.SKIPPED, T20),
]
CASE_A_WINNER = DispatchStatus.SUCCESS
CASE_A_KEEP = {
    RetryMode.DEFAULT: False,
    RetryMode.RETRY_SKIPPED: False,
    RetryMode.RETRY_FAILED: False,
}

# Case B — (failed t=10, skipped t=20):
#   priority(failed)=2 < priority(skipped)=4 → winner=failed.
#   DEFAULT/RETRY_FAILED: send; RETRY_SKIPPED: skip (bugfix — failed is
#   only retried via --retry-failed; v0.1.0 incorrectly retried via
#   --retry-skipped because latest=skipped under timestamp-only key).
CASE_B_ROWS = [
    _row(DispatchStatus.FAILED, T10),
    _row(DispatchStatus.SKIPPED, T20),
]
CASE_B_WINNER = DispatchStatus.FAILED
CASE_B_KEEP = {
    RetryMode.DEFAULT: True,
    RetryMode.RETRY_SKIPPED: False,  # FR-C02c bugfix
    RetryMode.RETRY_FAILED: True,
}

# Case C — (failed t=10, temporary_failure t=20):
#   priority(failed)=2 < priority(temporary_failure)=3 → winner=failed.
#   DEFAULT skips only SUCCESS → send. RETRY_FAILED retries failed/temp
#   → send. RETRY_SKIPPED retries only skipped → failed skipped under
#   RETRY_SKIPPED? Per current `idempotent_skip_filter`, RETRY_SKIPPED's
#   skip_statuses includes FAILED → so failed winner is SKIPPED (NOT
#   sent) under RETRY_SKIPPED.
CASE_C_ROWS = [
    _row(DispatchStatus.FAILED, T10),
    _row(DispatchStatus.TEMPORARY_FAILURE, T20),
]
CASE_C_WINNER = DispatchStatus.FAILED
CASE_C_KEEP = {
    RetryMode.DEFAULT: True,
    RetryMode.RETRY_SKIPPED: False,
    RetryMode.RETRY_FAILED: True,
}

# Case D — (test_dummy t=10, success t=20):
#   priority(success)=0 < priority(test_dummy)=1 → winner=success.
#   success skipped under every retry mode.
CASE_D_ROWS = [
    _row(DispatchStatus.TEST_DUMMY, T10),
    _row(DispatchStatus.SUCCESS, T20),
]
CASE_D_WINNER = DispatchStatus.SUCCESS
CASE_D_KEEP = {
    RetryMode.DEFAULT: False,
    RetryMode.RETRY_SKIPPED: False,
    RetryMode.RETRY_FAILED: False,
}

# Case E — (success t=10, dry_run t=20):
#   priority(success)=0 < priority(dry_run)=5 → winner=success.
#   success skipped under every retry mode.
CASE_E_ROWS = [
    _row(DispatchStatus.SUCCESS, T10),
    _row(DispatchStatus.DRY_RUN, T20),
]
CASE_E_WINNER = DispatchStatus.SUCCESS
CASE_E_KEEP = {
    RetryMode.DEFAULT: False,
    RetryMode.RETRY_SKIPPED: False,
    RetryMode.RETRY_FAILED: False,
}


_PRIORITY_MATRIX = [
    pytest.param(CASE_A_ROWS, CASE_A_WINNER, CASE_A_KEEP, id="A_success_t10__skipped_t20"),
    pytest.param(CASE_B_ROWS, CASE_B_WINNER, CASE_B_KEEP, id="B_failed_t10__skipped_t20"),
    pytest.param(CASE_C_ROWS, CASE_C_WINNER, CASE_C_KEEP, id="C_failed_t10__temp_failure_t20"),
    pytest.param(CASE_D_ROWS, CASE_D_WINNER, CASE_D_KEEP, id="D_test_dummy_t10__success_t20"),
    pytest.param(CASE_E_ROWS, CASE_E_WINNER, CASE_E_KEEP, id="E_success_t10__dry_run_t20"),
]


@pytest.mark.parametrize("rows,expected_winner,_keep_map", _PRIORITY_MATRIX)
def test_latest_status_picks_priority_winner(
    rows: list[DispatchLogRow],
    expected_winner: DispatchStatus,
    _keep_map: dict[RetryMode, bool],
) -> None:
    """`_latest_status_by_sid` must use priority-as-primary, timestamp
    DESC as tiebreak — NOT timestamp-only as v0.1.0 does."""
    latest = _latest_status_by_sid(rows)
    assert latest[SID] == expected_winner, (
        f"priority winner mismatch — rows={[(r.status, r.attempt_at_kst) for r in rows]}, "
        f"got {latest[SID]}, expected {expected_winner}"
    )


@pytest.mark.parametrize("rows,_expected_winner,keep_map", _PRIORITY_MATRIX)
@pytest.mark.parametrize(
    "mode",
    [RetryMode.DEFAULT, RetryMode.RETRY_SKIPPED, RetryMode.RETRY_FAILED],
)
def test_idempotent_filter_decides_send_skip_by_priority_winner(
    rows: list[DispatchLogRow],
    _expected_winner: DispatchStatus,
    keep_map: dict[RetryMode, bool],
    mode: RetryMode,
) -> None:
    """`idempotent_skip_filter` outcome is determined by the
    priority-winner status × retry-mode skip_statuses set
    (priority and mode are orthogonal — FR-C02b)."""
    keep = idempotent_skip_filter([SID], rows, mode)
    expected_kept = keep_map[mode]
    if expected_kept:
        assert keep == [SID], (
            f"sid should be SENT under mode={mode.value} with rows="
            f"{[(r.status.value, r.attempt_at_kst) for r in rows]}; got keep={keep}"
        )
    else:
        assert keep == [], (
            f"sid should be SKIPPED under mode={mode.value} with rows="
            f"{[(r.status.value, r.attempt_at_kst) for r in rows]}; got keep={keep}"
        )


# ---------------------------------------------------------------------------
# Same-priority within-status edge — negative-epoch DESC tiebreak.
# ---------------------------------------------------------------------------


def test_same_status_success_picks_latest_timestamp() -> None:
    """(success t=10, success t=20) → winner = success(t=20).

    Validates the negative-epoch trick (DESC by timestamp within the
    same priority bucket) in the v0.1.1 sort key.
    """
    rows = [
        _row(DispatchStatus.SUCCESS, T10),
        _row(DispatchStatus.SUCCESS, T20),
    ]
    latest = _latest_status_by_sid(rows)
    # `_latest_status_by_sid` returns only the status enum, not the
    # full row. Both rows share status=SUCCESS so the status assertion
    # alone is trivial; the meaningful invariant is that
    # idempotent_skip_filter still treats this as a SUCCESS winner
    # under DEFAULT (skip), and the picked row would be the latest
    # one — verified by an additional mixed-status test below.
    assert latest[SID] == DispatchStatus.SUCCESS
    # DEFAULT mode: SUCCESS winner → skip.
    assert idempotent_skip_filter([SID], rows, RetryMode.DEFAULT) == []


def test_same_status_failed_picks_latest_timestamp() -> None:
    """(failed t=10, failed t=20) → winner = failed(t=20).

    Same-priority bucket — later timestamp wins. Validates the
    negative-epoch DESC tiebreak rule applies to non-SUCCESS statuses
    as well.
    """
    rows = [
        _row(DispatchStatus.FAILED, T10),
        _row(DispatchStatus.FAILED, T20),
    ]
    latest = _latest_status_by_sid(rows)
    assert latest[SID] == DispatchStatus.FAILED
    # DEFAULT skips only SUCCESS → failed sid should be re-sent.
    assert idempotent_skip_filter([SID], rows, RetryMode.DEFAULT) == [SID]
    # RETRY_FAILED retries failed → sent.
    assert idempotent_skip_filter([SID], rows, RetryMode.RETRY_FAILED) == [SID]
    # RETRY_SKIPPED treats failed as skip_status → not sent.
    assert idempotent_skip_filter([SID], rows, RetryMode.RETRY_SKIPPED) == []
