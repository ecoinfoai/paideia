"""cleanup_log --keep validation 5 시나리오 — T025 (RED).

본 모듈은 v0.1.1 신규 명령 ``immersio email-cleanup-log`` 의 핵심 검증 로직
``immersio.email.cleanup.cleanup_log`` 의 단위 테스트다. T028 에서 ``cleanup.py`` 가
구현되면 GREEN 으로 전환된다.

테스트 인터페이스 가정 (T028 implementer 가 align 해야 할 사항)
-----------------------------------------------------------------
계약 문서 ``specs/007-immersio-email-v0-1-1/contracts/cli_email_cleanup_log.md``
§3·§5.1·§5.2 와 ``research.md`` R3·R4 를 근거로 다음 시그너처를 가정한다::

    def cleanup_log(
        log_csv_path: Path,
        keep_statuses: list[str],   # raw 토큰 — 함수 내부에서 enum 검증
        *,
        dry_run: bool = False,
        stdout: IO[str] | None = None,  # default sys.stdout
        stderr: IO[str] | None = None,  # default sys.stderr
    ) -> int:                       # 정상 완료 시 0

semantics:
  * unknown status (typo `succes` 또는 빈 토큰) → ``ValueError`` (또는
    ``ValidationError`` subclass) raise. CLI 핸들러가 exit 3 으로 매핑.
  * 실 모드 0 데이터행 → ``ValueError`` (별도 subclass 가능) raise.
    CLI 핸들러가 exit 4 으로 매핑.
  * dry-run 0 데이터행 → 정상 stdout 출력, return 0.

만약 T028 이 다른 시그너처 (예: ``argparse.Namespace`` 인자 / 별도 exception
class 이름) 를 택하면 본 테스트를 그에 맞춰 조정한다. 본 모듈의 검증 목적은
*행위* (lock 미획득, 백업 미생성, csv 무변경, stderr 한글 메시지 포함, return /
raise) 이며, 시그너처 자체는 결정적이지 않다.

RED 상태
--------
T025 작성 시점에 ``immersio.email.cleanup`` 모듈은 존재하지 않는다. 본 파일은
collection-time ImportError 를 피하기 위해 *deferred import* 패턴 (fixture 안에서
``from immersio.email.cleanup import cleanup_log``) 을 사용한다. T028 완료 전까지
모든 5 테스트가 ``ModuleNotFoundError`` 또는 ``AttributeError`` 로 FAIL 한다.
"""

from __future__ import annotations

