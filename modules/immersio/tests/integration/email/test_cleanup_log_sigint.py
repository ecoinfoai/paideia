"""cleanup-log atomic replace under failure injection — T027 (RED).

본 모듈은 v0.1.1 신규 명령 ``immersio email-cleanup-log`` 의 핵심 안전
invariant — *원본 csv 또는 정리된 새 csv 둘 중 하나가 온전* — 을 *부분 쓰기
실패* 상황에서 검증한다 (FR-C05c · research.md R3 · spec.md Edge Cases).

검증하려는 invariant
--------------------
research.md R3 은 cleanup-log 가 `os.replace()` 를 사용한 *atomic rename* 으로
csv 를 교체한다고 명시한다. ``os.replace`` 는 같은 filesystem 내 POSIX
``rename(2)`` 에 매핑되어 kernel-level 원자성을 보장하므로, replace 호출이
*도달하기 전* 에 실패가 발생하면 원본 csv 는 *byte-identical* 로 유지된다.
본 테스트는 atomic replace 도달 전·도중 의 2 가지 실패 (SIGINT 시뮬레이션,
디스크 가득 시뮬레이션) 를 monkeypatch 로 주입하여 다음을 단언한다:

  1. 함수가 ``KeyboardInterrupt`` 또는 ``OSError`` 를 propagate 한다.
  2. 원본 csv 의 sha256 가 정리 직전 sha256 와 일치한다 (atomic replace 미도달).
  3. 백업 파일 (있다면) 의 sha256 가 정리 직전 원본 csv sha256 과 일치한다
     (백업은 replace 와 *독립적인 사본* 이므로 무영향).
  4. ``*.tmp-*`` 임시 파일은 *orphan 으로 남을 수 있음* — research.md R3 §SIGINT
     절은 orphan tmp 를 명시적으로 허용 (signal handler race 회피).

요컨대 두 시나리오 모두 원본 csv (또는 백업) 의 *불변* 을 검증한다. 임시 파일
잔존 여부는 invariant 의 일부가 아니다 (운영자가 다음 cleanup-log 실행 시 새
임시 파일 사용 — R3).

테스트 인터페이스 가정 (T028 implementer 가 align 해야 할 사항)
-----------------------------------------------------------------
``immersio.email.cleanup.cleanup_log`` 시그너처는 T025·T026 와 동일::

    def cleanup_log(
        log_csv_path: Path,
        keep_statuses: list[str],
        *,
        dry_run: bool = False,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> int:

본 테스트는 *주입 지점* 으로 ``os.replace`` 를 monkeypatch 한다 (가장 결정적).
T028 implementer 가 research.md R3 sketch 대로 ``_atomic_write_csv`` helper 안에서
``os.replace(tmp.name, target)`` 를 호출하면 본 monkeypatch 가 그 호출을 직접
가로챈다.

만약 T028 이 다른 atomic-replace 전략 (예: ``Path.rename``, ``shutil.move``) 을
택하면 본 테스트의 monkeypatch target 만 조정한다. invariant 자체 (원본 csv
sha256 무변경) 는 그대로 유효하다.

ENOSPC 시나리오는 ``os.replace`` 가 ``OSError(errno.ENOSPC, ...)`` 를 raise 하도록
monkeypatch 한다 — 실제 디스크 가득 상황을 가장 직접적으로 모사. ``fsync`` 나
``tempfile`` 내부 write 를 패치하는 방식은 T028 의 정확한 구현 세부에 의존하므로
회피.

RED 상태
--------
T027 작성 시점 ``immersio.email.cleanup`` 모듈은 존재하지 않으므로 두 테스트는
fixture 안의 deferred import 에서 ``ModuleNotFoundError`` 로 ERROR 한다.
"""

from __future__ import annotations

import errno
import hashlib
import io
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from immersio.email.log import append_dispatch_log_rows
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Deferred import — module exists only after T028.
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_log_fn():
    """Return the ``cleanup_log`` callable; fail at fixture-resolution time.

    T028 will create ``modules/immersio/src/immersio/email/cleanup.py``. Until
    then, every test errors with ``ModuleNotFoundError`` cleanly (not at
    module-collection time).
    """
    from immersio.email.cleanup import cleanup_log  # noqa: F401

    return cleanup_log


