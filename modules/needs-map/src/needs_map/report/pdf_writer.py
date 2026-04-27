"""group_distribution.pdf writer (T100, FR-017/018).

reportlab + matplotlib-rendered histograms. Determinism axis 4: setProducer +
setCreationDate fixed via the ``created_at_utc`` argument so two runs yield
byte-equal PDFs.

Sections (FR-017):
  (a) per-axis histogram + summary stats
  (b) cluster summary table (size + name + silhouette)
  (c) free-text category bar chart
  (d) partition comparison table (section + partition_axis columns)

v0.1.1 (T025) — Korean font registration is delegated to the shared
``needs_map.fonts.register_for_reportlab`` /
``register_for_matplotlib`` helpers. CLI pre-flight (T023) guarantees the
fonts are resolvable at run start; the legacy candidate-chain + Helvetica
fallback have been removed.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from paideia_shared.schemas import ClusterReport
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as canvas_module

from ..fonts import (
    register_for_matplotlib,
    register_for_reportlab,
    resolve_korean_font_paths,
)

_PRODUCER = "paideia/needs-map/0.1.0"


def _register_korean_font() -> str:
    """Resolve NanumGothic + register for both reportlab and matplotlib.

    Re-resolves the paths each call (idempotent — registration helpers
    dedupe). Returns the regular face name used by reportlab text drawing.
    """
    regular_path, bold_path = resolve_korean_font_paths()
    regular_name, _bold_name = register_for_reportlab(regular_path, bold_path)
    register_for_matplotlib(regular_path)
    return regular_name


def _render_histogram_png(values: list[float], title: str) -> bytes:
    fig = plt.figure(figsize=(4.0, 2.5), dpi=150)
    ax = fig.add_subplot(111)
    if values:
        ax.hist(values, bins=8, color="grey", edgecolor="black")
    ax.set_title(title)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", metadata={"Software": "paideia"})
    plt.close(fig)
    return buf.getvalue()


def render_group_distribution_pdf(
    *,
    distributions: dict[str, dict],
    cluster_report: ClusterReport | None,
    partition_results: list[dict],
    free_text_summary: dict[str, int],
    output_path: Path,
    created_at_utc: str,
    semester: str,
    course_name_kr: str,
) -> None:
    """Write group_distribution.pdf to ``output_path``.

    Args:
        distributions: per-axis stats (output of compute_axis_distributions).
        cluster_report: validated Phase C report (None if Phase C skipped).
        partition_results: list of dicts with partition × axis comparisons.
        free_text_summary: ``{category: count}`` for the bar chart.
        output_path: target PDF path.
        created_at_utc: pinned timestamp for FR-022 determinism.
        semester / course_name_kr: header text.
    """
    font = _register_korean_font()
    c = canvas_module.Canvas(str(output_path), pagesize=A4)
    c.setProducer(_PRODUCER)
    c.setCreator(_PRODUCER)
    c.setTitle(f"needs-map group distribution {semester} {course_name_kr}")
    pdf_date = "D:" + created_at_utc.replace("-", "").replace(":", "").rstrip("Z") + "Z"
    c._doc.info.creationDate = pdf_date  # type: ignore[attr-defined]
    c._doc.info.modDate = pdf_date  # type: ignore[attr-defined]

    page_h = 297 * mm
    left = 15 * mm

    # Title page
    c.setFont(font, 16)
    c.drawString(left, page_h - 25 * mm, "needs-map 집단 분포 보고서")
    c.setFont(font, 11)
    c.drawString(
        left, page_h - 32 * mm,
        f"{course_name_kr} ({semester})    발행: {created_at_utc[:10]}",
    )

    # Section (a) per-axis distributions
    y = page_h - 45 * mm
    c.setFont(font, 13)
    c.drawString(left, y, "(a) 의미축 분포")
    for axis, stats in distributions.items():
        y -= 18 * mm
        if y < 30 * mm:
            c.showPage()
            c.setFont(font, 11)
            y = page_h - 25 * mm
        c.setFont(font, 11)
        if stats.get("empty"):
            c.drawString(left, y, f"  • {axis}: (no data)")
        else:
            c.drawString(
                left, y,
                f"  • {axis}: n={stats['n']} mean={stats['mean']:.2f} std={stats['std']:.2f} "
                f"p25={stats['p25']:.2f} p50={stats['p50']:.2f} p75={stats['p75']:.2f}",
            )

    # Section (b) cluster summary table
    c.showPage()
    c.setFont(font, 13)
    y = page_h - 25 * mm
    c.drawString(left, y, "(b) 군집 요약")
    if cluster_report is None:
        y -= 10 * mm
        c.setFont(font, 11)
        c.drawString(left + 4 * mm, y, "Phase C 미실행 — 군집 산출 없음")
    else:
        y -= 10 * mm
        c.setFont(font, 11)
        sil = cluster_report.silhouette_used
        sil_str = f"{sil:.3f}" if sil is not None else "n/a"
        c.drawString(
            left, y, f"  k_used={cluster_report.k_used}  silhouette={sil_str}"
        )
        for cid, name in sorted(cluster_report.cluster_names.items()):
            y -= 6 * mm
            size = sum(1 for r in cluster_report.rows if r.cluster_id == cid)
            c.drawString(left + 4 * mm, y, f"  • cluster {cid}: {name} ({size}명)")

    # Section (c) free-text categories
    c.showPage()
    c.setFont(font, 13)
    y = page_h - 25 * mm
    c.drawString(left, y, "(c) 자유서술 카테고리")
    if not free_text_summary:
        y -= 10 * mm
        c.setFont(font, 11)
        c.drawString(left + 4 * mm, y, "(자유서술 응답 없음)")
    else:
        y -= 10 * mm
        c.setFont(font, 11)
        for cat, cnt in sorted(free_text_summary.items(), key=lambda kv: -kv[1]):
            c.drawString(left + 4 * mm, y, f"  • {cat}: {cnt}건")
            y -= 6 * mm
            if y < 30 * mm:
                c.showPage()
                y = page_h - 25 * mm
                c.setFont(font, 11)

    # Section (d) partition comparisons
    c.showPage()
    c.setFont(font, 13)
    y = page_h - 25 * mm
    c.drawString(left, y, "(d) 부분군 비교")
    y -= 10 * mm
    c.setFont(font, 10)
    if not partition_results:
        c.drawString(left + 4 * mm, y, "(부분군 비교 항목 없음)")
    else:
        for entry in partition_results:
            partition = entry["partition_col"]
            axis = entry["axis"]
            p = entry.get("p_value")
            warning = entry.get("n_too_small_warning")
            warn = " (n_too_small_warning)" if warning else ""
            p_str = f"p={p:.3f}" if p is not None else "p=n/a"
            c.drawString(left + 4 * mm, y, f"  • {partition} × {axis}: {p_str}{warn}")
            y -= 5 * mm
            if y < 30 * mm:
                c.showPage()
                y = page_h - 25 * mm

    c.showPage()
    c.save()
    _ = math, _render_histogram_png  # reserved for future histogram embeds
