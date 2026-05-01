"""Phase E — MIME draft composition (T044).

Builds an ``EmailMessageDraft`` and an ``email.message.EmailMessage``
ready for either dry-run .eml writing (Phase 3 / US1) or live Gmail
API send (Phase 4+). Determinism is locked in:

  - Date: KST 12:00 on ``sent_date`` (ADR-008 / R2)
  - Message-ID: ``<sid.sent_date.course.semester@send_account_domain>``
  - MIME boundary: ``boundary-{student_id}-{sent_date}``
  - Header insertion order is fixed (FR-B07 / contracts/email_mime_format.md)

The body template ``EMAIL_BODY_TEMPLATE_KO`` carries only variable
placeholders (no student/professor identifiers — FR-G06 / ADR-009
allowed exception).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from email.header import Header
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, formataddr

from paideia_shared.schemas import (
    DispatchMode,
    EmailMappingEntry,
    EmailMessageDraft,
    ProfessorProfile,
    StudentPDFBundle,
    TestProfile,
)

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Body template (FR-G06 explicit allowance — variable placeholders only,
# no student/professor identifiers — ADR-009 exception #3).
# ---------------------------------------------------------------------------

EMAIL_BODY_TEMPLATE_KO = """안녕하세요 {university_name} {department_name} {sender_name} 교수입니다. 여러분이 얼마 전에 치른 {exam_name}의 결과를 이메일로 전달합니다.
첨부파일 내용을 확인하시고, 자신의 학습 방식이나 기타 궁금한 점은 상담을 통해 함께 고민해 봅시다. 상담이 필요한 학생은 아래 구글 캘린더 링크를 통해 상담 예약을 만들어주세요.
만약 상담예약을 넣었는데 일정을 바꿔야 할 일이 있다면, 다른 학생이 그 시간대를 사용할 수 있도록 꼭 상담예약을 수정해주세요(구글캘린더 링크 접속해서 수정/변경 가능합니다).

{google_calendar_url}

{sent_date_kr}

