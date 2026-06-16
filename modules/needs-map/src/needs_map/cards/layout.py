"""1-page card layout (T101, FR-019/020/021/022, contracts/needs_map_card.layout.md).

Reportlab Canvas-based. Determinism axis 4: setProducer + setCreator +
setCreationDate fixed via the ``created_at_utc`` argument so two runs
with identical input + the same NeedsMapArgs.created_at_utc yield byte-equal PDFs.

v0.1.1 (T024) — Korean font registration is delegated to the shared
``needs_map.fonts.register_for_reportlab`` helper, which assumes the CLI
pre-flight (T023) has already validated NanumGothic Regular + Bold via
``resolve_korean_font_paths``. The legacy candidate-chain + Helvetica
fallback have been removed: missing fonts now exit the pipeline at entry
with code 6 (FR-005), so card rendering never has to choose between
correct text and degraded glyphs.
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as canvas_module

from ..determinism import iso_utc_to_epoch, pin_source_date_epoch
from ..fonts import register_for_reportlab, resolve_korean_font_paths

_PRODUCER = "paideia/needs-map/0.1.0"


def _register_korean_font() -> str:
    """Register NanumGothic Regular + Bold and return the regular face name.

    Re-resolves the font paths via ``resolve_korean_font_paths`` so card
    rendering remains valid even when invoked outside the CLI pre-flight
    (e.g. unit tests). Both calls are idempotent.
    """
    regular_path, bold_path = resolve_korean_font_paths()
    regular_name, _bold_name = register_for_reportlab(regular_path, bold_path)
    return regular_name


def _format_semester_kr(semester: str) -> str:
    """Format ``YYYY-N`` semester code as ``YYYY학년도 N학기``.

    Falls back to the raw input if the pattern does not match.
    """
    if "-" in semester:
        year, term = semester.split("-", 1)
        if year.isdigit() and term.isdigit():
            return f"{year}학년도 {term}학기"
    return semester


def render_card_pdf(
    *,
    student_id: str,
    student_name: str | None = None,
    section: str | None,
    semester: str,
    course_name_kr: str,
    cluster_label: str | None,
    cluster_size: int | None,
    distance_z: float | None,
    free_text_categories: list[str],
    coaching_text: str,
    coaching_source: str,
    radar_png: bytes,
    created_at_utc: str,
) -> bytes:
    """Render one A4 portrait PDF as bytes per contracts/needs_map_card.layout.md.

    All inputs are PII-bearing (student_id is shown verbatim per FR-PII-001
    internal-use policy); the caller is responsible for deciding whether the
    output is exported externally.
    """
    font = _register_korean_font()
    buf = io.BytesIO()
    # Determinism axis 4 — reportlab captures its CreationDate/ModDate timestamp
    # at Canvas construction from SOURCE_DATE_EPOCH (else the host wall clock),
    # so pin it to created_at_utc for the construction to stay byte-reproducible.
    with pin_source_date_epoch(iso_utc_to_epoch(created_at_utc)):
        c = canvas_module.Canvas(buf, pagesize=A4)
    c.setProducer(_PRODUCER)
    c.setCreator(_PRODUCER)
    c.setTitle(f"needs-map card {student_id}")
    c.setSubject(f"{semester} {course_name_kr}")

    # Page geometry (per contracts/needs_map_card.layout.md)
    page_w = 210 * mm
    page_h = 297 * mm
    left = 15 * mm
    right = page_w - 15 * mm

    # A. Header
    y = page_h - 18 * mm
    c.setFont(font, 14)
    name_display = (student_name or "").strip() or "(미상)"
    c.drawString(left, y, f"학번 {student_id}    이름 {name_display}")
    c.setFont(font, 10)
    semester_kr = _format_semester_kr(semester)
    c.drawString(
        left,
        y - 6 * mm,
        f"{course_name_kr} ({semester_kr})    발행: {created_at_utc[:10]}",
    )
    _ = section  # 분반은 운영자 검토용 — silver/student_master에서 별도 조회

    # B. Radar
    radar_top = y - 12 * mm
    radar_height = 100 * mm
    img = ImageReader(io.BytesIO(radar_png))
    c.drawImage(
        img,
        left,
        radar_top - radar_height,
        width=right - left,
        height=radar_height,
        preserveAspectRatio=True,
        mask="auto",
    )

    # C. Cluster
    cluster_top = radar_top - radar_height - 5 * mm
    c.setFont(font, 12)
    if cluster_label:
        size_str = f" ({cluster_size}명)" if cluster_size is not None else ""
        dist_str = ""
        if distance_z is not None:
            if distance_z < 0.5:
                tier = "중앙에 가까움"
            elif distance_z < 1.0:
                tier = "중앙"
            elif distance_z < 1.5:
                tier = "주변"
            else:
                tier = "외곽"
            dist_str = f"  본인 위치: {tier} (거리 {distance_z:.2f})"
        c.drawString(left, cluster_top, f"군집: {cluster_label}{size_str}{dist_str}")
    else:
        c.drawString(left, cluster_top, "군집: 진단 미응답으로 군집 산출 불가")

    # D. Free-text categories
    ft_top = cluster_top - 12 * mm
    c.setFont(font, 10)
    c.drawString(left, ft_top, "학생 응답 카테고리:")
    if free_text_categories:
        for i, cat in enumerate(free_text_categories[:5]):
            c.drawString(left + 4 * mm, ft_top - (4 + 4 * i) * mm, f"• {cat}")
    else:
        c.drawString(left + 4 * mm, ft_top - 4 * mm, "• 응답 없음")

    # E. Coaching message
    coach_top = ft_top - 30 * mm
    c.setFont(font, 10)
    for i, line in enumerate(coaching_text.split("\n")[:4]):
        c.drawString(left, coach_top - 5 * mm * i, line)
    _ = coaching_source  # 운영 메타데이터 — manifest.json에 별도 기록

    c.showPage()
    c.save()
    return buf.getvalue()
