"""Contract tests for StudentPDFBundle (T010)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import StudentPDFBundle
from pydantic import ValidationError


def _make_pdf(tmp_path, name: str = "1234567890_홍길동.pdf") -> tuple:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4\nfake content\n%%EOF\n")
    return path, name


def test_valid_bundle_construction(tmp_path) -> None:
    path, name = _make_pdf(tmp_path)
    bundle = StudentPDFBundle(
        student_id="1234567890",
        name_kr="홍길동",
        pdf_path=path,
        pdf_filename=name,
        pdf_size_bytes=path.stat().st_size,
        pdf_sha256="a" * 64,
        body_first_page_text_normalized="hello",
        body_contains_student_id=True,
    )
    assert bundle.body_contains_student_id is True


def test_sha256_must_be_hex64(tmp_path) -> None:
    path, name = _make_pdf(tmp_path)
    with pytest.raises(ValidationError):
        StudentPDFBundle(
            student_id="1234567890",
            name_kr="홍길동",
            pdf_path=path,
            pdf_filename=name,
            pdf_size_bytes=10,
            pdf_sha256="too-short",
            body_first_page_text_normalized="x",
            body_contains_student_id=False,
        )


def test_sha256_uppercase_rejected(tmp_path) -> None:
    path, name = _make_pdf(tmp_path)
    with pytest.raises(ValidationError):
        StudentPDFBundle(
            student_id="1234567890",
            name_kr="홍길동",
            pdf_path=path,
            pdf_filename=name,
            pdf_size_bytes=10,
            pdf_sha256="A" * 64,  # uppercase rejected
            body_first_page_text_normalized="x",
            body_contains_student_id=False,
        )


def test_pdf_filename_must_be_basename(tmp_path) -> None:
    path, _ = _make_pdf(tmp_path)
    with pytest.raises(ValidationError):
        StudentPDFBundle(
            student_id="1234567890",
            name_kr="홍길동",
            pdf_path=path,
            pdf_filename=str(path),  # full path, not basename
            pdf_size_bytes=10,
            pdf_sha256="a" * 64,
            body_first_page_text_normalized="x",
            body_contains_student_id=False,
        )


def test_pdf_size_bytes_must_be_positive(tmp_path) -> None:
    path, name = _make_pdf(tmp_path)
    with pytest.raises(ValidationError):
        StudentPDFBundle(
            student_id="1234567890",
            name_kr="홍길동",
            pdf_path=path,
            pdf_filename=name,
            pdf_size_bytes=0,
            pdf_sha256="a" * 64,
            body_first_page_text_normalized="x",
            body_contains_student_id=False,
        )


def test_body_contains_student_id_must_be_bool(tmp_path) -> None:
    path, name = _make_pdf(tmp_path)
    bundle = StudentPDFBundle(
        student_id="1234567890",
        name_kr="홍길동",
        pdf_path=path,
        pdf_filename=name,
        pdf_size_bytes=10,
        pdf_sha256="a" * 64,
        body_first_page_text_normalized="x",
        body_contains_student_id=False,
    )
    assert bundle.body_contains_student_id is False
