"""Phase E (dry-run) — write .eml preview files (T045).

Each ``EmailMessageDraft`` is materialised via ``to_email_message`` and
serialised to ``{학번}_{이름}.eml`` under the preview directory.
Same input + same ``--sent-date`` → byte-identical output (SC-010).
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import EmailMessageDraft, StudentPDFBundle

from .composer import to_email_message


def write_eml_preview_files(
    drafts_with_pdfs: list[tuple[EmailMessageDraft, StudentPDFBundle]],
    preview_dir: Path,
) -> list[Path]:
    """Write one .eml per draft and return the resulting paths.

    Args:
        drafts_with_pdfs: Pairs ``(draft, bundle)`` so the writer can read
            attachment bytes from ``bundle.pdf_path``.
        preview_dir: Output directory. Created (and parents) if missing.

    Returns:
        List of written .eml paths sorted by ``student_id``.
    """
    if not isinstance(preview_dir, Path):
        raise TypeError(
            f"write_eml_preview_files: preview_dir must be Path, got "
            f"{type(preview_dir).__name__}"
        )
    preview_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for draft, bundle in drafts_with_pdfs:
        if draft.student_id != bundle.student_id:
            raise ValueError(
                f"write_eml_preview_files: draft/bundle student_id mismatch "
                f"({draft.student_id!r} vs {bundle.student_id!r})"
            )
        eml_name = f"{draft.student_id}_{draft.name_kr}.eml"
        eml_path = preview_dir / eml_name
        msg = to_email_message(draft, pdf_bytes=bundle.pdf_path.read_bytes())
        eml_path.write_bytes(msg.as_bytes())
        written.append(eml_path)

    return sorted(written, key=lambda p: p.name)


__all__ = ["write_eml_preview_files"]
