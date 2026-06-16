"""compute_metadata_aggregates — `2_메타데이터통계` 시트 산출 (T036, FR-010).

Spec 004 contracts/xlsx_sheets.md §3 + research §R-02 (Levene → ANOVA / Welch
ANOVA / Welch t-test 자동 폴백).

8 metadata_kind 그룹:
- 분반, 고교생물_이수, 직업: student-level 메타 컬럼에서 직접 집계
- 예상난이도, 난이도, 문제유형, 출처, 챕터: ExamItem 메타에서 집계
  (단, 본 v0.1.0 분기에서는 student-level 메타가 우선 — item-level 그룹은
  Phase 4 / 추후 확장)

본 v0.1.0 land 는 student-level 4종 (분반 + 고교생물_이수 + 직업) 우선 — 다른
4종 (item-level) 은 placeholder 행 (n=0) 으로 남겨 schema 정합 유지하되 추후
Phase 4 와 함께 확장 가능.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd
from paideia_shared.schemas import MetadataAggregate, MetadataKind, TestKind

from .stat_tests import levene_then_anova, welch_t_test

UNDEFINED_LABEL: str = "(메타 미정의)"
"""Reserved metadata_value when the student-level field is null/blank."""

_STUDENT_LEVEL_KINDS: tuple[tuple[MetadataKind, str], ...] = (
    ("분반", "section"),
    ("고교생물_이수", "고교생물_이수"),
    ("직업", "직업"),
)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _group_by(df: pd.DataFrame, key: str) -> dict[str, np.ndarray]:
    """Return ``{value: scores_array}`` for one metadata column."""
    out: dict[str, list[float]] = {}
    for _, row in df.iterrows():
        raw = row[key]
        label = UNDEFINED_LABEL if _is_blank(raw) else str(raw).strip()
        score = row["total_score"]
        if _is_blank(score):
            continue
        out.setdefault(label, []).append(float(score))
    return {k: np.array(v, dtype=float) for k, v in out.items()}


def _pick_test(groups: list[np.ndarray]) -> tuple[float | None, TestKind]:
    """Pick the appropriate test given group count and sizes."""
    valid = [g for g in groups if g.size >= 2]
    if len(valid) < 2:
        return None, "N/A"
    if len(valid) == 2:
        try:
            p = welch_t_test(valid[0], valid[1])
            return p, "Welch t-test"
        except ValueError:
            return None, "N/A"
    try:
        p, kind = levene_then_anova(valid)
        return p, kind
    except ValueError:
        return None, "N/A"


def _build_kind_rows(
    kind: MetadataKind,
    grouped: dict[str, np.ndarray],
) -> list[MetadataAggregate]:
    """Build per-value rows + a final test-result row for one metadata_kind."""
    sorted_labels = sorted(grouped.keys())
    test_groups = [grouped[label] for label in sorted_labels if label != UNDEFINED_LABEL]
    p_value, test_kind = _pick_test(test_groups)

    rows: list[MetadataAggregate] = []
    for label in sorted_labels:
        scores = grouped[label]
        n = int(scores.size)
        if label == UNDEFINED_LABEL:
            rows.append(
                MetadataAggregate(
                    metadata_kind=kind,
                    metadata_value=label,
                    n=n,
                    mean=float(scores.mean()) if n > 0 else None,
                    sd=(float(scores.std(ddof=1)) if n >= 2 else None),
                    test_kind="N/A",
                    test_p_value=None,
                    levene_p_value=None,
                    note="metadata 결측 — 검정 제외",
                )
            )
        else:
            rows.append(
                MetadataAggregate(
                    metadata_kind=kind,
                    metadata_value=label,
                    n=n,
                    mean=(float(scores.mean()) if n > 0 else None),
                    sd=(float(scores.std(ddof=1)) if n >= 2 else None),
                    test_kind=test_kind,
                    test_p_value=p_value,
                    levene_p_value=None,
                    note=("표본 < 30명, 신뢰도 낮음" if 0 < n < 30 else None),
                )
            )
    return rows


def compute_metadata_aggregates(
    *,
    student_metrics_df: pd.DataFrame,
    items: Iterable[dict],
) -> list[MetadataAggregate]:
    """Build the rows for the `2_메타데이터통계` sheet.

    Args:
        student_metrics_df: One row per responder with ``student_id``,
            ``total_score`` (float), and the per-student metadata columns
            (``section``, ``고교생물_이수``, ``직업``). Missing rows /
            blank values become ``UNDEFINED_LABEL`` rows (검정 제외).
        items: Iterable of ExamItem dicts (used by item-level kinds in
            future phases; v0.1.0 currently keeps the kinds defined but
            generates no rows when item_metric scaffolding is absent —
            present here so the signature stays stable for Phase 4).

    Returns:
        ``list[MetadataAggregate]`` — one row per (kind, value) plus an
        ``N/A`` placeholder when the kind has no usable groups.

    Raises:
        ValueError: When ``student_metrics_df`` is empty.
    """
    _ = items  # reserved for item-level kinds; v0.1.0 currently student-level only
    if student_metrics_df.empty:
        raise ValueError("compute_metadata_aggregates: student_metrics_df is empty")
    if "total_score" not in student_metrics_df.columns:
        raise ValueError(
            "compute_metadata_aggregates: student_metrics_df missing 'total_score' column"
        )

    rows: list[MetadataAggregate] = []
    for kind, column in _STUDENT_LEVEL_KINDS:
        if column not in student_metrics_df.columns:
            continue
        grouped = _group_by(student_metrics_df, column)
        if not grouped:
            continue
        rows.extend(_build_kind_rows(kind, grouped))
    return rows
