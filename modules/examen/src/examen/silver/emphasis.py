"""T056/T057/T058 — Lecture-emphasis aggregation (US7, enrichment).

Builds the keyword dictionary, aggregates per-section emphasis across the
available class sections (4-class intersection, missing sessions excluded), and
labels :class:`ExamItemDraft` items with the resulting emphasis flag + class
count.  All operations are fully deterministic (keyword substring counting; no
LLM, no randomness) per research R5.

Public functions
----------------
``build_keyword_dict(curriculum_map, config=None)``
    Derive a ``(chapter_no, section) -> [keywords]`` map from the curriculum's
    section titles; an optional ``config`` supplements/overrides it.

``aggregate_emphasis(scan, curriculum_map, keyword_dict, *, semester, course_slug)``
    Per curriculum section, intersect the available classes that emphasized it
    (any keyword appears in that class's concatenated week transcript) →
    :class:`EmphasisCell`.

``label_items_with_emphasis(items, cells, keyword_dict)``
    Stamp each item's ``is_emphasized`` / ``emphasis_class_count`` from the
    matching cell (section-level, falling back to chapter-level); degrade to a
    no-op when ``cells`` is empty.

Scope / deferral
----------------
FR-025 also calls for emphasis to feed "출제 우선순위에 반영" — i.e. into slot
SELECTION (which textbook sections become items).  That solver-level priority is
intentionally NOT implemented in US7: changing slot selection would destabilise
the already-green plan/solver test suite, and the constitution prioritises
deterministic completion over enrichment.  Instead, US7 labels generated items
with the emphasis flag/count and records the aggregation summary in the manifest
+ Silver ``emphasis.yaml``, so the human-reviewed draft and downstream immersio
can act on emphasis.  Wiring emphasis into solver section-priority is deferred to
a later iteration.
"""

from __future__ import annotations

import re

from paideia_shared.schemas import (
    CurriculumMap,
    EmphasisCell,
    ExamItemDraft,
)

from examen.ingest.stt import SttScan

# Leading "N." / "N)" / "N " numeric section-prefix to strip from a title.
_SECTION_PREFIX_RE = re.compile(r"^\s*\d+\s*[.)]?\s*")

_MAX_CLASSES = 4  # EmphasisCell counts are capped 0..4.


def _strip_section_prefix(section: str) -> str:
    """Remove a leading ``"N. "``-style numeric prefix from a section title."""
    return _SECTION_PREFIX_RE.sub("", section).strip()


def build_keyword_dict(
    curriculum_map: CurriculumMap,
    config: dict | None = None,
) -> dict[tuple[int, str], list[str]]:
    """Build a ``(chapter_no, section) -> [keywords]`` dictionary.

    Default derivation: for each :class:`CurriculumEntry` section title, strip a
    leading ``"N. "`` numeric prefix and use the remaining title as a keyword,
    plus every whitespace-split token of length ≥ 2.  Keywords are
    deduplicated while preserving first-seen order.

    Config shape (optional supplement/override)::

        {
            chapter_no: {           # int
                section: [kw, ...]  # section title (str) -> extra keywords
            }
        }

    Keywords from ``config`` are appended to the derived list for the matching
    ``(chapter_no, section)`` key (creating the key if absent).  This is purely
    additive and deterministic.

    Args:
        curriculum_map: The validated curriculum map.
        config: Optional nested mapping of supplemental keywords.

    Returns:
        Mapping from ``(chapter_no, section)`` to an ordered, de-duplicated list
        of keyword strings.
    """
    result: dict[tuple[int, str], list[str]] = {}

    for entry in curriculum_map.entries:
        for section in entry.sections:
            key = (entry.chapter_no, section)
            kws: list[str] = result.setdefault(key, [])
            title = _strip_section_prefix(section)
            candidates: list[str] = []
            if title:
                candidates.append(title)
            candidates.extend(tok for tok in title.split() if len(tok) >= 2)
            for kw in candidates:
                if kw and kw not in kws:
                    kws.append(kw)

    if config:
        for chapter_no, sections in config.items():
            if not isinstance(sections, dict):
                continue
            for section, extra in sections.items():
                key = (int(chapter_no), section)
                kws = result.setdefault(key, [])
                for kw in extra:
                    if kw and kw not in kws:
                        kws.append(kw)

    return result


