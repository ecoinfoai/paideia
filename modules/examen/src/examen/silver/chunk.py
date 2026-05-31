"""T023 — Section-level textbook chunking with TOC anchors.

Splits a cleaned chapter into :class:`paideia_shared.schemas.TextbookChunk`
objects, one per numbered section.  Section headings are detected from the
in-body occurrences of "N. 절제목" patterns (which mirror the chapter-top
TOC entries).

Each chunk carries:
- Deterministic ``chunk_id`` — SHA-256 of ``(semester, course_slug,
  chapter_no, section, ordinal)`` encoded as UTF-8 JSON.
- ``line_start`` / ``line_end`` — **ORIGINAL** file line numbers (not
  renumbered after cleaning) so the evidence index can anchor any passage.
- ``text`` — cleaned body text (exercises / captions / headers already
  stripped by :func:`examen.ingest.textbook_clean.clean_textbook`).
- ``removed_spans`` — forwarded from the cleaner for auditability.

Fallback behaviour: if no numbered sections are detected, the whole chapter
is returned as a single chunk (section=None).

Usage::

    from examen.silver.chunk import chunk_chapter

    chunks = chunk_chapter(
        lines=raw_lines,          # list[str] — original file lines
        chapter_no=10,
        chapter="10장 내분비계통",
        semester="2026-1",
        course_slug="anatomy",
        source_file="10장 내분비계통.txt",
        txt_summary=None,         # optional auxiliary summary text
    )
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Final

from paideia_shared.schemas import TextbookChunk

from examen.ingest.textbook_clean import clean_textbook

# ---------------------------------------------------------------------------
# Section-heading detection
# ---------------------------------------------------------------------------

# Matches "N. 절제목" where N is one or more digits.
# Covers both TOC entries (near chapter top) and body headings.
_RE_SECTION_HEADING: Final = re.compile(
    r"^\s*(\d+)\.\s+(.+)$"
)


def _make_chunk_id(
    semester: str,
    course_slug: str,
    chapter_no: int,
    section: str | None,
    ordinal: int,
) -> str:
    """Compute a deterministic chunk_id.

    The ID is the first 16 hex characters of the SHA-256 digest of the
    canonical JSON-encoded key tuple.  JSON key order is fixed (list) so
    the encoding is always identical for identical inputs.

    Args:
        semester: Semester code.
        course_slug: Course slug.
        chapter_no: Chapter number.
        section: Section heading string, or None for whole-chapter chunks.
        ordinal: 0-based ordinal within the chapter (disambiguates if a
            section heading appears more than once).

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
    txt_summary: str | None = None,
) -> list[TextbookChunk]:
    """Split a raw chapter into section-level TextbookChunk objects.

    Steps:
    1. Run :func:`~examen.ingest.textbook_clean.clean_textbook` on *lines*.
       This yields ``kept`` (original linenos + texts) and ``removed_spans``.
    2. Detect section boundaries using :data:`_RE_SECTION_HEADING` on the
       kept lines.
    3. Emit one chunk per section, preserving original line ranges.
    4. If no section headings found, emit a single whole-chapter chunk.

    The optional *txt_summary* is appended to the chunk text as an
    ``[auxiliary_summary]`` block when present.  It is NEVER used as the
    authoritative line anchor — line_start / line_end always reference the
    original textbook lines.

    Args:
        lines: Raw (uncleaned) lines from the textbook .txt file.
        chapter_no: Integer chapter number.
        chapter: Full chapter title string.
        semester: SemesterCode value.
        course_slug: CourseSlug value.
        source_file: Filename of the source .txt (basename, not full path).
        txt_summary: Optional auxiliary summary text (not authoritative).

    Returns:
        Non-empty list of :class:`~paideia_shared.schemas.TextbookChunk`.
    """
    # ----------------------------------------------------------------
    # Step 1: clean
    # ----------------------------------------------------------------
    kept, removed_spans = clean_textbook(lines)

    # Convenience: filter out blank lines for body text, but keep original
    # linenos for range calculation.
    non_blank_kept = [(lineno, text) for lineno, text in kept if text.strip()]

    # ----------------------------------------------------------------
    # Step 2: detect section boundaries in kept lines
    # ----------------------------------------------------------------
    # A section boundary is a kept line whose text matches _RE_SECTION_HEADING.
    # We also need to avoid re-detecting the TOC at the top of the chapter.
    # Strategy: the FIRST occurrence of "N. …" is TOC; subsequent occurrences
    # are body headings.  We use a two-pass approach:
    #   Pass A — collect all candidate (kept_index, lineno, section_text)
    #   Pass B — deduplicate: keep only body occurrences (second+ occurrence
    #            of each section number) OR, if a heading appears only once,
    #            treat that single occurrence as the body heading.

    # Collect all matching lines (kept, not blank)
    candidates: list[tuple[int, str]] = []  # (original_lineno, section_text)
    for lineno, text in non_blank_kept:
        m = _RE_SECTION_HEADING.match(text.strip())
        if m:
            # Reconstruct as "N. text" normalised
            sec_text = f"{m.group(1)}. {m.group(2).strip()}"
            candidates.append((lineno, sec_text))

    # Count occurrences per section number
    from collections import Counter
    sec_counts: Counter[str] = Counter(sec for _, sec in candidates)

    # Build body_headings: for each section number that appears >1 time,
    # skip the first occurrence (TOC); keep the rest.  If only once, keep it.
    body_headings: list[tuple[int, str]] = []  # (original_lineno, section_text)
    seen_sec: Counter[str] = Counter()
    for lineno, sec in candidates:
        seen_sec[sec] += 1
        if sec_counts[sec] > 1 and seen_sec[sec] == 1:
            # This is the first (TOC) occurrence — skip
            continue
        body_headings.append((lineno, sec))

    # ----------------------------------------------------------------
    # Step 3: build chunks
    # ----------------------------------------------------------------
    chunks: list[TextbookChunk] = []

    if not body_headings:
        # Fallback: whole-chapter as one chunk
        if non_blank_kept:
            line_start = non_blank_kept[0][0]
            line_end = non_blank_kept[-1][0]
        else:
            line_start = 1
            line_end = max(len(lines), 1)

        body_lines = [text for _, text in non_blank_kept]
        text_body = "\n".join(body_lines)
        if txt_summary:
            text_body = f"{text_body}\n\n[auxiliary_summary]\n{txt_summary}"

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

    # Determine the line range for each section:
    # Section i covers from body_headings[i][0] to body_headings[i+1][0]-1
    # (or to the last non-blank kept line for the final section).
    last_line = non_blank_kept[-1][0] if non_blank_kept else len(lines)

    for ordinal, (heading_lineno, section_text) in enumerate(body_headings):
        # Determine end line: start of next section heading minus 1,
        # or the last kept non-blank line.
        if ordinal + 1 < len(body_headings):
            next_heading_lineno = body_headings[ordinal + 1][0]
            # Include lines up to (but not including) the next heading
            end_lineno = next_heading_lineno - 1
        else:
            end_lineno = last_line

        # Collect body lines for this section (heading + body, no blanks)
        section_lines = [
            text
            for lineno, text in non_blank_kept
            if heading_lineno <= lineno <= end_lineno
        ]

        text_body = "\n".join(section_lines)
        if txt_summary:
            text_body = f"{text_body}\n\n[auxiliary_summary]\n{txt_summary}"

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
