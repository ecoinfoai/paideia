"""T018 — Textbook chapter loader with original line-number preservation.

Provides one public function:

``load_chapter(path) -> list[tuple[int, str]]``
    Read a textbook ``.txt`` file and return its lines as 1-based
    ``(lineno, text)`` pairs.  Line numbers are ORIGINAL (never renumbered)
    so they serve as the groundedness anchor for evidence retrieval and for
    the char-offset audit in T019.

    Char-offset note
    ----------------
    The returned pairs carry no explicit char_offset field — the caller can
    always reconstruct the char offset of line N as::

        offset = sum(len(text_k) + 1 for k in range(1, N))

    where the ``+ 1`` accounts for the newline separator in the original
    newline-joined file.  T019's ``clean_textbook`` uses the lineno to anchor
    ``removed_spans`` entries; T022 uses the same lineno to anchor evidence.

Usage::

    from maieutica.ingest.textbook import load_chapter

    lines = load_chapter(Path("data/bronze/maieutica/2026-1-anatomy/8장 호흡계통.txt"))
    # lines[0] == (1, "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y")
    # lines[7] == (8, "코는 후각과 공기 가습을 담당한다.")
"""

from __future__ import annotations

from pathlib import Path


def load_chapter(path: Path) -> list[tuple[int, str]]:
    """Read a textbook chapter file and return 1-based (lineno, text) pairs.

    Original line numbers are PRESERVED — no renumbering occurs.  Blank lines
    are included so that the line-number anchor is valid for every position in
    the file (and char offsets computed from the pairs remain exact).

    A file that ends with a trailing newline produces the same line count as the
    number of logical lines (the final empty string from ``split("\\n")`` is
    discarded when the file ends with ``"\\n"``).

    Args:
        path: Path to the ``.txt`` file.

    Returns:
        List of ``(lineno, text)`` where ``lineno`` starts at 1.

    Raises:
        FileNotFoundError: If ``path`` does not exist. Message includes the
            full path for fail-fast debugging.
    """
    if not path.exists():
        raise FileNotFoundError(f"Textbook chapter file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    # Split on newlines only; do NOT strip trailing newline to preserve count.
    lines = raw.split("\n")
    # A file ending with "\n" yields a trailing empty string — drop it only
    # when the raw text actually ends with "\n" (preserves the correct count).
    if raw.endswith("\n") and lines and lines[-1] == "":
        lines = lines[:-1]

    return [(i + 1, line) for i, line in enumerate(lines)]


__all__ = ["load_chapter"]
