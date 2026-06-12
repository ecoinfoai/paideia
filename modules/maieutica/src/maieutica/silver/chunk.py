"""T021 — Section-level textbook chunking for maieutica.

Splits a cleaned chapter into :class:`paideia_shared.schemas.TextbookChunk`
objects, one per numbered section.  Mirrors ``examen.silver.chunk`` but reads
maieutica's own ingest layer (``clean_textbook``).

Each chunk carries:
- Deterministic ``chunk_id`` — SHA-256 of ``(semester, course_slug,
  chapter_no, section, ordinal)`` encoded as canonical JSON.  Same input ⇒
  same id, across runs.
- ``line_start`` / ``line_end`` — **ORIGINAL** file line numbers (never
  renumbered after cleaning) so the evidence index (T022) can anchor any
  passage at its true position.
- ``text`` — cleaned body text (exercises / captions / headers already
  stripped by :func:`maieutica.ingest.textbook_clean.clean_textbook`).
- ``removed_spans`` — forwarded from the cleaner for auditability.

Fallback: if no numbered sections are detected, the whole chapter is returned
as a single chunk (``section=None``).

Usage::

    from maieutica.silver.chunk import chunk_chapter

    chunks = chunk_chapter(
        lines=raw_lines,          # list[str] — original file lines
        chapter_no=8,
        chapter="8장 호흡계통",
        semester="2026-1",
        course_slug="anatomy",
        source_file="8장 호흡계통.txt",
    )
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Final

from paideia_shared.schemas import TextbookChunk

from maieutica.ingest.textbook_clean import clean_textbook

# ---------------------------------------------------------------------------
# Section-heading detection
# ---------------------------------------------------------------------------

# Matches "N. 절제목" where N is one or more digits (TOC and body headings).
_RE_SECTION_HEADING: Final = re.compile(r"^\s*(\d+)\.\s+(.+)$")


def _make_chunk_id(
    semester: str,
    course_slug: str,
    chapter_no: int,
    section: str | None,
    ordinal: int,
) -> str:
    """Compute a deterministic chunk_id.

    The ID is the first 16 hex characters of the SHA-256 digest of the
    canonical JSON-encoded key list.  JSON list order is fixed so the
    encoding is identical for identical inputs.

    Args:
        semester: Semester code.
        course_slug: Course slug.
        chapter_no: Chapter number.
        section: Section heading string, or None for whole-chapter chunks.
        ordinal: 0-based ordinal within the chapter.

    Returns:
        16-character lowercase hex string.
    """
    key = json.dumps(
        [semester, course_slug, chapter_no, section, ordinal],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest[:16]


def chunk_chapter(
    lines: list[str],
    *,
    chapter_no: int,
    chapter: str,
    semester: str,
    course_slug: str,
    source_file: str,
) -> list[TextbookChunk]:
    """Split a raw chapter into section-level TextbookChunk objects.

    Steps:
    1. Run :func:`~maieutica.ingest.textbook_clean.clean_textbook` on *lines*,
       yielding ``kept`` (original linenos + texts) and ``removed_spans``.
    2. Detect section boundaries via :data:`_RE_SECTION_HEADING` on the kept
       lines.  A heading appearing more than once is assumed to have a TOC
       copy at the top; the first occurrence is skipped.
    3. Emit one chunk per body section, preserving ORIGINAL line ranges.
    4. If no section headings are found, emit one whole-chapter chunk.

    Args:
        lines: Raw (uncleaned) lines from the textbook .txt file.
        chapter_no: Integer chapter number.
        chapter: Full chapter title string.
        semester: SemesterCode value.
        course_slug: CourseSlug value.
        source_file: Basename of the source .txt file (authority).

    Returns:
        Non-empty list of :class:`~paideia_shared.schemas.TextbookChunk`.
    """
    kept, removed_spans = clean_textbook(lines)

    # Keep original linenos but drop blanks for body/heading detection.
    non_blank_kept = [(lineno, text) for lineno, text in kept if text.strip()]

    # Collect heading candidates (original lineno + normalised section text).
    candidates: list[tuple[int, str]] = []
    for lineno, text in non_blank_kept:
        m = _RE_SECTION_HEADING.match(text.strip())
        if m:
            sec_text = f"{m.group(1)}. {m.group(2).strip()}"
            candidates.append((lineno, sec_text))

    sec_counts: Counter[str] = Counter(sec for _, sec in candidates)

    # Skip the first occurrence of any heading that appears more than once
    # (that copy is the chapter-top TOC entry); keep the rest as body headings.
    body_headings: list[tuple[int, str]] = []
    seen_sec: Counter[str] = Counter()
    for lineno, sec in candidates:
        seen_sec[sec] += 1
        if sec_counts[sec] > 1 and seen_sec[sec] == 1:
            continue
        body_headings.append((lineno, sec))

    chunks: list[TextbookChunk] = []

    if not body_headings:
        # Fallback: whole chapter as one chunk.
        if non_blank_kept:
            line_start = non_blank_kept[0][0]
            line_end = non_blank_kept[-1][0]
        else:
            line_start = 1
            line_end = max(len(lines), 1)

        text_body = "\n".join(text for _, text in non_blank_kept)
        chunk_id = _make_chunk_id(semester, course_slug, chapter_no, None, 0)
        chunks.append(
            TextbookChunk(
                semester=semester,
                course_slug=course_slug,
                chunk_id=chunk_id,
                chapter_no=chapter_no,
                chapter=chapter,
                section=None,
                source_file=source_file,
                line_start=line_start,
                line_end=line_end,
                text=text_body if text_body.strip() else "(empty)",
                removed_spans=removed_spans,
            )
        )
        return chunks

    last_line = non_blank_kept[-1][0] if non_blank_kept else len(lines)

    for ordinal, (heading_lineno, section_text) in enumerate(body_headings):
        if ordinal + 1 < len(body_headings):
            end_lineno = body_headings[ordinal + 1][0] - 1
        else:
            end_lineno = last_line

        section_lines = [
            text
            for lineno, text in non_blank_kept
            if heading_lineno <= lineno <= end_lineno
        ]
        text_body = "\n".join(section_lines)

        chunk_id = _make_chunk_id(
            semester, course_slug, chapter_no, section_text, ordinal
        )
        chunks.append(
            TextbookChunk(
                semester=semester,
                course_slug=course_slug,
                chunk_id=chunk_id,
                chapter_no=chapter_no,
                chapter=chapter,
                section=section_text,
                source_file=source_file,
                line_start=heading_lineno,
                line_end=end_lineno,
                text=text_body if text_body.strip() else "(empty)",
                removed_spans=removed_spans,
            )
        )

    return chunks


__all__ = ["chunk_chapter"]
