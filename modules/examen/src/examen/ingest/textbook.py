"""T022 — Textbook chapter loader + chapter-file existence verification.

Provides two public functions:

``load_chapter(path) -> list[tuple[int, str]]``
    Read a textbook .txt file and return its lines as 1-based
    ``(lineno, text)`` pairs.  Line numbers are ORIGINAL (never renumbered)
    so they serve as the groundedness anchor for evidence retrieval.

``verify_chapter_files(curriculum_map, bronze_dir) -> None``
    Check that every distinct ``chapter_no`` declared in *curriculum_map*
    has a matching ``.txt`` file inside *bronze_dir*.  Matching rule:
    the filename must contain ``"N장"`` where N is the chapter number
    (lenient — covers "8장 호흡계통.txt", "8장.txt", "ch8.txt" variant via
    the numeric prefix rule).  Raises ``FileNotFoundError`` mentioning the
    missing chapter number if any file is absent (the CLI maps this to
    exit code 2).
"""

from __future__ import annotations

import re
from pathlib import Path

from paideia_shared.schemas import CurriculumMap


def load_chapter(path: Path) -> list[tuple[int, str]]:
    """Read a textbook chapter file and return 1-based (lineno, text) pairs.

    Original line numbers are PRESERVED — no renumbering occurs.  Blank
    lines are included so that the line-number anchor is valid for every
    position in the file.

    Args:
        path: Path to the .txt file.

    Returns:
        List of ``(lineno, text)`` where ``lineno`` starts at 1.

    Raises:
        FileNotFoundError: If ``path`` does not exist.  Message includes
            the full path for fail-fast debugging.
    """
    if not path.exists():
        raise FileNotFoundError(f"Textbook chapter file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    # Split on newlines only; do NOT strip trailing newline to preserve count
    lines = raw.split("\n")
    # If the file ends with a newline, split produces an extra empty string —
    # drop it only if it's the last element and the raw text ended with "\n".
    if raw.endswith("\n") and lines and lines[-1] == "":
        lines = lines[:-1]
    return [(i + 1, line) for i, line in enumerate(lines)]


# ---------------------------------------------------------------------------
# Chapter-file matching
# ---------------------------------------------------------------------------


def _chapter_file_pattern(chapter_no: int) -> re.Pattern[str]:
    """Return a compiled regex that matches a filename for *chapter_no*.

    Matching strategy (lenient, config-independent): the stem must contain
    the token ``{N}장`` where ``N`` is the chapter number, with ``N`` not
    immediately preceded by another digit.  Examples (chapter_no=8):

    - "8장 호흡계통"  → match
    - "8장"          → match
    - "18장"         → NO match (the leading ``1`` is a digit before ``8장``)

    Real course files always use the ``장`` token, so digit-only stems like
    "8.txt" or "08.txt" are intentionally NOT matched (out of scope).
    """
    n = str(chapter_no)
    # N장 token (preceded by start-of-string or a non-digit) → matches
    # "8장"/"10장" without colliding with "18장".
    return re.compile(rf"(?:^|(?<=\D)){re.escape(n)}장")


def _find_chapter_file(bronze_dir: Path, chapter_no: int) -> Path | None:
    """Return the first .txt file in *bronze_dir* matching *chapter_no*, or None."""
    pattern = _chapter_file_pattern(chapter_no)
    for p in sorted(bronze_dir.glob("*.txt")):
        if pattern.search(p.stem):
            return p
    return None


def verify_chapter_files(
    curriculum_map: CurriculumMap,
    bronze_dir: Path,
) -> None:
    """Verify that every declared chapter has a matching .txt file.

    Iterates over the *unique* set of ``chapter_no`` values in
    ``curriculum_map.entries``.  For each, calls :func:`_find_chapter_file`.
    If any chapter is unmatched, raises :class:`FileNotFoundError` with a
    message that includes the missing chapter number and the directory
    searched.

    This is a fail-fast check (constitution III); the CLI maps the raised
    exception to exit code 2.

    Args:
        curriculum_map: Validated CurriculumMap from config.
        bronze_dir: Directory containing textbook .txt files.

    Raises:
        FileNotFoundError: If any declared chapter has no matching file.
            Message includes the chapter number and directory.
    """
    seen: set[int] = set()
    missing: list[int] = []

    for entry in curriculum_map.entries:
        chapter_no = entry.chapter_no
        if chapter_no in seen:
            continue
        seen.add(chapter_no)
        if _find_chapter_file(bronze_dir, chapter_no) is None:
            missing.append(chapter_no)

    if missing:
        missing_str = ", ".join(str(n) for n in sorted(missing))
        raise FileNotFoundError(
            f"Missing textbook files for chapter(s) {missing_str} "
            f"in '{bronze_dir}'.  Expected filenames containing 'N장' "
            f"(e.g. '{missing[0]}장 교재제목.txt')."
        )


__all__ = ["load_chapter", "verify_chapter_files"]
