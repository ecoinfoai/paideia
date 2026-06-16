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

from paideia_shared.schemas import EmailMessageDraft, PreSendSummary, StudentPDFBundle


class ConfirmGateAborted(Exception):  # noqa: N818  (intentional control-flow exception name, not an Error)
    """Raised when the operator does not type the exact ``yes`` token."""


def confirm_first_n(
    drafts_with_pdfs: Sequence[tuple[EmailMessageDraft, StudentPDFBundle]],
    *,
    sample_size: int = 3,
    summary: PreSendSummary | None = None,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Print the first ``sample_size`` rows and require exact ``yes`` to proceed.

    Args:
        drafts_with_pdfs: Pairs ``(draft, bundle)`` ready for send.
        sample_size: 1 ≤ N ≤ 10 (FR-C04 + clarification Q3 default 3).
        summary: v0.1.1 pre-send summary (self-test vs production banner).
            ``None`` (default) preserves v0.1.0 output exactly.
            When provided, ``is_self_test=True`` emits the self-test
            banner (T018); otherwise the production 4-bucket count +
            optional 학번 명단 (cap 3) banner is emitted (T023).
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
        raise ValueError(f"confirm_first_n: sample_size must be 1 ≤ N ≤ 10 (got {sample_size})")
    out = stdout if stdout is not None else sys.stdout
    in_ = stdin if stdin is not None else sys.stdin

    sample_n = min(sample_size, len(drafts_with_pdfs))

    if summary is not None and summary.is_self_test:
        # v0.1.1 self-test branch (T018) — contracts/confirm_gate_output.md §4.
        # 강조 라인 2 줄 + 3-bucket 카운트 줄 + 표본 prefix/suffix 변경.
        print("[immersio email] 확인 게이트", file=out)
        print(
            "*** 주의: 현재 본인 테스트(SELF-TEST) 모드입니다. 학생 메일함 도달 0건. ***",
            file=out,
        )
        print(
            f"*** 본인({summary.operator_email}) 메일함으로만 발송됩니다. ***",
            file=out,
        )
        print(
            f"  본인 발송 예정: {summary.sendable_count}건 / "
            f"코호트 범위 밖: {summary.cohort_outside_count}건 / "
            f"합계: {summary.total_targets}건",
            file=out,
        )
        print(f"첫 {sample_n} 건 표본 (수신자=본인):", file=out)
        for draft, _bundle in list(drafts_with_pdfs)[:sample_size]:
            print(
                f"  학번={draft.student_id} 이름={draft.name_kr} "
                f"이메일={draft.to_header} (수신자={summary.operator_email})",
                file=out,
            )
    elif summary is not None:
        # v0.1.1 production branch (T023) — contracts/confirm_gate_output.md §3.
        # 4-bucket 카운트 줄 + (skip > 0 일 때) 학번 명단 줄 cap 3 + v0.1.0 표본 형식.
        print("[immersio email] 확인 게이트", file=out)
        print(
            f"  발송 예정: {summary.sendable_count}건 / "
            f"이미 발송됨(skip): {len(summary.idempotent_skipped_sids)}건 / "
            f"코호트 범위 밖: {summary.cohort_outside_count}건 / "
            f"합계: {summary.total_targets}건",
            file=out,
        )
        if len(summary.idempotent_skipped_sids) > 0:
            first_three = summary.idempotent_skipped_sids[:3]
            print(
                f"  이미 발송된 첫 3 학번: {', '.join(first_three)}",
                file=out,
            )
        print(f"첫 {sample_n} 건 표본:", file=out)
        for draft, bundle in list(drafts_with_pdfs)[:sample_size]:
            print(
                f"  학번={draft.student_id} 이름={draft.name_kr} "
                f"이메일={draft.to_header} pdf={bundle.pdf_path}",
                file=out,
            )
    else:
        # v0.1.0 backward-compat (summary is None) — preserve exactly.
        print(
            f"[immersio email] 확인 게이트 — 첫 {sample_n} 건 표본:",
            file=out,
        )
        for draft, bundle in list(drafts_with_pdfs)[:sample_size]:
            print(
                f"  학번={draft.student_id} 이름={draft.name_kr} "
                f"이메일={draft.to_header} pdf={bundle.pdf_path}",
                file=out,
            )
    print(
        "위 표본의 (학번, 이름, 이메일, PDF) 매칭이 정확합니까? "
        "이 시점 이전에는 어느 메일함에도 발송되지 않았습니다 — "
        "'yes' 입력 직후 발송이 시작됩니다. "
        "진행하려면 'yes' 를 정확히 입력하세요 (yes 외 모든 입력은 중단):",
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
