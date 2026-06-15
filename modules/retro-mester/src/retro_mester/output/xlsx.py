"""T028 — Gold-layer xlsx writer for retro-mester.

Entry point: ``write_xlsx(gaps, recs, xlsx_path, when)``.

Sheets:
- ``빈틈``       — one row per UnitGap.
- ``변경권고``   — one row per ChangeRecommendation.

Determinism:
- Row order: gaps sorted by (chapter, segment); recs by (rank nulls-last,
  chapter, segment).
- Workbook creator / lastModifiedBy pinned to ``_PRODUCER``.
- ``finalize_xlsx(xlsx_path, when)`` rewrites ``<dcterms:modified>`` and
  ``<dcterms:created>`` post-save for byte-identical output.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from paideia_shared.schemas.change_recommendation import ChangeRecommendation
from paideia_shared.schemas.unit_gap import UnitGap

from retro_mester.output.determinism import finalize_xlsx

_PRODUCER = "paideia/retro-mester/0.1.0"

# Column orders are derived from the model field order for predictability.
_GAP_COLUMNS: list[str] = [
    "semester",
    "course_slug",
    "chapter",
    "segment",
    "segment_mean_rate",
    "n_below",
    "pct_segment",
    "pct_cohort",
    "is_structural",
    "cohort_failing_item_types",
    "cause",
    "cause_signals",
    "validity",
    "unit_importance",
    "weight",
    "impact_score",
    "evidence_n",
]

_REC_COLUMNS: list[str] = [
    "semester",
    "course_slug",
    "rank",
    "chapter",
    "target_cognitive_level",
    "segment",
    "cause_hypothesis",
    "covered_n",
    "covered_pct_segment",
    "covered_pct_cohort",
    "unit_importance",
    "weight",
    "impact_score",
    "effort_level",
    "priority_quadrant",
    "prescription_key",
    "cluster_vocab",
    "validity",
    "is_covered",
]


def _build_gap_sheet(wb: Workbook, gaps: list[UnitGap]) -> None:
    ws = wb.create_sheet("빈틈")
    bold = Font(bold=True)

    # Header row
    for c, col in enumerate(_GAP_COLUMNS, start=1):
        ws.cell(1, c, col).font = bold

    # Sort gaps: chapter ASC, segment ASC
    sorted_gaps = sorted(gaps, key=lambda g: (g.chapter, g.segment))
    for r, gap in enumerate(sorted_gaps, start=2):
        row_dict = gap.model_dump()
        for c, col in enumerate(_GAP_COLUMNS, start=1):
            value = row_dict[col]
            # List/dict columns: convert to str for readability in xlsx
            if isinstance(value, (list, dict)):
                value = str(value)
            ws.cell(r, c, value)


def _build_rec_sheet(wb: Workbook, recs: list[ChangeRecommendation]) -> None:
    ws = wb.create_sheet("변경권고")
    bold = Font(bold=True)

    # Header row
    for c, col in enumerate(_REC_COLUMNS, start=1):
        ws.cell(1, c, col).font = bold

    # Sort recs: rank (None last) ASC, chapter ASC, segment ASC
    sorted_recs = sorted(
        recs,
        key=lambda r: (r.rank if r.rank is not None else 999, r.chapter, r.segment),
    )
    for row_idx, rec in enumerate(sorted_recs, start=2):
        row_dict = rec.model_dump()
        for c, col in enumerate(_REC_COLUMNS, start=1):
            ws.cell(row_idx, c, row_dict[col])


def write_xlsx(
    gaps: list[UnitGap],
    recs: list[ChangeRecommendation],
    xlsx_path: Path,
    when: datetime.datetime,
) -> None:
    """Write ``빈틈`` and ``변경권고`` sheets to ``xlsx_path``.

    Never calls ``datetime.now()`` internally.  ``finalize_xlsx`` is
    called after ``save()`` to pin ``<dcterms:modified>`` and
    ``<dcterms:created>`` so two runs with the same ``when`` produce
    byte-identical files.

    Args:
        gaps: List of UnitGap records.
        recs: List of ChangeRecommendation records.
        xlsx_path: Destination ``.xlsx`` path. Parent directory must exist.
        when: Timestamp for workbook metadata and determinism pin.

    Raises:
        FileNotFoundError: When ``xlsx_path.parent`` does not exist.
    """
    xlsx_path = Path(xlsx_path)
    if not xlsx_path.parent.is_dir():
        raise FileNotFoundError(
            f"write_xlsx: parent directory missing: {xlsx_path.parent}"
        )

    wb = Workbook()
    # Drop the default active sheet so tab order matches spec exactly.
    default = wb.active
    if default is not None:
        wb.remove(default)

    _build_gap_sheet(wb, gaps)
    _build_rec_sheet(wb, recs)

    # Pin workbook-level metadata
    wb.properties.creator = _PRODUCER
    wb.properties.lastModifiedBy = _PRODUCER
    wb.properties.created = when
    wb.properties.modified = when

    wb.save(xlsx_path)

    # Rewrite <dcterms:modified> + <dcterms:created> after save() stamps
    # them with datetime.now() — ensures byte-identical output.
    finalize_xlsx(xlsx_path, when)


__all__ = ["write_xlsx"]
