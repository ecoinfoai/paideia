"""PreSendSummary — confirm-gate aggregate context (spec 007, FR-C04).

Pipeline 가 ``confirm_first_n`` 호출 *직전* 에 채워서 keyword 인자로 전달하는
4-bucket 집계 객체. confirm gate 출력의 카운트 줄·skip 명단 줄·self-test
강조 라인의 *유일한 source-of-truth* (FR-C04 — single SoT).

v0.1.0 모델 8종은 변경하지 않으며 (FR-C06a/b/c), 본 모델만 신규 추가한다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

_STUDENT_ID_RE = re.compile(r"^\d{10}$")


class PreSendSummary(BaseModel):
    """Aggregate context passed to confirm_gate (FR-C04 — single SoT).

    Attributes:
        sendable_count: confirm_gate 이후 SMTP 호출될 건수. self-test 모드에서는
            본인 발송 건수 (cohort 좁힘 후 첫 N 건).
        idempotent_skipped_sids: priority+retry-mode 로 skip 된 학번, ASC
            사전 정렬 (FR-C04b — 첫 3 건 표시).
        cohort_outside_count: roster 에 있으나 발송 대상에서 제외된 모든 학생
            (cohort 좁힘 + 이메일/PDF 매핑 부재 합산 — 단일 버킷, FR-C04a).
        total_targets: roster 전체 인원 (시험 응시자 전수).
        is_self_test: ``--self-test`` 활성 여부. True 시 confirm_gate 가
            강조 라인 2 줄 출력 (FR-C04d).
        operator_email: ``is_self_test=True`` 시 표시할 운영자 이메일.
            False 시 None.

    Invariants (enforced via ``@model_validator(mode="after")``):
        1. sendable + len(skipped) + outside == total_targets  (FR-C04a)
        2. idempotent_skipped_sids == sorted(idempotent_skipped_sids)  (FR-C04b · Q5)
        3. is_self_test XOR (operator_email is None)
        4. each sid matches ``^\\d{10}$`` (DispatchLogRow.student_id 동일 정책)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sendable_count: int = Field(ge=0)
    idempotent_skipped_sids: list[str]
    cohort_outside_count: int = Field(ge=0)
    total_targets: int = Field(ge=0)
    is_self_test: bool
    operator_email: EmailStr | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> PreSendSummary:
        if (
            self.sendable_count + len(self.idempotent_skipped_sids) + self.cohort_outside_count
            != self.total_targets
        ):
            raise ValueError(
                f"PreSendSummary bucket sum mismatch: "
                f"sendable({self.sendable_count}) + "
                f"skipped({len(self.idempotent_skipped_sids)}) + "
                f"outside({self.cohort_outside_count}) != "
                f"total({self.total_targets})"
            )
        if self.idempotent_skipped_sids != sorted(self.idempotent_skipped_sids):
            raise ValueError("PreSendSummary.idempotent_skipped_sids must be ASC sorted (FR-C04b)")
        for sid in self.idempotent_skipped_sids:
            if not _STUDENT_ID_RE.fullmatch(sid):
                raise ValueError(
                    f"PreSendSummary.idempotent_skipped_sids: {sid!r} must match ^\\d{{10}}$"
                )
        if self.is_self_test != (self.operator_email is not None):
            raise ValueError(
                "PreSendSummary: is_self_test must XOR with operator_email "
                "(True ↔ operator_email present, False ↔ operator_email is None)"
            )
        return self


__all__ = ["PreSendSummary"]
