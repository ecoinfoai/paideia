"""PreSendSummary contract test (T003 — spec 007 immersio/email-v0.1.1).

FR-C04 의 4 invariant 위반 시 ``ValidationError`` 가 발생함을 단언하고,
정상 케이스에서 ``model_dump_json`` → ``model_validate_json`` round-trip 이
byte-identical 함을 검증한다.

Invariants (PreSendSummary._check_invariants 참조):
    1. sendable_count + len(skipped) + cohort_outside_count == total_targets
    2. idempotent_skipped_sids == sorted(idempotent_skipped_sids)
    3. is_self_test XOR (operator_email is None)
    4. each sid matches ``^\\d{10}$``
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paideia_shared.schemas import PreSendSummary

# ---------------------------------------------------------------------------
# Happy-path fixtures (module-level for reuse in roundtrip + violation tests)
# ---------------------------------------------------------------------------

_VALID_PRODUCTION_KWARGS: dict[str, object] = {
    "sendable_count": 10,
    "idempotent_skipped_sids": ["1000000001", "1000000002"],
    "cohort_outside_count": 3,
    "total_targets": 15,  # 10 + 2 + 3 == 15
    "is_self_test": False,
    "operator_email": None,
}

_VALID_SELF_TEST_KWARGS: dict[str, object] = {
    "sendable_count": 1,
    "idempotent_skipped_sids": [],
    "cohort_outside_count": 49,
    "total_targets": 50,  # 1 + 0 + 49 == 50
    "is_self_test": True,
    "operator_email": "operator@example.ac.kr",
}


# ---------------------------------------------------------------------------
# Invariant 1 — bucket sum mismatch (FR-C04a)
# ---------------------------------------------------------------------------


def test_pre_send_summary_raises_on_bucket_sum_mismatch() -> None:
    """sendable + len(skipped) + outside != total → ValidationError.

    10 + 2 + 5 == 17 ≠ 20 (total_targets) 이므로 거부되어야 한다.
    """
    with pytest.raises(ValidationError) as excinfo:
        PreSendSummary(
            sendable_count=10,
            idempotent_skipped_sids=["1000000001", "1000000002"],
            cohort_outside_count=5,
            total_targets=20,
            is_self_test=False,
            operator_email=None,
        )
    assert "bucket sum mismatch" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Invariant 2 — unsorted sids (FR-C04b · Q5)
# ---------------------------------------------------------------------------


def test_pre_send_summary_raises_on_unsorted_sids() -> None:
    """idempotent_skipped_sids 가 ASC 정렬되지 않으면 거부되어야 한다."""
    with pytest.raises(ValidationError) as excinfo:
        PreSendSummary(
            sendable_count=10,
            idempotent_skipped_sids=["1000000002", "1000000001"],
            cohort_outside_count=3,
            total_targets=15,  # bucket math OK; only sort 위반
            is_self_test=False,
            operator_email=None,
        )
    assert "ASC sorted" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Invariant 3 — is_self_test XOR operator_email
# ---------------------------------------------------------------------------


def test_pre_send_summary_raises_on_self_test_true_without_operator_email() -> None:
    """is_self_test=True 인데 operator_email 가 None 이면 거부."""
    with pytest.raises(ValidationError) as excinfo:
        PreSendSummary(
            sendable_count=1,
            idempotent_skipped_sids=[],
            cohort_outside_count=49,
            total_targets=50,
            is_self_test=True,
            operator_email=None,
        )
    assert "XOR" in str(excinfo.value)


def test_pre_send_summary_raises_on_self_test_false_with_operator_email() -> None:
    """is_self_test=False 인데 operator_email 가 주어지면 거부."""
    with pytest.raises(ValidationError) as excinfo:
        PreSendSummary(
            sendable_count=10,
            idempotent_skipped_sids=["1000000001", "1000000002"],
            cohort_outside_count=3,
            total_targets=15,
            is_self_test=False,
            operator_email="op@example.ac.kr",  # ALLOW_HARDCODING: RFC 2606 example domain (synthetic operator placeholder)
        )
    assert "XOR" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Invariant 4 — student id regex (^\d{10}$)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_sid",
    [
        "123",  # too short
        "abcd123456",  # non-digit chars
        "12345678901",  # 11 digits — too long
    ],
)
def test_pre_send_summary_raises_on_invalid_sid_regex(bad_sid: str) -> None:
    """idempotent_skipped_sids 의 각 sid 는 ``^\\d{10}$`` 매칭 필수."""
    with pytest.raises(ValidationError) as excinfo:
        # bucket math: sendable + 1 + outside == total
        PreSendSummary(
            sendable_count=10,
            idempotent_skipped_sids=[bad_sid],
            cohort_outside_count=4,
            total_targets=15,
            is_self_test=False,
            operator_email=None,
        )
    # error 메시지에 sid 가 반영되는지 (or "match" keyword) 확인
    msg = str(excinfo.value)
    assert "match" in msg or bad_sid in msg


# ---------------------------------------------------------------------------
# Roundtrip — model_dump_json → model_validate_json byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        _VALID_PRODUCTION_KWARGS,
        _VALID_SELF_TEST_KWARGS,
    ],
    ids=["production", "self_test"],
)
def test_pre_send_summary_roundtrip_byte_identical(
    kwargs: dict[str, object],
) -> None:
    """model_dump_json → model_validate_json 후 재dump 가 byte-identical.

    serialize/deserialize 가 손실 없이 동일 표현으로 복원됨을 검증한다.
    """
    original = PreSendSummary(**kwargs)  # type: ignore[arg-type]
    json_first = original.model_dump_json()
    restored = PreSendSummary.model_validate_json(json_first)
    json_second = restored.model_dump_json()
    assert json_first == json_second
    assert restored == original
