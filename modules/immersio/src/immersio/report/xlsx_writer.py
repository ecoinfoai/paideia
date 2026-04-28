"""Quality-analysis xlsx writer (T045, FR-001/002, R-01).

Spec 004 contracts/xlsx_sheets.md §1-§6 — six sheets in this build:

  1. 전체요약          (13 indicator/value rows)
  2. 1_히스토그램       (구간_시작 / 구간_끝 / 도수 / 누적 / 누적_백분율)
  3. 2_메타데이터통계   (metadata_kind / value / n / mean / sd / test_kind /
                        test_p_value / levene_p_value / note)
  4. 3_변별력          (per-item discrimination + 판정 + 메타)
  5. 4_정답률          (per-item correct rate + 메타 + 정답·최다오답)
  6. 5_오답분석        (per-item label + 무응답률 + 인접 distractor 등)

The 7th legacy sheet (학생성적) is Phase 4's responsibility (T052) — it
is intentionally absent from this writer and added by an update path
later.

Determinism (FR-023 / R-10):
* ``Workbook.properties.creator`` and ``lastModifiedBy`` pinned to a
  fixed string so legacy/build-host metadata never leaks in.
* ``created`` / ``modified`` parsed from the operator's
  ``generated_at_utc`` argument — that string is a single source of
  truth shared by xlsx Producer, pdf CreationDate, and png Software.
* openpyxl's ``save()`` overwrites ``modified`` with ``datetime.now()``
  via ``openpyxl.writer.excel.write_root_rels`` neighbour code. We
  defeat this by monkey-patching ``datetime.datetime.now`` *inside the
  openpyxl.writer.excel namespace only* for the duration of the save
  call; the override is reverted in a ``try/finally`` so global state is
  never polluted. This keeps two consecutive calls byte-identical
  (verified by T030).
"""

from __future__ import annotations

import contextlib
import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.writer import excel as _openpyxl_excel
from paideia_shared.schemas import (
    HistogramBin,
    ItemStatistics,
    MetadataAggregate,
)

_PRODUCER = "paideia/immersio/0.1.0"


@contextlib.contextmanager
def _pin_openpyxl_now(when: datetime.datetime):
    """Monkey-patch ``openpyxl.writer.excel.datetime.datetime.now`` to ``when``.

    Restored on context exit even if ``Workbook.save()`` raises. ``when``
    is treated as UTC and any tzinfo is stripped so the patched ``now``
    matches openpyxl's expected ``datetime.datetime.now(tz=...).replace(
    tzinfo=None)`` shape.
    """
    pinned = when.replace(tzinfo=None) if when.tzinfo is not None else when

    class _PinnedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 — match openpyxl's call signature
            return pinned

    original = _openpyxl_excel.datetime.datetime
    _openpyxl_excel.datetime.datetime = _PinnedDateTime  # type: ignore[misc]
    try:
        yield
    finally:
        _openpyxl_excel.datetime.datetime = original  # type: ignore[misc]


def _parse_iso8601_utc(s: str) -> datetime.datetime:
    """Parse the manifest ISO8601 string into a tz-naive UTC datetime.

    openpyxl's ``properties.created`` setter strips tzinfo internally, so
    we hand it a naive datetime sourced from the explicit UTC ISO string.
    """
    if not isinstance(s, str) or not s:
        raise ValueError(f"generated_at_utc must be a non-empty string, got {s!r}")
    s_norm = s.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s_norm)
    except ValueError as exc:
        raise ValueError(
            f"generated_at_utc is not a valid ISO8601 string: {s!r}"
        ) from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def _stamp_workbook(wb: Workbook, semester: str, course_name_kr: str, when: datetime.datetime) -> None:
    wb.properties.creator = _PRODUCER
    wb.properties.lastModifiedBy = _PRODUCER
    wb.properties.created = when
    wb.properties.modified = when
    wb.properties.title = f"시험분석결과 — {semester} {course_name_kr}"


