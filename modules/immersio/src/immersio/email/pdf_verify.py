"""Phase D — PDF body student-id substring verification (T043).

The ``StudentPDFBundle`` already carries ``body_contains_student_id``
populated by ``scan_pdf_directory`` — this module re-evaluates it for
clarity and emits the per-student skip / failed classification used by
the pipeline's reporting layer.

Attachment-size check (FR-F02) lands here too: any PDF whose
``pdf_size_bytes`` exceeds the operator's
``profile.operational_defaults.attachment_max_bytes`` is classified as
``failed`` with ``error_kind=attachment_size_exceeded``.
"""

from __future__ import annotations

from dataclasses import dataclass

from paideia_shared.schemas import StudentPDFBundle


@dataclass(frozen=True)
class PDFVerifyResult:
    """Outcome of verifying one ``StudentPDFBundle`` (Phase D).

    Attributes:
        bundle: The original bundle (unchanged).
        ok: True if the PDF passes both the body-substring and the
            attachment-size checks.
        error_kind: ``""`` when ``ok`` is True; otherwise one of
            ``pdf_no_student_id`` (FR-A06) or ``attachment_size_exceeded``
            (FR-F02).
    """

    bundle: StudentPDFBundle
    ok: bool
    error_kind: str


def verify_pdf_body_contains_student_id(
    bundle: StudentPDFBundle,
    *,
    attachment_max_bytes: int,
) -> PDFVerifyResult:
    """Verify that the PDF body contains the student_id and is within size.

    Args:
        bundle: One ``StudentPDFBundle`` from the scan/cross-check pipeline.
        attachment_max_bytes: Operator-configured max attachment size
            from ``profile.operational_defaults.attachment_max_bytes``.
            Boundary is inclusive — exactly equal is OK.

    Returns:
        ``PDFVerifyResult`` with ``ok=False`` + appropriate ``error_kind``
        on the first failed check, or ``ok=True`` + empty error_kind.
    """
    if attachment_max_bytes < 1:
        raise ValueError(
            f"attachment_max_bytes must be ≥ 1 (got {attachment_max_bytes})"
        )
    if bundle.pdf_size_bytes > attachment_max_bytes:
        return PDFVerifyResult(
            bundle=bundle, ok=False, error_kind="attachment_size_exceeded"
        )
    if not bundle.body_contains_student_id:
        return PDFVerifyResult(
            bundle=bundle, ok=False, error_kind="pdf_no_student_id"
        )
    return PDFVerifyResult(bundle=bundle, ok=True, error_kind="")


__all__ = ["PDFVerifyResult", "verify_pdf_body_contains_student_id"]