def aggregate_emphasis(
    scan: SttScan,
    curriculum_map: CurriculumMap,
    keyword_dict: dict[tuple[int, str], list[str]],
    *,
    semester: str,
    course_slug: str,
) -> list[EmphasisCell]:
    """Aggregate per-section emphasis into :class:`EmphasisCell` rows.

    For each curriculum (week, chapter_no, section):

    - ``classes_with_data`` = classes having ≥1 session that week.
    - ``available_class_count`` = ``min(4, len(classes_with_data))``.
    - A class "emphasizes" the section if ANY keyword for
      ``(chapter_no, section)`` appears (substring) in the concatenation of all
      that class's week sessions' text.
    - ``emphasized_class_count`` = ``min(available, #emphasizing classes)``.
    - ``is_emphasized`` = ``emphasized == available and available > 0`` (the
      4-class intersection; EmphasisCell invariant V2).

    A section taught across multiple weeks (same chapter_no) is unioned across
    those weeks: a class counts as having data if it taught ANY of the weeks,
    and emphasizes if any keyword appears in ANY of its sessions across those
    weeks.

    Empty scan (no sessions) → ``[]`` (degrade).

    Args:
        scan: The STT scan result.
        curriculum_map: The validated curriculum map.
        keyword_dict: Output of :func:`build_keyword_dict`.
        semester: Semester code for the EmphasisCell rows.
        course_slug: Course slug for the EmphasisCell rows.

    Returns:
        List of :class:`EmphasisCell`, sorted by ``(chapter_no, section)``.
    """
    if not scan.sessions:
        return []

    # (chapter_no, section) -> set of weeks teaching it.
    section_weeks: dict[tuple[int, str], set[int]] = {}
    for entry in curriculum_map.entries:
        for section in entry.sections:
            section_weeks.setdefault((entry.chapter_no, section), set()).add(entry.week)

    # Group session text by (class_id, week).
    by_class_week: dict[tuple[str, int], list] = {}
    for s in scan.sessions:
        by_class_week.setdefault((s.class_id, s.week), []).append(s)

    cells: list[EmphasisCell] = []
    for (chapter_no, section), weeks in sorted(
        section_weeks.items(), key=lambda kv: (kv[0][0], kv[0][1])
    ):
        keywords = keyword_dict.get((chapter_no, section), [])

        # Classes that have data in ANY of the teaching weeks.
        classes_with_data = sorted(
            {
                cid
                for (cid, wk) in by_class_week
                if wk in weeks
            }
        )
        # The department teaches ≤4 sections (1A–1D), so len(classes_with_data)
        # is normally ≤4; the min() guards the EmphasisCell le=4 bound defensively
        # in case malformed input ever yields a 5th observed class id.
        available = min(_MAX_CLASSES, len(classes_with_data))

        emphasizing: list[str] = []
        evidence_refs: list[str] = []
        for class_id in classes_with_data:
            class_sessions = [
                sess
                for wk in weeks
                for sess in by_class_week.get((class_id, wk), [])
            ]
            matched = False
            for sess in class_sessions:
                for kw in keywords:
                    if kw and kw in sess.text:
                        evidence_refs.append(
                            f"{sess.class_id}/{sess.week}주차/{sess.session}차시:{kw}"
                        )
                        matched = True
            if matched:
                emphasizing.append(class_id)

        emphasized = min(available, len(emphasizing))
        is_emphasized = emphasized == available and available > 0

        cells.append(
            EmphasisCell(
                semester=semester,
                course_slug=course_slug,
                chapter_no=chapter_no,
                section=section,
                emphasized_class_count=emphasized,
                available_class_count=available,
                is_emphasized=is_emphasized,
                evidence_refs=sorted(set(evidence_refs)),
            )
        )

    return cells