def _build_overall_sheet(wb: Workbook, rows: Sequence[Mapping[str, object]]) -> None:
    ws = wb.create_sheet("전체요약")
    bold = Font(bold=True)
    ws.cell(1, 1, "지표").font = bold
    ws.cell(1, 2, "값").font = bold
    for i, row in enumerate(rows, start=2):
        ws.cell(i, 1, row["지표"])
        ws.cell(i, 2, row["값"])


def _build_histogram_sheet(wb: Workbook, bins: Sequence[HistogramBin]) -> None:
    ws = wb.create_sheet("1_히스토그램")
    bold = Font(bold=True)
    headers = ("구간_시작", "구간_끝", "도수", "누적", "누적_백분율")
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h).font = bold
    for i, b in enumerate(bins, start=2):
        ws.cell(i, 1, b.bin_start)
        ws.cell(i, 2, b.bin_end)
        ws.cell(i, 3, b.count)
        ws.cell(i, 4, b.cumulative)
        ws.cell(i, 5, b.cumulative_pct)


def _build_metadata_sheet(wb: Workbook, rows: Sequence[MetadataAggregate]) -> None:
    ws = wb.create_sheet("2_메타데이터통계")
    bold = Font(bold=True)
    headers = (
        "metadata_kind", "metadata_value", "n", "mean", "sd",
        "test_kind", "test_p_value", "levene_p_value", "note",
    )
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h).font = bold
    for i, r in enumerate(rows, start=2):
        ws.cell(i, 1, r.metadata_kind)
        ws.cell(i, 2, r.metadata_value)
        ws.cell(i, 3, r.n)
        ws.cell(i, 4, r.mean)
        ws.cell(i, 5, r.sd)
        ws.cell(i, 6, r.test_kind)
        ws.cell(i, 7, r.test_p_value)
        ws.cell(i, 8, r.levene_p_value)
        ws.cell(i, 9, r.note)


def _verdict_for_discrimination(d: float) -> str:
    if d < 0:
        return "역변별"
    if d >= 0.40:
        return "우수"
    if d >= 0.30:
        return "양호"
    if d >= 0.20:
        return "보통"
    if d >= 0.10:
        return "개선필요"
    return "약함"


def _build_discrimination_sheet(wb: Workbook, items: Sequence[ItemStatistics]) -> None:
    ws = wb.create_sheet("3_변별력")
    bold = Font(bold=True)
    headers = (
        "문항번호", "정답률", "변별력지수", "점-이연_상관",
        "변별력_판정", "챕터", "문제유형", "난이도",
    )
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h).font = bold
    for i, it in enumerate(sorted(items, key=lambda x: x.item_no), start=2):
        ws.cell(i, 1, it.item_no)
        ws.cell(i, 2, it.correct_rate)
        ws.cell(i, 3, it.discrimination_index)
        ws.cell(i, 4, it.point_biserial)
        ws.cell(i, 5, _verdict_for_discrimination(it.discrimination_index))
        ws.cell(i, 6, it.chapter)
        ws.cell(i, 7, it.item_type)
        ws.cell(i, 8, it.difficulty_level)


def _build_correct_rate_sheet(wb: Workbook, items: Sequence[ItemStatistics]) -> None:
    ws = wb.create_sheet("4_정답률")
    bold = Font(bold=True)
    headers = (
        "문항번호", "정답률(%)", "챕터", "문제유형", "출처",
        "난이도", "예상_난이도", "정답번호", "최다오답번호",
        "최다오답률(%)", "무응답(%)",
    )
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h).font = bold
    for i, it in enumerate(sorted(items, key=lambda x: x.item_no), start=2):
        ws.cell(i, 1, it.item_no)
        ws.cell(i, 2, round(it.correct_rate * 100, 2))
        ws.cell(i, 3, it.chapter)
        ws.cell(i, 4, it.item_type)
        ws.cell(i, 5, it.source)
        ws.cell(i, 6, it.difficulty_level)
        ws.cell(i, 7, it.expected_difficulty)
        ws.cell(i, 8, it.correct_answer)
        ws.cell(i, 9, it.top_distractor_no)
        ws.cell(
            i, 10,
            round(it.top_distractor_rate * 100, 2) if it.top_distractor_rate is not None else None,
        )
        ws.cell(i, 11, round(it.omit_rate * 100, 2))


