"""Phase C master cross-check tests (T034)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from immersio.email.master_check import (
    MasterMismatchError,
    MasterMissingError,
    cross_check_with_master,
)
from paideia_shared.schemas import StudentPDFBundle


def _bundle(tmp_path: Path, sid: str, name: str) -> StudentPDFBundle:
    pdf = tmp_path / f"{sid}_{name}.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n")
    return StudentPDFBundle(
        student_id=sid,
        name_kr=name,
        pdf_path=pdf,
        pdf_filename=pdf.name,
        pdf_size_bytes=pdf.stat().st_size,
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        body_first_page_text_normalized=f"학번{sid}",
        body_contains_student_id=True,
    )


def _make_master(tmp_path: Path, rows: list[tuple[str, str | None]]) -> Path:
    path = tmp_path / "학생마스터.parquet"
    table = pa.table(
        {
            "student_id": [r[0] for r in rows],
            "name_kr": [r[1] for r in rows],
        }
    )
    pq.write_table(table, path)
    return path


def test_matched_bundles_pass(tmp_path: Path) -> None:
    bundles = [_bundle(tmp_path, "1234567890", "홍길동")]
    master = _make_master(tmp_path, [("1234567890", "홍길동")])
    matched, missing = cross_check_with_master(bundles, master)
    assert [b.student_id for b in matched] == ["1234567890"]
    assert missing == []


def test_name_mismatch_aborts(tmp_path: Path) -> None:
    bundles = [_bundle(tmp_path, "1234567890", "홍길동")]
    master = _make_master(tmp_path, [("1234567890", "다른이름")])
    with pytest.raises(MasterMismatchError, match="FR-A05") as exc_info:
        cross_check_with_master(bundles, master)
    msg = str(exc_info.value)
    assert "홍길동" in msg
    assert "다른이름" in msg


def test_master_file_missing_raises(tmp_path: Path) -> None:
    bundles = [_bundle(tmp_path, "1234567890", "홍길동")]
    with pytest.raises(MasterMissingError):
        cross_check_with_master(bundles, tmp_path / "missing.parquet")


def test_student_not_in_master_yields_missing(tmp_path: Path) -> None:
    bundles = [
        _bundle(tmp_path, "1234567890", "홍길동"),
        _bundle(tmp_path, "1234567891", "유령"),
    ]
    master = _make_master(tmp_path, [("1234567890", "홍길동")])
    matched, missing = cross_check_with_master(bundles, master)
    assert [b.student_id for b in matched] == ["1234567890"]
    assert [b.student_id for b in missing] == ["1234567891"]
