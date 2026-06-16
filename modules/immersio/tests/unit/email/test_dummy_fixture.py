"""dummy_fixture.py unit tests (T084)."""

from __future__ import annotations

import re
from pathlib import Path

from immersio.email.dummy_fixture import generate_dummy_pdfs


def test_byte_identical_two_calls(tmp_path: Path) -> None:
    """Same input two calls → byte-identical PDFs (SOURCE_DATE_EPOCH=0)."""
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    students = [("1234567001", "홍길동"), ("1234567002", "김갑동")]
    paths_a = generate_dummy_pdfs(out_a, students)
    paths_b = generate_dummy_pdfs(out_b, students)
    for pa, pb in zip(sorted(paths_a), sorted(paths_b), strict=True):
        assert pa.read_bytes() == pb.read_bytes()


def test_body_contains_student_id(tmp_path: Path) -> None:
    """PDF body must contain student_id text (FR-A06 downstream pass)."""
    students = [("1234567890", "홍길동")]
    [pdf] = generate_dummy_pdfs(tmp_path, students)

    # pypdf extract — same path the production verifier uses
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    text = reader.pages[0].extract_text() or ""
    # Whitespace-stripped text contains student_id
    normalized = re.sub(r"\s+", "", text)
    assert "1234567890" in normalized


def test_arbitrary_student_id_lands_in_body(tmp_path: Path) -> None:
    """Caller-provided student_id appears in body — no hard-coding."""
    custom_sid = "9988776655"
    [pdf] = generate_dummy_pdfs(tmp_path, [(custom_sid, "테스트학생")])

    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    text = reader.pages[0].extract_text() or ""
    normalized = re.sub(r"\s+", "", text)
    assert custom_sid in normalized


def test_filename_pattern_matches_production(tmp_path: Path) -> None:
    """Output filenames follow ``{학번}_{이름}.pdf`` (FR-A04 pass)."""
    students = [("1234567001", "홍길동"), ("1234567002", "김갑동")]
    paths = generate_dummy_pdfs(tmp_path, students)
    names = sorted(p.name for p in paths)
    assert names == ["1234567001_홍길동.pdf", "1234567002_김갑동.pdf"]
