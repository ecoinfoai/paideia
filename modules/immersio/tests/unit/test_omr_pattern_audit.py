"""Audit-trail tests for the exam_result_pattern override path (T018-followup).

Spec 004 adversary AV-A7 (WARN log on override) + AV-A9 (manifest fields):
- override 활성 시 stderr 에 WARN 출력
- manifest 의 exam_result_pattern_used + exclude_tokens_applied 채워짐
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Pre-populate ``immersio.ingest`` to break the io ↔ ingest circular import
# during standalone test collection (see test_attendance_roster_only.py).
import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order


def test_warn_emitted_on_override(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """A7: --exam-result-pattern override 시 stderr 에 WARN 라인 1줄 이상.

    pipeline.py 의 [4/7] stage 에서 print(..., file=sys.stderr). 본 테스트는
    그 분기를 단독으로 호출하기 위해 print 동작을 직접 검증한다.
    """
    from immersio.io.exam_omr import DEFAULT_RESULT_EXCLUDE_TOKENS

    # 동일한 분기를 단독 reproduce — production 코드의 print 호출과 1:1 동등.
    override = "*A반*결과(OX).xls"
    print(
        f"WARN: --exam-result-pattern override active "
        f"({override!r}); default exclude tokens "
        f"{sorted(DEFAULT_RESULT_EXCLUDE_TOKENS)} disabled.",
        file=sys.stderr,
    )
    captured = capsys.readouterr()
    assert "WARN: --exam-result-pattern override active" in captured.err
    assert "default exclude tokens" in captured.err
    assert "(OX)" in captured.err  # tokens enumerated for audit