def label_items_with_emphasis(
    items: list[ExamItemDraft],
    cells: list[EmphasisCell],
    keyword_dict: dict[tuple[int, str], list[str]],
) -> list[ExamItemDraft]:
    """Stamp items with ``is_emphasized`` / ``emphasis_class_count``.

    Resolution order per item:

    1. If ``cells`` is empty → return items unchanged (degrade path; fields stay
       ``None``).
    2. Determine the item's section: prefer ``item.section``; otherwise map
       ``item.key_concept`` via ``keyword_dict`` restricted to the item's
       ``chapter_no``.
    3. If a ``(chapter_no, section)`` cell exists → copy its flag + count.
    4. Else fall back to chapter-level: ``is_emphasized`` = any cell in that
       chapter is emphasized; ``emphasis_class_count`` = the max
       ``emphasized_class_count`` among that chapter's cells.  If the chapter has
       no cells, the item is left unchanged.

    The chapter-level coarsening (step 4) is an INTENTIONAL design choice: when an
    item cannot be pinned to a single section (no ``section`` and no
    ``key_concept`` match), attributing the chapter's strongest emphasis is a
    deliberate optimistic prior so the item still carries an enrichment signal
    rather than ``None``.  A chapter with no cells at all is left untouched
    (``None``, NOT ``False``) so "no signal" stays distinct from "not emphasized".

    Args:
        items: The exam items to label.
        cells: Aggregated EmphasisCell rows.
        keyword_dict: Output of :func:`build_keyword_dict` (for key_concept →
            section mapping).

    Returns:
        New list of items (frozen → ``model_copy``); unchanged items are
        returned as-is.
    """
    if not cells:
        return list(items)

    cell_by_key: dict[tuple[int, str], EmphasisCell] = {
        (c.chapter_no, c.section): c for c in cells
    }

    # chapter_no -> (is_emphasized_any, max_emphasized_count)
    chapter_summary: dict[int, tuple[bool, int]] = {}
    for c in cells:
        cur = chapter_summary.get(c.chapter_no, (False, 0))
        chapter_summary[c.chapter_no] = (
            cur[0] or c.is_emphasized,
            max(cur[1], c.emphasized_class_count),
        )

    # Reverse keyword -> (chapter_no, section) for key_concept resolution.
    # ``setdefault`` means a keyword shared by multiple sections in the same
    # chapter resolves to the FIRST-INSERTED section (curriculum entry order →
    # deterministic).
    keyword_to_key: dict[tuple[int, str], tuple[int, str]] = {}
    for (chapter_no, section), kws in keyword_dict.items():
        for kw in kws:
            keyword_to_key.setdefault((chapter_no, kw), (chapter_no, section))

    labeled: list[ExamItemDraft] = []
    for item in items:
        section = item.section
        if section is None and item.key_concept:
            # Try matching the key_concept against this chapter's keywords.
            for (chapter_no, kw), key in keyword_to_key.items():
                if chapter_no == item.chapter_no and kw and kw in item.key_concept:
                    section = key[1]
                    break

        cell = (
            cell_by_key.get((item.chapter_no, section))
            if section is not None
            else None
        )

        if cell is not None:
            labeled.append(
                item.model_copy(
                    update={
                        "is_emphasized": cell.is_emphasized,
                        "emphasis_class_count": cell.emphasized_class_count,
                    }
                )
            )
        elif item.chapter_no in chapter_summary:
            is_emph, count = chapter_summary[item.chapter_no]
            labeled.append(
                item.model_copy(
                    update={
                        "is_emphasized": is_emph,
                        "emphasis_class_count": count,
                    }
                )
            )
        else:
            labeled.append(item)

    return labeled


__all__ = [
    "build_keyword_dict",
    "aggregate_emphasis",
    "label_items_with_emphasis",
]
