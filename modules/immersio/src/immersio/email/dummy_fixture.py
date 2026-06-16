"""Dummy PDF generator for TestProfile mode (T087, R9).

Generates 1-page PDFs containing the student_id text so the regular
PDF body verifier (FR-A06) accepts them. SOURCE_DATE_EPOCH=0 +
deterministic content → byte-identical across re-runs.

The helper is *callee-agnostic* — student_id / name_kr come from the
caller (TestProfile.dummy_students). No identifying value is hard-
coded inside this module (FR-G04 / ADR-009).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from reportlab.pdfgen import canvas


@contextmanager
def _frozen_clock() -> Iterator[None]:
    """Pin SOURCE_DATE_EPOCH=0 so reportlab metadata is deterministic."""
    original = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = original


def generate_dummy_pdfs(
    output_dir: Path,
    students: list[tuple[str, str]],
) -> list[Path]:
    """Write one PDF per ``(student_id, name_kr)`` tuple to ``output_dir``.

    Args:
        output_dir: Test-mode dummy fixture directory (typically
            ``profile.dummy_fixture_dir``). Created if missing.
        students: List of ``(student_id, name_kr)`` tuples. Caller pre-
            sorts for determinism.

    Returns:
        List of paths written, sorted by student_id.

    Side effects:
        Each PDF contains the student_id on page 1 so FR-A06 body
        verification passes the same downstream check as production
        PDFs. Filenames follow ``{student_id}_{name_kr}.pdf``.
    """
    if not isinstance(output_dir, Path):
        raise TypeError(f"output_dir must be Path, got {type(output_dir).__name__}")
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    with _frozen_clock():
        for sid, name_kr in sorted(students, key=lambda s: s[0]):
            path = output_dir / f"{sid}_{name_kr}.pdf"
            c = canvas.Canvas(str(path))
            c.drawString(100, 750, f"학번: {sid}")
            c.drawString(100, 720, f"이름: {name_kr}")
            c.drawString(100, 680, "더미 학생 보고서 (test mode)")
            c.showPage()
            c.save()
            written.append(path)
    return written


__all__ = ["generate_dummy_pdfs"]
