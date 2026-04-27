"""cluster_summary.xlsx writer (T099, FR-017 (b)).

openpyxl-based: 1 summary sheet (cluster_id × name × size × silhouette) +
1 sheet per cluster (학생 수 × 의미축 평균).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from paideia_shared.schemas import ClusterReport

_AXES: tuple[str, ...] = (
    "motivation",
    "anxiety",
    "self_efficacy",
    "interest",
    "prior_knowledge",
    "life_context",
)


def write_cluster_summary_xlsx(
    cluster_report: ClusterReport,
    factor_scores_df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write a 2-tier xlsx: summary + per-cluster detail.

    Args:
        cluster_report: validated ClusterReport from Phase C.
        factor_scores_df: factor_scores parquet content (1 row per student).
        output_path: target xlsx file path.
    """
    wb = Workbook()
    ws_summary = wb.active
    if ws_summary is None:
        raise RuntimeError("openpyxl returned no active worksheet")
    ws_summary.title = "summary"
    ws_summary.append(["cluster_id", "name", "size", "silhouette_used"])

    # student_id → cluster_id lookup
    cluster_by_student = {row.student_id: row.cluster_id for row in cluster_report.rows}
    factor_scores_df = factor_scores_df.copy()
    factor_scores_df["cluster_id"] = factor_scores_df["student_id"].map(cluster_by_student)

    for cluster_id in sorted(cluster_report.cluster_names.keys()):
        size = sum(1 for r in cluster_report.rows if r.cluster_id == cluster_id)
        ws_summary.append(
            [
                int(cluster_id),
                cluster_report.cluster_names[cluster_id],
                int(size),
                float(cluster_report.silhouette_used)
                if cluster_report.silhouette_used is not None
                else "",
            ]
        )

    # Per-cluster sheet
    for cluster_id in sorted(cluster_report.cluster_names.keys()):
        ws = wb.create_sheet(title=f"cluster_{cluster_id}")
        ws.append(["axis", "mean", "std", "n"])
        cluster_df = factor_scores_df[factor_scores_df["cluster_id"] == cluster_id]
        for axis in _AXES:
            if axis not in cluster_df.columns:
                continue
            substantive = cluster_df[axis].dropna()
            if substantive.empty:
                ws.append([axis, "", "", 0])
            else:
                ws.append(
                    [
                        axis,
                        float(substantive.mean()),
                        float(substantive.std(ddof=0)),
                        int(substantive.shape[0]),
                    ]
                )

    wb.save(str(output_path))
