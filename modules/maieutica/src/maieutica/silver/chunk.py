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
# Section-heading detection (multi-level)
# ---------------------------------------------------------------------------

# Ordered level patterns.  ANY match (at any level) is a chunk boundary, so the
# split descends to the deepest heading present in each branch (contract C1).
# Order matters: ``N.M`` MUST be tried before plain ``N.`` so that "1.1 제목"
# is captured as one decimal label rather than partially matching "1.".  Each
# pattern captures (marker, title); the emitted section label is the verbatim
# heading text "<marker> <title>".
_SECTION_HEADING_PATTERNS: Final = (
    re.compile(r"^\s*(\d+\.\d+)\s+(.+)$"),  # N.M   e.g. "1.1 제목"
    re.compile(r"^\s*(\d+\.)\s+(.+)$"),  # N.    e.g. "1. 제목"
    re.compile(r"^\s*(\d+\))\s+(.+)$"),  # N)    e.g. "1) 코"
    re.compile(r"^\s*(\(\d+\))\s+(.+)$"),  # (N)   e.g. "(1) 코"
    re.compile(r"^\s*([가-힣]\))\s+(.+)$"),  # 가)   e.g. "가) 성대"
    re.compile(r"^\s*([①-⑳])\s+(.+)$"),  # ①-⑳ e.g. "① 중추 조절"
)

# Oversized-subsection multiplier (contract C2).  A subsection whose body char
# count exceeds (chapter median body char count × this constant) is further
# split at blank-line (paragraph) boundaries.  Fixed in code, never per-chapter.
_OVERSIZE_K: Final = 3


def _match_section_heading(text: str) -> str | None:
    """Return the verbatim section label if *text* is a numbered heading.

    A line is a heading only when it genuinely STARTS with a level marker
    (leading whitespace, then the marker, then whitespace, then a title), so a
    body sentence that merely contains a marker mid-line never matches.

    Args:
        text: A single (already stripped) candidate line.

    Returns:
        The normalised section label ``"<marker> <title>"`` (single space
        between marker and title), or ``None`` if no level pattern matches.
    """
    for pattern in _SECTION_HEADING_PATTERNS:
        m = pattern.match(text)
        if m:
            return f"{m.group(1)} {m.group(2).strip()}"
    return None


def _body_char_count(
    non_blank_kept: list[tuple[int, str]],
    line_start: int,
    line_end: int,
) -> int:
    """Sum non-blank character counts over a subsection's original line range.

    Blank lines are excluded since they carry no body content; the count is
    used only to compare subsection sizes for the oversized test (C2).

    Args:
        non_blank_kept: ``(lineno, text)`` pairs for kept non-blank lines.
        line_start: Inclusive ORIGINAL start line of the subsection.
        line_end: Inclusive ORIGINAL end line of the subsection.

    Returns:
        Total character count of the subsection's non-blank body lines.
    """
    return sum(len(text) for lineno, text in non_blank_kept if line_start <= lineno <= line_end)


def _paragraph_split(
    kept: list[tuple[int, str]],
    line_start: int,
    line_end: int,
) -> list[tuple[int, int]]:
    """Split a subsection's line range into paragraph pieces at blank lines.

    A blank line ENDS the current paragraph piece (the blank itself is kept at
    the tail of that piece), so the returned pieces tile ``[line_start,
    line_end]`` contiguously with no overlap (C3).  A run with no interior blank
    line yields a single piece identical to the input range.

    Args:
        kept: ``(lineno, text)`` pairs for ALL kept lines (blanks included),
            in original line order.
        line_start: Inclusive ORIGINAL start line of the subsection.
        line_end: Inclusive ORIGINAL end line of the subsection.

    Returns:
        Ordered list of ``(piece_start, piece_end)`` ORIGINAL line ranges that
        exactly partition ``[line_start, line_end]``.
    """
    pieces: list[tuple[int, int]] = []
    piece_start = line_start
    for lineno, text in kept:
        if lineno < line_start or lineno > line_end:
            continue
        if not text.strip():
            # Blank line closes the current piece (blank rides at its tail).
            pieces.append((piece_start, lineno))
            piece_start = lineno + 1
    if piece_start <= line_end:
        pieces.append((piece_start, line_end))
    return pieces


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
    2. Detect multi-level section boundaries via
       :func:`_match_section_heading` on the kept lines (``N.`` · ``N)`` ·
       ``(N)`` · ``가)`` · ``①`` · ``N.M``).  A heading appearing more than
       once is assumed to have a TOC copy at the top; the first occurrence is
       skipped.
    3. Emit one chunk per body section, preserving ORIGINAL line ranges; a
       subsection whose body exceeds the chapter median × :data:`_OVERSIZE_K`
       is further paragraph-split at blank-line boundaries.
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

    # Collect heading candidates (original lineno + normalised section text)
    # across ALL levels — any detected heading is a chunk boundary (C1).
    candidates: list[tuple[int, str]] = []
    for lineno, text in non_blank_kept:
        sec_text = _match_section_heading(text.strip())
        if sec_text is not None:
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

    # Build one (section, line_start, line_end) span per body heading; each
    # heading region runs up to the line before the next heading (C3: ranges are
    # contiguous, ORIGINAL, and non-overlapping).
    subsections: list[tuple[str, int, int]] = []
    for idx, (heading_lineno, section_text) in enumerate(body_headings):
        end_lineno = body_headings[idx + 1][0] - 1 if idx + 1 < len(body_headings) else last_line
        subsections.append((section_text, heading_lineno, end_lineno))

    # Oversized threshold: subsections whose body exceeds median × K are
    # paragraph-split (C2).  K is the fixed code constant _OVERSIZE_K.
    body_char_counts = [
        _body_char_count(non_blank_kept, start, end) for _, start, end in subsections
    ]
    sorted_counts = sorted(body_char_counts)
    n_sub = len(sorted_counts)
    median = (
        sorted_counts[n_sub // 2]
        if n_sub % 2 == 1
        else (sorted_counts[n_sub // 2 - 1] + sorted_counts[n_sub // 2]) / 2
    )
    threshold = median * _OVERSIZE_K

    # A single global ordinal across ALL final chunks keeps chunk_ids unique and
    # deterministic even when an oversized subsection yields several pieces (C5).
    ordinal = 0
    for (section_text, start, end), char_count in zip(subsections, body_char_counts, strict=True):
        pieces = _paragraph_split(kept, start, end) if char_count > threshold else [(start, end)]

        for piece_start, piece_end in pieces:
            section_lines = [
                text for lineno, text in non_blank_kept if piece_start <= lineno <= piece_end
            ]
            text_body = "\n".join(section_lines)
            chunk_id = _make_chunk_id(semester, course_slug, chapter_no, section_text, ordinal)
            chunks.append(
                TextbookChunk(
                    semester=semester,
                    course_slug=course_slug,
                    chunk_id=chunk_id,
                    chapter_no=chapter_no,
                    chapter=chapter,
                    section=section_text,
                    source_file=source_file,
                    line_start=piece_start,
                    line_end=piece_end,
                    text=text_body if text_body.strip() else "(empty)",
                    removed_spans=removed_spans,
                )
            )
            ordinal += 1

    return chunks


__all__ = ["chunk_chapter"]
