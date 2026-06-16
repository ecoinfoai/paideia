"""T022 — Evidence index: groundedness authority (FR-003 / SC-007, R6).

Given a search term, return a
:class:`paideia_shared.schemas.MaieuticaTextbookEvidence` whose ``char_start``
/ ``char_end`` index the **ORIGINAL** newline-joined textbook file (not the
cleaned text).  If the term is absent the evidence has ``status="미확인"``.

OFFSET TRAP (from ingest review — critical)
-------------------------------------------
Original char offsets are computed from the FULL original line list together
with each line's ORIGINAL 1-based line number::

    char_start(N) = sum(len(line_k) + 1 for k in 1..N-1)

The ``+ 1`` accounts for the newline separator of the original
newline-joined file.  Offsets are **never** derived from the cleaned
``TextbookChunk.text`` alone — those would be short by the byte length of any
earlier lines the cleaner stripped.  ``removed_spans`` are audit-only and are
not an offset source.

This mirrors ``examen.silver.evidence_index.EvidenceIndex.from_chapter``: the
index re-anchors against the original lines so groundedness positions stay
valid even after cleaning.

Usage::

    from maieutica.silver.chunk import chunk_chapter
    from maieutica.silver.evidence_index import EvidenceIndex

    chunks = chunk_chapter(lines=raw_lines, ...)
    idx = EvidenceIndex.from_chapter(
        lines=raw_lines, chunks=chunks, source_file="8장 호흡계통.txt"
    )
    ev = idx.lookup("폐포")   # MaieuticaTextbookEvidence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import accumulate

from paideia_shared.schemas import MaieuticaTextbookEvidence, TextbookChunk


@dataclass
class EvidenceIndex:
    """Searchable index anchoring terms at ORIGINAL char offsets.

    Built via :meth:`from_chapter`.  Stores the original lines (1-based) so any
    match can be mapped back to its exact byte position in the original
    newline-joined file, and the owning chunk located by line range.

    Attributes:
        source_file: Basename of the source file (authority).
        _lines: ``(1-based lineno, text)`` for every original line (incl.
            blanks).
        _chunks: The chapter's chunks (used to attach the owning ``chunk_id``).
        _line_char_start: 0-based char offset of each line in the original
            newline-joined text, indexed by ``lineno - 1``.
    """

    source_file: str
    _lines: list[tuple[int, str]] = field(default_factory=list, repr=False)
    _chunks: list[TextbookChunk] = field(default_factory=list, repr=False)
    _line_char_start: list[int] = field(default_factory=list, repr=False)

    @classmethod
    def from_chapter(
        cls,
        lines: list[str],
        *,
        chunks: list[TextbookChunk],
        source_file: str,
    ) -> EvidenceIndex:
        """Build an index from the ORIGINAL lines and the chapter chunks.

        Args:
            lines: 0-indexed ORIGINAL string lines (BEFORE cleaning).  Line N
                (1-based) is ``lines[N - 1]``.
            chunks: Chunks for the same chapter (their ORIGINAL line ranges map
                a hit to its owning ``chunk_id``).
            source_file: Basename of the source file (used in evidence records).

        Returns:
            A populated :class:`EvidenceIndex`.

        Raises:
            TypeError: If ``lines`` is not a list of ``str`` (fail-fast guard
                against accidentally passing the ``(lineno, text)`` form).
        """
        if lines and not isinstance(lines[0], str):
            raise TypeError(
                "EvidenceIndex.from_chapter expects list[str] for `lines`; got "
                f"an element of type {type(lines[0]).__name__!r}."
            )
        idx = cls(source_file=source_file)
        idx._lines = [(i + 1, line) for i, line in enumerate(lines)]
        idx._chunks = list(chunks)
        # Char offset of line N (1-based) = sum(len(line_k) + 1 for k < N).
        # accumulate over (len + 1), prefixed with 0 for the first line.
        idx._line_char_start = [0, *accumulate(len(line) + 1 for line in lines)][: len(lines)]
        return idx

    def _chunk_id_for_line(self, lineno: int) -> str | None:
        """Return the chunk_id whose ORIGINAL line range covers ``lineno``."""
        for chunk in self._chunks:
            if chunk.line_start <= lineno <= chunk.line_end:
                return chunk.chunk_id
        return None

    @staticmethod
    def _line_matches_scoped(text: str, term: str) -> bool:
        """Two-direction substring match for the scoped ``lookup`` mode.

        ``term`` (the answer-point evidence) may be a verbatim textbook line OR
        a longer sentence quoting one, so match in either direction.

        Args:
            text: The candidate original line's text.
            term: The search term.

        Returns:
            ``True`` when ``term`` contains, or is contained by, ``text``.
        """
        # The `stripped and` guard excludes blank lines: an empty string is a
        # substring of EVERY term, so without it every blank line would match.
        stripped = text.strip()
        return term in text or (bool(stripped) and stripped in term)

    def lookup(self, term: str, *, chunk_id: str | None = None) -> MaieuticaTextbookEvidence:
        """Locate ``term`` and return its groundedness evidence.

        Two match modes by line, both scanning in ascending line order and
        returning the FIRST hit:

        - **Whole-index** (``chunk_id is None``, legacy/default): the first
          original line that CONTAINS ``term`` as a substring is the hit.
        - **Scoped** (``chunk_id`` given): only original lines whose owning
          chunk equals ``chunk_id`` (by the chunk's ``[line_start, line_end]``)
          are considered, and the match is **two-direction substring** —
          ``term in line.text`` OR (``line.text.strip()`` non-empty AND
          ``line.text.strip() in term``).  This is robust to the answer-point
          evidence being phrased either as a verbatim textbook line or as a
          longer sentence that quotes a textbook line.

        ``found_text`` is the full text of the hit line; ``char_start`` /
        ``char_end`` index the ORIGINAL newline-joined file so that
        ``original_text[char_start:char_end] == found_text``.

        Args:
            term: The key search term.
            chunk_id: When set, restrict matching to lines owned by this chunk
                and use the two-direction substring rule above; the returned
                evidence's ``chunk_id`` is therefore always this value on a hit.

        Returns:
            ``MaieuticaTextbookEvidence`` with ``status="확인"`` when found
            (chunk_id + char range + found_text), otherwise ``status="미확인"``
            (chunk_id / offsets left ``None``, search_term preserved).
        """
        scoped = chunk_id is not None
        for lineno, text in self._lines:
            owning_chunk_id = self._chunk_id_for_line(lineno)
            if scoped:
                if owning_chunk_id != chunk_id:
                    continue
                if not self._line_matches_scoped(text, term):
                    continue
            else:
                if term not in text:
                    continue
                if owning_chunk_id is None:
                    # Hit lies outside every chunk's body range (e.g. removed
                    # TOC/noise region) — not a citable, grounded passage.
                    continue
            char_start = self._line_char_start[lineno - 1]
            char_end = char_start + len(text)
            return MaieuticaTextbookEvidence(
                chunk_id=owning_chunk_id,
                source_file=self.source_file,
                char_start=char_start,
                char_end=char_end,
                line=lineno,
                found_text=text,
                search_term=term,
                status="확인",
            )

        return MaieuticaTextbookEvidence(
            source_file=self.source_file,
            search_term=term,
            status="미확인",
        )


__all__ = ["EvidenceIndex"]
