"""Dummy PDF byte-identical contract test (T086, SOURCE_DATE_EPOCH=0)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from immersio.email.dummy_fixture import generate_dummy_pdfs


def test_two_calls_byte_identical_in_different_dirs(tmp_path: Path) -> None:
    """Same input, two output dirs → byte-identical PDF pair (R9)."""
    students = [("1234567990", "더미일"), ("1234567991", "더미이")]
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    a_paths = sorted(generate_dummy_pdfs(out_a, students))
    b_paths = sorted(generate_dummy_pdfs(out_b, students))
    for pa, pb in zip(a_paths, b_paths, strict=True):
        assert pa.read_bytes() == pb.read_bytes()
        assert hashlib.sha256(pa.read_bytes()).hexdigest() == (
            hashlib.sha256(pb.read_bytes()).hexdigest()
        )


def test_pdf_hash_matches_expected_pattern(tmp_path: Path) -> None:
    """Hash is hex64 — sanity check on hashlib output."""
    [pdf] = generate_dummy_pdfs(tmp_path, [("1234567990", "더미일")])
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
