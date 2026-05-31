"""T022 — Evidence index for groundedness verification.

The EvidenceIndex maps a search term to a list of hits in the *original*
(uncleaned) textbook lines.  Later sub-units (US1-c groundedness
verification) use this index to confirm that generated exam items cite
passage locations that actually appear in the source file.

The index is built from the raw lines (before cleaning) so that every
position in the original file is addressable — this is intentional.
Clean text is used for *generation*; original text is used for *citation*.

Usage::

    from examen.silver.evidence_index import EvidenceIndex, EvidenceHit

    idx = EvidenceIndex.build(lines, source_file="8장 호흡계통.txt")
    hits = idx.search("폐포")
    # hits: list[EvidenceHit]
    for h in hits:
        print(h.line_no, h.found_text)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceHit:
    """A single line that contains the search term.

    Attributes:
        source_file: Filename of the source .txt (not a full path — the
            basename is stored so the index is relocatable).
        line_no: 1-based original line number in *source_file*.
        found_text: The full text of the line containing the match.
    """

    source_file: str
    line_no: int
    found_text: str


@dataclass
class EvidenceIndex:
    """Searchable index over original textbook lines.

    Built via :meth:`build`.  Stores lines in insertion order so that
    ``search`` results are ordered by ascending line number.

    Attributes:
        source_file: Filename this index was built from.
        _lines: Internal list of ``(1-based lineno, text)`` for every line,
            including blanks.
    """

    source_file: str
    _lines: list[tuple[int, str]] = field(default_factory=list, repr=False)

    @classmethod
    def build(
        cls,
        lines: list[str],
        *,
        source_file: str,
    ) -> EvidenceIndex:
        """Build an EvidenceIndex from a list of raw string lines.

        Line numbers are assigned by position (1-based ``enumerate``).  Use
        this when you have the plain ``list[str]`` form (e.g. the result of
        ``Path.read_text().split("\\n")``).  If you already have the
        ``(lineno, text)`` tuple form produced by
        :func:`examen.ingest.textbook.load_chapter`, call
        :meth:`from_chapter` instead — passing tuples here is a type error
        that would otherwise silently corrupt line numbers.

        Args:
            lines: 0-indexed raw string lines from the original file (BEFORE
                any cleaning step).
            source_file: Basename of the source file (used in hit records).

        Returns:
            A populated EvidenceIndex.

        Raises:
            TypeError: If ``lines`` is not a list of ``str`` (fail-fast guard
                against accidentally passing the ``load_chapter`` tuple form).
        """
        # Fail-fast: reject the (lineno, text) tuple shape so a caller can't
        # silently get wrong line numbers (matters for T027 groundedness).
        if lines and not isinstance(lines[0], str):
            raise TypeError(
                "EvidenceIndex.build expects list[str]; got an element of "
                f"type {type(lines[0]).__name__!r}.  If you have the "
                "(lineno, text) form from load_chapter, use "
                "EvidenceIndex.from_chapter() instead."
            )
        idx = cls(source_file=source_file)
        idx._lines = [(i + 1, line) for i, line in enumerate(lines)]
        return idx

    @classmethod
    def from_chapter(
        cls,
        numbered_lines: list[tuple[int, str]],
        *,
        source_file: str,
    ) -> EvidenceIndex:
        """Build an EvidenceIndex directly from ``load_chapter`` output.

        This is the type-safe bridge between
        :func:`examen.ingest.textbook.load_chapter` (which returns
        ``list[tuple[int, str]]`` with ORIGINAL 1-based line numbers) and the
        evidence index.  The original line numbers are preserved verbatim —
        no renumbering — so groundedness anchors stay valid (T027).

        Args:
            numbered_lines: ``(1-based lineno, text)`` pairs, as returned by
                ``load_chapter``.
            source_file: Basename of the source file (used in hit records).

        Returns:
            A populated EvidenceIndex preserving the supplied line numbers.

        Raises:
            TypeError: If an element is not a ``(int, str)`` pair (fail-fast).
        """
        idx = cls(source_file=source_file)
        validated: list[tuple[int, str]] = []
        for item in numbered_lines:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], int)
                or not isinstance(item[1], str)
            ):
                raise TypeError(
                    "EvidenceIndex.from_chapter expects list[tuple[int, str]] "
                    f"(load_chapter output); got element {item!r}."
                )
            validated.append(item)
        idx._lines = validated
        return idx

    def search(self, term: str) -> list[EvidenceHit]:
        """Return all lines that contain *term* as a substring.

        The search is a plain substring match (``term in text``).  Korean
        text is case-invariant in practice; no normalisation is applied so
        the results are fully deterministic.

        Args:
            term: The search string.  Empty string matches all lines.

        Returns:
            Ordered list of :class:`EvidenceHit` (ascending line number).
            Empty list if no matches.
        """
        hits: list[EvidenceHit] = []
        for lineno, text in self._lines:
            if term in text:
                hits.append(
                    EvidenceHit(
                        source_file=self.source_file,
                        line_no=lineno,
                        found_text=text,
                    )
                )
        return hits


__all__ = ["EvidenceHit", "EvidenceIndex"]