# ---------------------------------------------------------------------------
# Helpers — DispatchLogRow factory + csv state snapshot.
# ---------------------------------------------------------------------------


def _row(
    sid: str,
    *,
    status: DispatchStatus = DispatchStatus.SUCCESS,
    minute: int = 0,
    exam_name: str = "중간고사_진단",
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, minute, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<deterministic@example.ac.kr>",
        error_kind="",
        error_detail="",
        exam_name=exam_name,
        cohort=CohortLabel.ALL,
    )


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_multi_status_csv(log: Path) -> str:
    """Append 5 mixed-status rows and return the resulting sha256.

    Rows: 2 success + 1 test_dummy + 1 dry_run + 1 skipped. With
    ``--keep success,test_dummy`` this produces a non-trivial atomic-replace
    payload (3 kept, 2 removed) — exercises both the read and write paths.
    """
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.SUCCESS, minute=1),
            _row("1234567003", status=DispatchStatus.TEST_DUMMY, minute=2),
            _row("1234567004", status=DispatchStatus.DRY_RUN, minute=3),
            _row("1234567005", status=DispatchStatus.SKIPPED, minute=4),
        ],
    )
    return _sha256_of(log)


def _assert_original_csv_intact(log: Path, sha_before: str) -> None:
    """Assert the original csv is byte-identical to the pre-cleanup snapshot."""
    assert log.exists(), "원본 csv 가 사라짐 — atomic replace 가 부분적으로 진행됨 (invariant 위반)"
    assert _sha256_of(log) == sha_before, (
        "원본 csv 가 변경됨 — atomic replace 도달 전 실패였으므로 무변경이어야 함 "
        "(FR-C05c · research.md R3)"
    )


def _assert_backup_intact_if_present(log: Path, sha_before: str) -> None:
    """If a ``*.bak-*`` exists, its sha256 must equal pre-cleanup csv sha256.

    research.md R3·FR-C05b 에 따라 백업은 정리 *전* 원본의 사본이므로 atomic
    replace 의 성공·실패와 무관하게 정리 직전 sha256 와 일치해야 한다.
    """
    bak_files = list(log.parent.glob(f"{log.name}.bak-*"))
    for bak in bak_files:
        assert _sha256_of(bak) == sha_before, (
            f"백업 파일 {bak.name!r} 의 sha256 가 정리 직전 원본과 불일치 — "
            f"백업은 replace 와 독립적인 사본이어야 함 (FR-C05b)"
        )


# ---------------------------------------------------------------------------
# (a) SIGINT simulation — KeyboardInterrupt raised inside atomic-replace step.
# ---------------------------------------------------------------------------


