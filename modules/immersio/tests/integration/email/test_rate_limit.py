"""Rate-limit timing test (T081, FR-E01 / SC-008).

Real-time measurement: ``--rate-per-min N`` causes ``send_one`` to
sleep ``60/N`` seconds *between* sends (no sleep after the last send).
For 5 sends at rate=30 → 4 inter-send gaps × 2.0s = 8.0s minimum.

To keep test runtime reasonable while still exercising the timing
path, this test uses a ``time.sleep`` monkeypatch that *records the
sleep durations* instead of actually sleeping. The 8s / 24s
real-time assertions in the spec apply to operations on production
hardware; the unit-level invariant we verify here is that sleep
durations sum correctly.
"""

from __future__ import annotations

import argparse
import io
from unittest.mock import patch

import pytest

from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(*, rate_per_min: int) -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=True,
        self_test=None,
        retry_failed=False,
        retry_skipped=False,
        rate_per_min=rate_per_min,
        cohort="all",
        confirm_sample=3,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
    )
    args._stdin = io.StringIO("yes\n")
    args._stdout = io.StringIO()
    return args


class _FastDispatcher:
    """Mocks GmailAPIDispatcher but preserves the rate-limit kwarg."""

    captured_rate: int | None = None

    def __init__(self, profile, *, rate_per_minute: int | None = None):
        type(self).captured_rate = rate_per_minute
        self._rate_per_minute = rate_per_minute

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def sleep_between_sends(self):
        # Real implementation calls time.sleep — we intercept via the
        # module-level patch on time.sleep below to record durations.
        if self._rate_per_minute is None:
            return
        import time as _time

        _time.sleep(60.0 / self._rate_per_minute)

    def send_one(self, draft, *, pdf_bytes):
        from immersio.email.sender import SendResult

        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def test_rate_per_min_30_emits_2s_sleeps(email_fixture, monkeypatch) -> None:
    """5 sends at rate=30 → 4 sleeps of 2.0s each (no sleep after last)."""
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _FastDispatcher
    )
    sleep_durations: list[float] = []
    real_sleep = lambda d: sleep_durations.append(d)
    with patch("time.sleep", real_sleep):
        rc = run_email_dispatch(_args(rate_per_min=30))
    assert rc == 0
    # 4 inter-send gaps for 5 students
    assert len(sleep_durations) == 4
    assert all(d == pytest.approx(2.0) for d in sleep_durations)
    assert sum(sleep_durations) == pytest.approx(8.0)


def test_rate_per_min_10_emits_6s_sleeps(email_fixture, monkeypatch) -> None:
    """5 sends at rate=10 → 4 sleeps of 6.0s each (sum 24s)."""
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _FastDispatcher
    )
    sleep_durations: list[float] = []
    real_sleep = lambda d: sleep_durations.append(d)
    with patch("time.sleep", real_sleep):
        rc = run_email_dispatch(_args(rate_per_min=10))
    assert rc == 0
    assert len(sleep_durations) == 4
    assert all(d == pytest.approx(6.0) for d in sleep_durations)
    assert sum(sleep_durations) == pytest.approx(24.0)


def test_rate_per_min_propagated_to_dispatcher(
    email_fixture, monkeypatch
) -> None:
    """CLI --rate-per-min plumbed into GmailAPIDispatcher kwarg."""
    _FastDispatcher.captured_rate = None
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _FastDispatcher
    )
    with patch("time.sleep"):
        rc = run_email_dispatch(_args(rate_per_min=15))
    assert rc == 0
    assert _FastDispatcher.captured_rate == 15


def test_rate_out_of_range_rejected_at_dispatcher() -> None:
    """1 ≤ N ≤ 30 enforced inside GmailAPIDispatcher.__init__."""
    from immersio.email.sender import GmailAPIDispatcher

    import yaml
    from paideia_shared.schemas import ProfessorProfile

    profile = ProfessorProfile.model_validate(
        yaml.safe_load(
            """
profile_kind: operator
profile_name: alpha-prof
sender:
  display_name: 알파교수
  email: alpha@example.ac.kr
send_account:
  email: noreply@example.ac.kr
institution:
  university_name: 알파대학교
  department_name: 알파학과
booking:
  google_calendar_url: https://calendar.google.com/calendar/u/0/appointments/abc
gmail_api:
  service_account_subject: noreply@example.ac.kr
  scopes:
    - https://www.googleapis.com/auth/gmail.send
secrets_ref:
  service_account_json_path_env: PAIDEIA_GCP_SA_JSON_PATH_ALPHA
operational_defaults:
  rate_per_minute: 20
  confirm_sample_size: 3
  attachment_max_bytes: 104857600
"""
        )
    )
    with pytest.raises(ValueError, match="1 ≤ N ≤ 30"):
        GmailAPIDispatcher(profile, rate_per_minute=0)
    with pytest.raises(ValueError, match="1 ≤ N ≤ 30"):
        GmailAPIDispatcher(profile, rate_per_minute=31)
