"""4-sheet xlsx workbook writer — US1 sheets `상관매트릭스` + `회귀결과` (T032).

FR-001 / FR-002 + research §R6 #4 + §R13 vector #5 (`<dcterms:modified>`
epoch pin + zip entry date_time fix). Phase 1+2 의 public
``rewrite_modified_in_zip`` 을 직접 후처리로 호출하여 byte-identical
재실행 보장.

Public:
- :func:`write_us1_xlsx(correlation_cells, regression_coefs,
  regression_fit, out_path)` — 2-sheet 워크북 (US2/US4 sheets 는 후속
  T041/T055 가 추가).

Sheets:
- `상관매트릭스`: header (8 columns) + 1 row per correlation cell
- `회귀결과`: 3-row fit summary block + blank row + coef table (header +
  8 axis rows + warnings sub-block)

Determinism:
- 행 정렬: caller 가 결정 (correlation 모듈은 STANDARD_AXIS_KEYS ×
  metric alphabetic; regression 은 STANDARD_AXIS_KEYS)
- ``<dcterms:modified>`` 후처리: Phase 1+2 ``rewrite_modified_in_zip``
  with epoch ``2000-01-01T00:00:00Z`` (research §R13 vector #5 정합)
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from immersio.report.xlsx_writer import rewrite_modified_in_zip

from paideia_shared.schemas import (
    CorrelationCell,
    RegressionCoefficient,
    RegressionFitSummary,
)

# Determinism vector #5 — fixed epoch (matches Phase 1+2 conventions).
_EPOCH_MODIFIED = datetime.datetime(
    2000, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
)

_CORRELATION_HEADERS = (
    "axis_key",
    "exam_metric_key",
    "n",
    "pearson_r",
    "raw_p",
    "fdr_q",
    "significant",
    "unstable_n_lt_20",
)

_REGRESSION_HEADERS = (
    "axis_key",
    "coef",
    "std_err",
    "t_stat",
    "raw_p",
    "fdr_q",
    "ci_low_95",
    "ci_high_95",
    "beta_standardized",
    "vif",
    "multicollinearity_flag",
)


def _build_correlation_sheet(
    wb: Workbook, cells: Sequence[CorrelationCell]
) -> None:
    sheet = wb.create_sheet("상관매트릭스")
    sheet.append(list(_CORRELATION_HEADERS))
    for c in cells:
        sheet.append(
            [
                c.axis_key,
                c.exam_metric_key,
                c.n,
                c.pearson_r,
                c.raw_p,
                c.fdr_q,
                c.significant_after_correction,
                c.unstable_inference_flag,
            ]
        )
    # Modest column widths so headers are visible without auto-fit.
    for i, _ in enumerate(_CORRELATION_HEADERS, start=1):
        sheet.column_dimensions[get_column_letter(i)].width = 16


def _build_regression_sheet(
    wb: Workbook,
    coefs: Sequence[RegressionCoefficient],
    fit: RegressionFitSummary,
) -> None:
    sheet = wb.create_sheet("회귀결과")

    # Block 1 — fit summary (3 rows: header label, fields, values).
    sheet.append(["적합 지표"])
    sheet.append(
        [
            "n_complete_case",
            "n_dropped",
            "R²",
            "R²_adj",
            "F_stat",
            "F_pvalue",
            "regression_method",
            "multiple_comparison_method",
            "small_sample_warning",
        ]
    )
    sheet.append(
        [
            fit.n_complete_case,
            fit.n_dropped,
            fit.r2,
            fit.r2_adj,
            fit.f_stat,
            fit.f_pvalue,
            fit.regression_method,
            fit.multiple_comparison_method,
            fit.small_sample_warning,
        ]
    )
    sheet.append([])  # blank separator row

    # Block 2 — coefficient table.
    sheet.append(list(_REGRESSION_HEADERS))
    for c in coefs:
        sheet.append(
            [
                c.axis_key,
                c.coef,
                c.std_err,
                c.t_stat,
                c.raw_p,
                c.fdr_q,
                c.ci_low_95,
                c.ci_high_95,
                c.beta_standardized,
                c.vif,
                c.multicollinearity_flag,
            ]
        )

    for i, _ in enumerate(_REGRESSION_HEADERS, start=1):
        sheet.column_dimensions[get_column_letter(i)].width = 16


def write_us1_xlsx(
    *,
    correlation_cells: Sequence[CorrelationCell],
    regression_coefs: Sequence[RegressionCoefficient],
    regression_fit: RegressionFitSummary,
    out_path: Path,
) -> None:
    """Write the US1 partial workbook (2 sheets) to ``out_path``.

    Args:
        correlation_cells: Output of :func:`compute_correlation_matrix`
            — caller is responsible for deterministic ordering
            (STANDARD_AXIS_KEYS × exam_metric_key alphabetic).
        regression_coefs: Output of :func:`compute_ols_regression`
            (1st element).
        regression_fit: Output of :func:`compute_ols_regression`
            (2nd element).
        out_path: ``.xlsx`` destination. Parent dir auto-created.

    Raises:
        ValueError: If either input list is empty (Fail-Fast).
    """
    if not correlation_cells:
        raise ValueError("write_us1_xlsx: correlation_cells is empty")
    if not regression_coefs:
        raise ValueError("write_us1_xlsx: regression_coefs is empty")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    # Remove the default sheet that openpyxl creates so our 2 sheets are
    # the only ones present (deterministic sheet order).
    if wb.active is not None and wb.active.title == "Sheet":
        wb.remove(wb.active)

    _build_correlation_sheet(wb, correlation_cells)
    _build_regression_sheet(wb, regression_coefs, regression_fit)

    wb.save(out_path)

    # Determinism vector #5 — pin <dcterms:modified> + zip entry dates.
    rewrite_modified_in_zip(out_path, _EPOCH_MODIFIED)


__all__ = ["write_us1_xlsx"]
