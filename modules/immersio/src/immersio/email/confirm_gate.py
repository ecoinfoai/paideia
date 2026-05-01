"""Confirm gate — strict ``yes`` matching before live send (T068).

FR-C04 / clarification Q3: the operator MUST type ``yes`` (lowercase,
no surrounding whitespace) to proceed. Any other input — ``y``, ``YES``,
empty string, ``no`` — aborts. The gate has *no disable flag* so a
careless automation cannot bypass the human review step (SC-004).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import IO

from paideia_shared.schemas import EmailMessageDraft, StudentPDFBundle


class ConfirmGateAborted(Exception):
    """Raised when the operator does not type the exact ``yes`` token."""


def confirm_first_n(
    drafts_with_pdfs: Sequence[tuple[EmailMessageDraft, StudentPDFBundle]],
    *,
    sample_size: int,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Print the first ``sample_size`` rows and require exact ``yes`` to proceed.

    Args:
        drafts_with_pdfs: Pairs ``(draft, bundle)`` ready for send.
        sample_size: 1 ≤ N ≤ 10 (FR-C04 + clarification Q3 default 3).
        stdin: Optional override (test injection). Defaults to
            ``sys.stdin`` so production reads from the operator's
            terminal.
        stdout: Optional override (test injection). Defaults to
            ``sys.stdout``.

    Raises:
        ValueError: When ``sample_size`` is outside 1..10.
        ConfirmGateAborted: When the operator declines (any input other
            than ``"yes"``).
    """
    if sample_size < 1 or sample_size > 10:
        raise ValueError(
            f"confirm_first_n: sample_size must be 1 ≤ N ≤ 10 "
            f"(got {sample_size})"
        )
    out = stdout if stdout is not None else sys.stdout
    in_ = stdin if stdin is not None else sys.stdin

    print(f"[immersio email] 확인 게이트 — 첫 {min(sample_size, len(drafts_with_pdfs))} 건 표본:", file=out)
    for draft, bundle in list(drafts_with_pdfs)[:sample_size]:
        print(
            f"  학번={draft.student_id} 이름={draft.name_kr} "
            f"이메일={draft.to_header} pdf={bundle.pdf_path}",
            file=out,
        )
    print(
        "위 표본의 학번/이메일/PDF 매칭이 정확합니까? 운영자 본인 받은 편지함에서 "
        "self-test 메일을 먼저 확인하셨다면, 전체 발송을 진행하려면 'yes' 를 "
        "정확히 입력하세요 (yes 외 모든 입력은 중단):",
        file=out,
        flush=True,
    )

    answer = in_.readline()
    # Compare without rstrip — "yes\n" → "yes" only if exactly that
    answer = answer.rstrip("\r\n")
    if answer != "yes":
        raise ConfirmGateAborted(
            f"FR-C04: operator declined ({'(empty)' if answer == '' else repr(answer)})."
        )


__all__ = ["ConfirmGateAborted", "confirm_first_n"]