def _build_distractor_sheet(wb: Workbook, items: Sequence[ItemStatistics]) -> None:
    ws = wb.create_sheet("5_오답분석")
    bold = Font(bold=True)
    headers = (
        "문항번호", "정답률(%)", "변별력지수", "무응답률(%)",
        "최다오답번호", "최다오답률(%)", "인접_distractor",
        "distractor_label",
    )
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h).font = bold
    for i, it in enumerate(sorted(items, key=lambda x: x.item_no), start=2):
        ws.cell(i, 1, it.item_no)
        ws.cell(i, 2, round(it.correct_rate * 100, 2))
        cell_d = ws.cell(i, 3, it.discrimination_index)
        ws.cell(i, 4, round(it.omit_rate * 100, 2))
        ws.cell(i, 5, it.top_distractor_no)
        ws.cell(
            i, 6,
            round(it.top_distractor_rate * 100, 2) if it.top_distractor_rate is not None else None,
        )
        ws.cell(i, 7, "yes" if it.is_top_distractor_adjacent else "no")
        cell_label = ws.cell(i, 8, it.distractor_label)
        # Per US4 (T059), 변별력 < 0 행은 굵게 강조.
        if it.discrimination_index < 0:
            for c in range(1, 9):
                ws.cell(i, c).font = bold
        # Otherwise leave the cell defaults; only the header row + this row
        # carry styling so the xlsx remains visually scannable.
        _ = cell_d, cell_label  # references retained for clarity


def write_analysis_xlsx(
    *,
    output_path: Path,
    overall_rows: Sequence[Mapping[str, object]],
    histogram_bins: Sequence[HistogramBin],
    metadata_rows: Sequence[MetadataAggregate],
    item_stats: Iterable[ItemStatistics],
    semester: str,
    course_name_kr: str,
    generated_at_utc: str,
) -> None:
    """Write the 6-sheet ``시험분석결과.xlsx`` to ``output_path``.

    Args:
        output_path: Destination ``.xlsx`` path. Parent directory must
            exist; the function refuses to ``mkdir`` (fail-fast).
        overall_rows: 13-row payload from
            ``analysis.overall_summary.compute_overall_summary``.
        histogram_bins: List of ``HistogramBin`` from
            ``analysis.histogram.compute_score_histogram``.
        metadata_rows: List of ``MetadataAggregate`` from
            ``analysis.metadata_stats.compute_metadata_aggregates``.
        item_stats: Iterable of ``ItemStatistics`` from
            ``analysis.item_stats.compute_item_statistics``.
        semester: e.g. ``"2026-1"`` (used in workbook title).
        course_name_kr: e.g. ``"인체구조와기능"`` (used in workbook title).
        generated_at_utc: ISO8601 UTC timestamp pinning Workbook
            ``created``/``modified`` for byte-identical determinism.

    Raises:
        ValueError: When required inputs are empty / malformed.
        FileNotFoundError: When ``output_path.parent`` does not exist.
    """
    if not overall_rows:
        raise ValueError("write_analysis_xlsx: overall_rows is empty")
    items = list(item_stats)
    if not items:
        raise ValueError("write_analysis_xlsx: item_stats is empty")
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise FileNotFoundError(
            f"write_analysis_xlsx: parent directory missing: {output_path.parent}"
        )

    when = _parse_iso8601_utc(generated_at_utc)

    wb = Workbook()
    # Workbook() seeds a default 'Sheet' which we drop so the tab order
    # mirrors contracts/xlsx_sheets.md exactly.
    default = wb.active
    wb.remove(default)

    _build_overall_sheet(wb, overall_rows)
    _build_histogram_sheet(wb, histogram_bins)
    _build_metadata_sheet(wb, metadata_rows)
    _build_discrimination_sheet(wb, items)
    _build_correct_rate_sheet(wb, items)
    _build_distractor_sheet(wb, items)

    _stamp_workbook(wb, semester, course_name_kr, when)
    with _pin_openpyxl_now(when):
        wb.save(output_path)


__all__ = ["write_analysis_xlsx"]
