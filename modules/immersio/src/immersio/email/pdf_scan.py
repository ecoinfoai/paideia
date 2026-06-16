"""Phase B PDF directory scan (T041).

Scans the gold PDF directory for files matching ``{학번}_{이름}.pdf``
and returns ``StudentPDFBundle`` rows with sha256 + first-page text.
File-name pattern violations or duplicate student_ids abort the run
(FR-A04, FR-A07 — *not* per-student skip).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from paideia_shared.schemas import StudentPDFBundle
from pypdf import PdfReader

_FILENAME_RE = re.compile(r"^(\d{10})_(.+)\.pdf$")


class PDFScanError(RuntimeError):
    """Raised on filename-pattern violation or duplicate student_id (FR-A04/A07)."""


def parse_filename_pattern(name: str) -> tuple[str, str]:
    """Extract ``(student_id, name_kr)`` from ``{학번}_{이름}.pdf``.

    Args:
        name: Basename of the PDF file (no path). Path-traversal
            sequences (``..``, ``/``, ``\\``, NUL, control bytes) are
            rejected even if they pass the regex (AV-S2 defence).

    Returns:
        ``(student_id, name_kr)`` tuple — student_id is 10 digits,
        name_kr is the rest before ``.pdf`` (Korean, no separator
        consumed beyond the first underscore).

    Raises:
        PDFScanError: When ``name`` does not match the regex or contains
            path-traversal segments / NUL / control bytes.
    """
    if "\x00" in name:
        raise PDFScanError(f"FR-A04: PDF filename {name!r} contains NUL byte")
    if any(ord(c) < 32 for c in name):
        raise PDFScanError(f"FR-A04: PDF filename {name!r} contains control characters")
    m = _FILENAME_RE.fullmatch(name)
    if m is None:
        raise PDFScanError(
            f"FR-A04: PDF filename {name!r} violates pattern ^(\\d{{10}})_(.+)\\.pdf$"
        )
    sid, name_kr = m.group(1), m.group(2)
    # Path-traversal defence (AV-S2): reject ``..``, path separators.
    if ".." in name_kr or "/" in name_kr or "\\" in name_kr:
        raise PDFScanError(
            f"FR-A04: PDF filename {name!r} contains path-traversal segment in name_kr={name_kr!r}"
        )
    return sid, name_kr


def _normalize_first_page_text(text: str) -> str:
    """Strip whitespace + soft hyphens for FR-A06 substring search."""
    if not text:
        return ""
    return re.sub(r"[\s­​]+", "", text)


def _read_first_page_text(pdf_path: Path) -> str:
    """Best-effort first-page text extract (returns ``""`` on failure)."""
    try:
        reader = PdfReader(str(pdf_path))
        if not reader.pages:
            return ""
        return reader.pages[0].extract_text() or ""
    except Exception:  # noqa: BLE001 — pypdf raises a wide tree
        return ""


def scan_pdf_directory(gold_pdf_dir: Path) -> list[StudentPDFBundle]:
    """Scan ``gold_pdf_dir`` and return one ``StudentPDFBundle`` per PDF.

    Args:
        gold_pdf_dir: Absolute path to ``data/gold/immersio/.../이메일_발송용/``.
            Must exist and be readable.

    Returns:
        List of ``StudentPDFBundle``, sorted by ``student_id``.

    Raises:
        PDFScanError: When the directory does not exist, contains a PDF
            with a filename violating ``^(\\d{10})_(.+)\\.pdf$``, or
            two PDFs share the same student_id (FR-A07 — silent overwrite
            risk, abort).
    """
    if not isinstance(gold_pdf_dir, Path):
        raise PDFScanError(
            f"scan_pdf_directory: gold_pdf_dir must be Path, got {type(gold_pdf_dir).__name__}"
        )
    if not gold_pdf_dir.is_dir():
        raise PDFScanError(f"scan_pdf_directory: directory not found at {gold_pdf_dir}")

    by_sid: dict[str, StudentPDFBundle] = {}
    for path in sorted(gold_pdf_dir.glob("*.pdf")):
        if not path.is_file():
            continue
        sid, name_kr = parse_filename_pattern(path.name)
        if sid in by_sid:
            raise PDFScanError(
                f"FR-A07: duplicate student_id {sid!r} — files "
                f"{by_sid[sid].pdf_filename!r} and {path.name!r} "
                f"both claim the same student. Resolve before re-running."
            )
        size_bytes = path.stat().st_size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        first_page = _read_first_page_text(path)
        normalized = _normalize_first_page_text(first_page)
        contains_id = sid in normalized
        bundle = StudentPDFBundle(
            student_id=sid,
            name_kr=name_kr,
            pdf_path=path,
            pdf_filename=path.name,
            pdf_size_bytes=size_bytes,
            pdf_sha256=digest,
            body_first_page_text_normalized=normalized,
            body_contains_student_id=contains_id,
        )
        by_sid[sid] = bundle

    return sorted(by_sid.values(), key=lambda b: b.student_id)


__all__ = ["PDFScanError", "parse_filename_pattern", "scan_pdf_directory"]
