"""T019 — Deterministic textbook rule cleaner.

Strips noise introduced by PDF extraction from raw textbook ``.txt`` files and
returns a list of kept ``(original_lineno, text)`` pairs plus a
``removed_spans`` audit log.  All decisions are rule-based; no LLM is involved.

Noise categories handled
------------------------
1. Spaced-letter headers  — lines where every visible "word" is a single
   uppercase character separated by spaces, e.g. "C H A P T E R  10" or
   "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y".
2. Running chapter headers — lines matching "제NNN장 …" (repeat at page top).
3. Standalone page numbers — a line containing only digits (optionally
   surrounded by whitespace).
4. Figure captions        — lines starting "그림 NN-N" (Korean figure label).
5. Table captions         — lines starting "표 NN-N" (Korean table label).
6. 연습문제 block           — from a line equal to "연습문제" (or a variant) to
   the end of the file (chapter-level exercises always appear at the tail).
7. 참고문헌 section          — from a line starting "참고문헌" to end of file.
8. Footnote marker lines  — lines starting with †, *, ※ (footnote body, NOT
   body text that happens to reference a note).

Body text and numbered section headings are explicitly KEPT.

removed_spans format
--------------------
Each entry is a human-readable string referencing the ORIGINAL (1-based) line
number(s) of the removed content::

    "[reason] line N: 'text'"         # single-line removal
    "[reason] lines start–end: …"     # multi-line block removal

``removed_spans`` is an AUDIT LOG ONLY — it is not a structured offset source,
and downstream code must NOT string-parse the ``line N`` token to recover
offsets.  Char offsets for KEPT lines are derived from the full original line
list produced by ``load_chapter`` (T018) together with the ``(lineno, text)``
pairs returned here::

    char_start(N) = sum(len(line_k) + 1 for k in 1..N-1)

i.e. the offset of a kept line is computed from the original lines and its
preserved lineno, never by re-parsing the audit strings.

Usage::

    from maieutica.ingest.textbook_clean import clean_textbook

    kept, removed_spans = clean_textbook(lines)
    # kept: list[tuple[int, str]]  — (1-based original lineno, text)
    # removed_spans: list[str]     — human-readable audit log entries
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Compiled regex patterns (compiled once at module load for determinism)
# ---------------------------------------------------------------------------

# Standalone page number: line is only digits
_RE_PAGE_NUMBER: Final = re.compile(r"^\s*\d+\s*$")

# Figure caption: starts "그림 " followed by a digit
_RE_FIGURE_CAPTION: Final = re.compile(r"^그림\s+\d+")

# Table caption: starts "표 " followed by a digit
_RE_TABLE_CAPTION: Final = re.compile(r"^표\s+\d+")

# Running chapter header: "제N장 …" (standalone line)
_RE_RUNNING_HEADER: Final = re.compile(r"^제\d+장\s")

# 연습문제 block start — heading variants (same as examen cleaner)
_RE_EXERCISE_START: Final = re.compile(
    r"^[\s■□▶◆●○\[\(]*"          # leading decoration / opening bracket
    r"연습\s*문제"                  # "연습문제" or "연습 문제"
    r"\s*[:\-–—\]\)]*"             # trailing colon / dash / closing bracket
    r"\s*(?:\([0-9가-힣\s]+\))?"   # optional "(N문항)" tail
    r"\s*$"
)

# 참고문헌 section start
_RE_REFERENCE_START: Final = re.compile(r"^참고문헌")

# Footnote marker line: †, *, ※ at start
_RE_FOOTNOTE_LINE: Final = re.compile(r"^[†*※]")

# Allowed tokens in a spaced-letter header (single uppercase, digit, or symbol)
_SPACED_HEADER_ALLOWED_TOKENS: frozenset[str] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789&%"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_spaced_letter_header(stripped: str) -> bool:
    """Return True if ``stripped`` looks like a spaced-letter header.

    A spaced-letter header is a line where every whitespace-delimited token is
    at most two characters drawn from uppercase letters, digits, or the symbols
    ``&`` / ``%``, AND there are at least 3 such tokens (to avoid false
    positives on short section labels).  The ≤2-char allowance lets a trailing
    chapter number ride along, e.g. the ``10`` in "C H A P T E R  10".

    Examples::

        "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y"  → True
        "C H A P T E R  10"                                   → True
        "A"                                                    → False (< 3 tokens)
        "갑상샘"                                                → False
    """
    tokens = stripped.split()
    if len(tokens) < 3:
        return False
    return all(
        len(t) <= 2 and all(ch in _SPACED_HEADER_ALLOWED_TOKENS for ch in t)
        for t in tokens
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clean_textbook(
    lines: list[str],
) -> tuple[list[tuple[int, str]], list[str]]:
    """Remove textbook noise from a list of raw lines.

    The function is stateless and deterministic: identical input always produces
    identical output.  It never raises on valid input; ambiguous lines that
    match no rule are silently kept (the caller may treat zero removed_spans as
    a signal that no cleaning was needed).

    Original line numbers (1-based) are preserved in both the kept list and the
    removed_spans audit entries.  This ensures that downstream evidence anchoring
    (T022) can always map a kept or removed line back to its position in the
    original file, and that char offsets can be reconstructed by the caller
    (offset of line N = sum of len(line_k)+1 for k in 1..N-1).

    Args:
        lines: Raw lines from a PDF-extracted textbook ``.txt`` file.  The list
            is 0-indexed on input; returned line numbers are 1-based, so
            ``lines[0]`` maps to lineno 1, ``lines[i]`` to lineno ``i + 1``.

    Returns:
        A 2-tuple of:
        - kept: ``list[tuple[int, str]]`` — ``(1-based_lineno, text)`` for
          every line that survived cleaning.
        - removed_spans: ``list[str]`` — human-readable audit log of every
          removed region, one entry per distinct noise span.  Format:
          ``"[reason] line <N>: '<text>'"`` for single lines, or
          ``"[reason] lines <start>–<end>: '<head_text>' … (K lines)"``
          for multi-line blocks.
    """
    if not lines:
        return [], []

    kept: list[tuple[int, str]] = []
    removed_spans: list[str] = []

    n = len(lines)

    # Pass 1: identify terminal block start (연습문제 / 참고문헌).
    # The FIRST occurrence causes everything from that line onwards to be
    # removed (chapter-level blocks always end the file).
    terminal_start: int | None = None  # 1-based
    terminal_reason: str | None = None

    for i, line in enumerate(lines):
        lineno = i + 1
        stripped = line.strip()
        if _RE_EXERCISE_START.match(stripped):
            terminal_start = lineno
            terminal_reason = "연습문제"
            break
        if _RE_REFERENCE_START.match(stripped):
            terminal_start = lineno
            terminal_reason = "참고문헌"
            break

    # Log the terminal block as a single removed span
    if terminal_start is not None:
        end_lineno = n
        removed_spans.append(
            f"[{terminal_reason}/exercise_block] "
            f"lines {terminal_start}–{end_lineno}: "
            f"'{lines[terminal_start - 1].strip()}' … "
            f"({end_lineno - terminal_start + 1} lines)"
        )

    # Pass 2: line-by-line classification
    for i, line in enumerate(lines):
        lineno = i + 1
        stripped = line.strip()

        # Skip terminal block lines
        if terminal_start is not None and lineno >= terminal_start:
            continue

        # Blank lines — keep (preserve structure)
        if stripped == "":
            kept.append((lineno, line))
            continue

        # Rule 1: spaced-letter header
        if _is_spaced_letter_header(stripped):
            removed_spans.append(f"[spaced_header] line {lineno}: '{stripped}'")
            continue

        # Rule 2: running chapter header (제N장 …)
        if _RE_RUNNING_HEADER.match(stripped):
            removed_spans.append(f"[running_header] line {lineno}: '{stripped}'")
            continue

        # Rule 3: standalone page number
        if _RE_PAGE_NUMBER.match(stripped):
            removed_spans.append(f"[page_number] line {lineno}: '{stripped}'")
            continue

        # Rule 4: figure caption
        if _RE_FIGURE_CAPTION.match(stripped):
            removed_spans.append(
                f"[figure_caption/그림] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 5: table caption
        if _RE_TABLE_CAPTION.match(stripped):
            removed_spans.append(
                f"[table_caption/표] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 6: footnote marker line
        if _RE_FOOTNOTE_LINE.match(stripped):
            removed_spans.append(f"[footnote/각주] line {lineno}: '{stripped}'")
            continue

        # No rule matched — keep the line
        kept.append((lineno, line))

    return kept, removed_spans


__all__ = ["clean_textbook"]