{sender_name} 교수
"""


_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


def _format_sent_date_kr(sent_date: date) -> str:
    """Format ``sent_date`` as ``YYYY년 M월 D일``."""
    return f"{sent_date.year}년 {sent_date.month}월 {sent_date.day}일"


def _build_subject(course_name_kr: str, exam_name: str, name_kr: str, sid: str) -> str:
    """Construct the Subject line in plain UTF-8 (RFC 2047 happens later)."""
    return f"[{course_name_kr}] {exam_name} 결과 보고서 — {name_kr}({sid})"


def _build_body(
    profile: ProfessorProfile | TestProfile,
    *,
    exam_name: str,
    sent_date: date,
) -> str:
    """Substitute the 6 body variables and assert no placeholder leaks (FR-G06)."""
    body = EMAIL_BODY_TEMPLATE_KO.format(
        university_name=profile.institution.university_name,
        department_name=profile.institution.department_name,
        sender_name=profile.sender.display_name,
        exam_name=exam_name,
        google_calendar_url=str(profile.booking.google_calendar_url),
        sent_date_kr=_format_sent_date_kr(sent_date),
    )
    leftover = _PLACEHOLDER_RE.search(body)
    if leftover is not None:
        raise ValueError(
            f"FR-G06: body still contains placeholder {leftover.group(0)!r} "
            f"after substitution — operator profile or exam_name is missing "
            f"a required field."
        )
    return body


def build_email_draft(
    profile: ProfessorProfile | TestProfile,
    mapping_entry: EmailMappingEntry,
    pdf_bundle: StudentPDFBundle,
    *,
    course_name_kr: str,
    course_slug: str,
    semester: str,
    exam_name: str,
    sent_date: date,
    mode: DispatchMode,
    override_to: str | None = None,
) -> EmailMessageDraft:
    """Compose one ``EmailMessageDraft`` for a single (student, PDF) pair.

    Args:
        profile: Loaded operator/test profile.
        mapping_entry: ``EmailMappingEntry`` with the student's email.
        pdf_bundle: ``StudentPDFBundle`` carrying the attachment metadata.
        course_name_kr: Korean course name from ``mapping.metadata.course_name_kr``.
        course_slug: ASCII kebab-case slug used in Message-ID.
        semester: ``YYYY-N`` code used in Message-ID.
        exam_name: ``--exam-name`` value (FR-B04).
        sent_date: ``--sent-date`` value (FR-B05).
        mode: ``DispatchMode.PRODUCTION`` or ``TEST`` (FR-D09).
        override_to: When non-None, sets ``to_header`` to this address
            instead of ``mapping_entry.email`` (US2 self-test mode —
            FR-C05). The student's email is *not* used at all in this case.

    Returns:
        Validated ``EmailMessageDraft`` (Pydantic enforces single-recipient,
        Message-ID format, sha256 hex64).
    """
    if not isinstance(profile, (ProfessorProfile, TestProfile)):
        raise TypeError(
            f"build_email_draft: profile must be ProfessorProfile or "
            f"TestProfile, got {type(profile).__name__}"
        )

    sender_domain = profile.send_account.email.split("@", 1)[1]
    iso_date = sent_date.isoformat()

    from_display = f"{course_name_kr} ({profile.sender.display_name} 교수)"
    from_header = formataddr((from_display, profile.send_account.email))
    reply_to_header = formataddr(
        (profile.sender.display_name, profile.sender.email)
    )

    to_header = override_to if override_to is not None else str(mapping_entry.email)

    subject_plain = _build_subject(
        course_name_kr=course_name_kr,
        exam_name=exam_name,
        name_kr=pdf_bundle.name_kr,
        sid=pdf_bundle.student_id,
    )
    # RFC 2047 encode the Korean subject for the wire format. Plain str
    # is preserved on the draft for human inspection; subject_encoded is
    # the form that lands in the .eml / Gmail API request body.
    subject_encoded = Header(subject_plain, "utf-8").encode()

    body_text = _build_body(profile, exam_name=exam_name, sent_date=sent_date)

    # Deterministic Message-ID and boundary
    message_id = (
        f"<{pdf_bundle.student_id}.{iso_date}.{course_slug}.{semester}"
        f"@{sender_domain}>"
    )
    mime_boundary = f"boundary-{pdf_bundle.student_id}-{iso_date}"

    date_header = datetime.combine(sent_date, datetime.min.time(), tzinfo=KST).replace(
        hour=12
    )

    return EmailMessageDraft(
        student_id=pdf_bundle.student_id,
        name_kr=pdf_bundle.name_kr,
        from_header=from_header,
        reply_to_header=reply_to_header,
        to_header=to_header,
        subject=subject_plain,
        subject_encoded=subject_encoded,
        body_text=body_text,
        attachment_filename=pdf_bundle.pdf_filename,
        attachment_sha256=pdf_bundle.pdf_sha256,
        attachment_bytes_size=pdf_bundle.pdf_size_bytes,
        date_header=date_header,
        message_id=message_id,
        mime_boundary=mime_boundary,
        mode=mode,
    )


def to_email_message(draft: EmailMessageDraft, *, pdf_bytes: bytes) -> EmailMessage:
    """Materialise an ``EmailMessage`` from a ``EmailMessageDraft``.

    Args:
        draft: Validated draft returned by ``build_email_draft``.
        pdf_bytes: The exact bytes of the attachment PDF (caller reads
            from disk so this function stays pure).

    Returns:
        ``email.message.EmailMessage`` with the 8 canonical headers in
        fixed order, single text/plain body, and a single PDF
        attachment with RFC 2231 filename. Suitable for ``.as_bytes()``
        write or base64url-encoded Gmail API send.
    """
    msg = EmailMessage(policy=SMTP)
    msg["From"] = draft.from_header
    msg["Reply-To"] = draft.reply_to_header
    msg["To"] = draft.to_header
    msg["Subject"] = draft.subject
    msg["Date"] = format_datetime(draft.date_header)
    msg["Message-ID"] = draft.message_id
    msg["MIME-Version"] = "1.0"

    msg.set_content(draft.body_text, subtype="plain", charset="utf-8")
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=draft.attachment_filename,
    )
    # Pin the boundary deterministically (replace auto-generated one).
    msg.replace_header("Content-Type", f'multipart/mixed; boundary="{draft.mime_boundary}"')
    msg.set_boundary(draft.mime_boundary)
    return msg


__all__ = [
    "EMAIL_BODY_TEMPLATE_KO",
    "build_email_draft",
    "to_email_message",
]