def test_keyboard_interrupt_during_atomic_replace_preserves_csv(
    tmp_path: Path,
    cleanup_log_fn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGINT 시뮬레이션 — KeyboardInterrupt 가 atomic replace 직전에 raise.

    Monkeypatch 전략
    ----------------
    ``os.replace`` 를 monkeypatch — research.md R3 sketch 가 ``os.replace(tmp.name,
    target)`` 로 atomic rename 을 수행하므로, 이 함수가 ``KeyboardInterrupt`` 를
    raise 하면 *임시 파일은 이미 작성된 상태* 지만 *원본 csv 는 미터치* 가 보장된다
    (POSIX rename 의 원자성이 호출 자체에 도달하지 않았으므로).

    invariant 검증
    --------------
    1. ``KeyboardInterrupt`` 가 propagate (cleanup_log 가 삼키지 않음).
    2. 원본 csv sha256 == 정리 직전 sha256 (atomic replace 미도달 → 원본 불변).
    3. 백업 (있다면) sha256 == 정리 직전 원본 sha256 (FR-C05b — 독립 사본).
    4. ``*.tmp-*`` orphan 임시 파일은 *허용* (research.md R3 — signal handler
       race 회피를 위해 명시적 cleanup 미수행).
    """
    log = tmp_path / "메일_발송로그.csv"
    sha_before = _seed_multi_status_csv(log)

    # Inject KeyboardInterrupt at the atomic-replace call site.
    def _raise_sigint(src, dst, *args, **kwargs):  # noqa: ARG001
        raise KeyboardInterrupt("simulated SIGINT mid-replace")

    monkeypatch.setattr(os, "replace", _raise_sigint)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with pytest.raises(KeyboardInterrupt):
        cleanup_log_fn(
            log,
            ["success", "test_dummy"],
            dry_run=False,
            stdout=stdout,
            stderr=stderr,
        )

    # Invariant 1+2: 원본 csv 무변경 (atomic replace 미도달).
    _assert_original_csv_intact(log, sha_before)

    # Invariant 3: 백업 파일이 생성됐다면 sha256 가 정리 직전 원본과 일치.
    _assert_backup_intact_if_present(log, sha_before)

    # Invariant 4 (negative): orphan tmp 파일이 남는 것은 OK — 단언하지 않음.
    # research.md R3 가 명시적으로 orphan tmp 허용 → 본 테스트는 *원본 무변경*
    # 만 검증한다. 임시 파일 잔존 여부는 implementation detail.


# ---------------------------------------------------------------------------
# (b) ENOSPC simulation — OSError raised at atomic-replace step.
# ---------------------------------------------------------------------------


def test_enospc_during_atomic_replace_preserves_csv(
    tmp_path: Path,
    cleanup_log_fn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """디스크 가득 시뮬레이션 — ``OSError(errno.ENOSPC)`` 가 atomic replace 에서 raise.

    Monkeypatch 전략
    ----------------
    ``os.replace`` 를 monkeypatch 하여 ``OSError(errno.ENOSPC, "No space left on
    device")`` 를 raise. 실제 디스크 full 시 ``rename(2)`` 가 반환하는 errno 와
    동일 → 가장 직접적인 시뮬레이션.

    (대안: ``tempfile.NamedTemporaryFile.write`` 또는 ``os.fsync`` patch — T028
    의 정확한 호출 순서에 의존하므로 회피. ``os.replace`` 는 R3 sketch 에 명시된
    public API 이므로 패치 안정성이 가장 높다.)

    invariant 검증
    --------------
    1. ``OSError`` 가 propagate 하고 ``errno == ENOSPC``.
    2. 원본 csv sha256 == 정리 직전 sha256 (atomic replace 실패 → 원본 불변).
    3. 백업 파일 (있다면) sha256 == 정리 직전 원본 sha256 (FR-C05b).

    *원본 csv 또는 정리된 새 csv 둘 중 하나가 온전* invariant 의 후자 (정리된
    새 csv) 는 atomic replace 실패 시 성립하지 않으므로, 전자 (원본 csv 온전)
    가 성립하면 충분하다.
    """
    log = tmp_path / "메일_발송로그.csv"
    sha_before = _seed_multi_status_csv(log)

    def _raise_enospc(src, dst, *args, **kwargs):  # noqa: ARG001
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", _raise_enospc)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with pytest.raises(OSError) as exc_info:
        cleanup_log_fn(
            log,
            ["success", "test_dummy"],
            dry_run=False,
            stdout=stdout,
            stderr=stderr,
        )

    # Invariant 1: errno == ENOSPC (KeyboardInterrupt 가 아닌 OSError 인지 추가
    # 검증). T028 이 ``OSError`` 를 wrapper 예외로 감싸지 않는다고 가정.
    assert exc_info.value.errno == errno.ENOSPC, (
        f"OSError 의 errno 가 ENOSPC 이어야 함, got errno={exc_info.value.errno}"
    )

    # Invariant 2: 원본 csv 무변경.
    _assert_original_csv_intact(log, sha_before)

    # Invariant 3: 백업 파일 (있다면) 무영향.
    _assert_backup_intact_if_present(log, sha_before)