import hashlib
import io
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
# Deferred import fixture — keeps test file discoverable before T028 lands.
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_log_fn():
    """Return the ``cleanup_log`` callable; fail at fixture-resolution time.

    T028 will create ``modules/immersio/src/immersio/email/cleanup.py`` with a
    public ``cleanup_log`` function. Until then, every test fails with
    ``ModuleNotFoundError`` cleanly (not at module-collection time).
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


def _no_lock_or_backup_artifacts(csv_path: Path) -> None:
    """Assert that no stray lock or .bak-* sibling files exist next to csv.

    cleanup-log (post-unification) locks the csv path itself, NOT a
    separate ``.dispatch.lock`` file — so the latter should never be
    created. Validation-failure paths additionally must not produce
    backup or temp artifacts.
    """
    parent = csv_path.parent
    # No .dispatch.lock sibling — cleanup-log no longer uses this path;
    # if it exists, an older / divergent code path is leaking artifacts.
    assert not (parent / ".dispatch.lock").exists(), (
        "lock-target divergence: .dispatch.lock should not exist "
        "(cleanup-log locks the csv path itself, matching email --send)"
    )
    # No backup files
    bak_files = list(parent.glob(f"{csv_path.name}.bak-*"))
    assert not bak_files, (
        f"FR-C05a-1 violation: backup file(s) created during validation failure: {bak_files}"
    )
    # No temp files
    tmp_files = list(parent.glob(f"{csv_path.name}.tmp-*"))
    assert not tmp_files, (
        f"FR-C05a-1 violation: temp file(s) leaked during validation failure: {tmp_files}"
    )


# ---------------------------------------------------------------------------
# (a) unknown status `--keep succes,success` → exit 3 (ValidationError)
# ---------------------------------------------------------------------------


def test_unknown_status_typo_raises_validation_error(tmp_path: Path, cleanup_log_fn) -> None:
    """typo `succes` 가 섞이면 ValueError (exit 3 매핑) — FR-C05a-1 / §5.1."""
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.FAILED, minute=1),
        ],
    )
    sha_before = _sha256_of(log)

    stderr = io.StringIO()
    with pytest.raises(ValueError) as exc_info:
        cleanup_log_fn(
            log,
            ["succes", "success"],  # typo: missing 's'
            dry_run=False,
            stderr=stderr,
        )

    # stderr 또는 예외 메시지에 한글 안내가 포함되어야 함 (§5.1).
    combined = stderr.getvalue() + str(exc_info.value)
    assert "succes" in combined, "에러 메시지에 invalid 토큰 `succes` 가 명시되어야 함 (§5.1)"
    # "지원되지 않는 status" 또는 "유효한 값" 한글 안내가 어딘가에 포함
    assert ("지원되지 않는 status" in combined) or ("유효한 값" in combined), (
        f"Korean status validation message expected in stderr/exc, got: {combined!r}"
    )

    # 부수 효과 없음
    _no_lock_or_backup_artifacts(log)
    assert _sha256_of(log) == sha_before, "csv 가 변경됨 (validation 전이어야 함)"


# ---------------------------------------------------------------------------
# (b) empty token `--keep success,,test_dummy` → exit 3 (ValidationError)
# ---------------------------------------------------------------------------


def test_empty_token_raises_validation_error(tmp_path: Path, cleanup_log_fn) -> None:
    """빈 토큰 (`,,`) 이 섞이면 ValueError (exit 3 매핑) — FR-C05a-1 / §2."""
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.TEST_DUMMY, minute=1),
        ],
    )
    sha_before = _sha256_of(log)

    stderr = io.StringIO()
    with pytest.raises(ValueError):
        cleanup_log_fn(
            log,
            ["success", "", "test_dummy"],  # 빈 토큰 가운데
            dry_run=False,
            stderr=stderr,
        )

    # 부수 효과 없음
    _no_lock_or_backup_artifacts(log)
    assert _sha256_of(log) == sha_before, "csv 가 변경됨 (validation 전이어야 함)"


# ---------------------------------------------------------------------------
# (c) result 0 data rows (csv has only dry_run + --keep success) → exit 4
# ---------------------------------------------------------------------------


def test_empty_result_abort_in_real_mode(tmp_path: Path, cleanup_log_fn) -> None:
    """csv 에 dry_run 만 + `--keep success` 실 모드 → ValueError (exit 4) — §5.2.

    백업·임시 파일 미생성, 원본 csv sha256 무변경.
    """
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.DRY_RUN),
            _row("1234567002", status=DispatchStatus.DRY_RUN, minute=1),
        ],
    )
    sha_before = _sha256_of(log)

    stderr = io.StringIO()
    with pytest.raises(ValueError) as exc_info:
        cleanup_log_fn(
            log,
            ["success"],
            dry_run=False,
            stderr=stderr,
        )

    combined = stderr.getvalue() + str(exc_info.value)
    # §5.2 한글 메시지
    assert ("0 데이터행" in combined) or ("정리 결과가 0" in combined), (
        f"empty-result Korean abort message expected, got: {combined!r}"
    )

    # 부수 효과 없음 (백업·임시 파일·csv 변경 없음)
    _no_lock_or_backup_artifacts(log)
    assert _sha256_of(log) == sha_before, "csv 가 변경됨 (abort 후 무변경이어야)"


# ---------------------------------------------------------------------------
# (d) same 0-row scenario but --dry-run mode → exit 0 (normal preview)
# ---------------------------------------------------------------------------


def test_empty_result_dry_run_is_normal(tmp_path: Path, cleanup_log_fn) -> None:
    """csv 에 dry_run 만 + `--keep success` + dry-run → 정상 (FR-C05a-2 후단).

    빈 미리보기 + 0-건 분포 보고를 stdout 으로 출력하고 return 0.
    csv 와 lock 모두 미터치.
    """
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.DRY_RUN),
            _row("1234567002", status=DispatchStatus.DRY_RUN, minute=1),
        ],
    )
    sha_before = _sha256_of(log)

    stdout = io.StringIO()
    stderr = io.StringIO()
    result = cleanup_log_fn(
        log,
        ["success"],
        dry_run=True,
        stdout=stdout,
        stderr=stderr,
    )

    # 정상 종료 (return 0 또는 None — 허용 범위)
    assert result in (0, None), f"dry-run 정상 종료 시 return 0 (또는 None) 기대, got {result!r}"
    out = stdout.getvalue()
    # §4.2 — dry-run 미리보기 헤더 + 0 데이터행 보고
    assert "dry-run" in out or "미리보기" in out, f"stdout 에 dry-run/미리보기 안내 없음: {out!r}"
    assert "0 데이터행" in out or "(총 0" in out, f"stdout 에 0 데이터행 미리보기 없음: {out!r}"
    # 분포 보고가 0 건이라도 출력
    assert "성공(success)" in out or "정리 결과 분포" in out, (
        f"stdout 에 status 분포 보고 없음: {out!r}"
    )

    # 부수 효과 없음 (dry-run 은 lock 도 잡지 않음)
    _no_lock_or_backup_artifacts(log)
    assert _sha256_of(log) == sha_before, "dry-run 인데 csv 가 변경됨"


# ---------------------------------------------------------------------------
# (e) valid --keep + ≥1 matching row → normal proceed
# ---------------------------------------------------------------------------


def test_valid_keep_with_matching_rows_succeeds(tmp_path: Path, cleanup_log_fn) -> None:
    """유효 `--keep` + ≥1 매칭 행 → 정상 진행 (실 모드).

    백업 파일 생성 (.bak-<unix_ts>), atomic replace 적용 (csv 새 내용).
    """
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.TEST_DUMMY, minute=1),
            _row("1234567003", status=DispatchStatus.FAILED, minute=2),
            _row("1234567004", status=DispatchStatus.DRY_RUN, minute=3),
        ],
    )
    sha_before = _sha256_of(log)

    stdout = io.StringIO()
    result = cleanup_log_fn(
        log,
        ["success", "test_dummy"],
        dry_run=False,
        stdout=stdout,
    )

    # 정상 종료
    assert result in (0, None), f"정상 완료 시 return 0 (또는 None) 기대, got {result!r}"

    # 백업 파일이 csv 옆에 생성됨 (`*.bak-<unix_ts>` 패턴)
    bak_files = list(log.parent.glob(f"{log.name}.bak-*"))
    assert len(bak_files) == 1, f"백업 파일 1개 기대 (*.bak-<unix_ts>), got: {bak_files}"
    # 백업의 sha256 == 정리 직전 원본 sha256
    assert _sha256_of(bak_files[0]) == sha_before, (
        "백업 파일의 sha256 가 정리 직전 원본과 일치해야 함 (FR-C05b)"
    )

    # 원본 csv 는 정리되어 변경됨 (success + test_dummy 만 남음)
    assert _sha256_of(log) != sha_before, (
        "정리 후 원본 csv 가 새로운 내용으로 atomic replace 되어야 함"
    )

    # stdout 에 한글 분포 보고
    out = stdout.getvalue()
    assert "성공(success)" in out, f"stdout 에 한글 분포 보고 없음: {out!r}"
    assert "제거(removed)" in out, f"stdout 에 '제거(removed)' 분리 라벨 없음: {out!r}"
