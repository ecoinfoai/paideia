"""1-page card layout (T101, FR-019/020/021/022, contracts/needs_map_card.layout.md).

Reportlab Canvas-based. Determinism axis 4: setProducer + setCreator +
setCreationDate fixed via the ``created_at_utc`` argument so two runs
with identical input + the same NeedsMapArgs.created_at_utc yield byte-equal PDFs.

Korean font: registered via _register_korean_font (Noto Sans CJK KR if
available; falls back to Helvetica + romanized labels — never raises).
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as canvas_module

_PRODUCER = "paideia/needs-map/0.1.0"
_KOREAN_FONT_NAME = "NotoSansCJKKR"
_KOREAN_FONT_REGISTERED: bool = False


def _register_korean_font() -> str:
    """Register Noto Sans CJK KR if a TTF/OTF is locatable; return font name to use."""
    global _KOREAN_FONT_REGISTERED
    if _KOREAN_FONT_REGISTERED:
        return _KOREAN_FONT_NAME
    candidates = [
        "/run/current-system/sw/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/nix/store/4q2wdcakn6likmvqsh94rbjbbnr2lz0x-home-manager-path/share/fonts/opentype/noto-cjk/NotoSansCJK-VF.otf.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    import os

    env_override = os.environ.get("PAIDEIA_KR_FONT_PATH")
    if env_override:
        candidates.insert(0, env_override)

    for path in candidates:
        if Path(path).is_file():
            try:
                pdfmetrics.registerFont(TTFont(_KOREAN_FONT_NAME, path, subfontIndex=1))
                _KOREAN_FONT_REGISTERED = True
                return _KOREAN_FONT_NAME
            except Exception:  # noqa: BLE001, S112 — font load failure → next candidate
                continue  # noqa: S112 — fallback chain by design
    return "Helvetica"


def render_card_pdf(
    *,
    student_id: str,
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
    c = canvas_module.Canvas(buf, pagesize=A4)

    # Determinism axis 4 — fixed metadata
    c.setProducer(_PRODUCER)
    c.setCreator(_PRODUCER)
    c.setTitle(f"needs-map card {student_id}")
    c.setSubject(f"{semester} {course_name_kr}")
    # reportlab needs a 'D:YYYYMMDDHHmmSS' format — derive from created_at_utc
    pdf_date = "D:" + created_at_utc.replace("-", "").replace(":", "").rstrip("Z") + "Z"
    c._doc.info.creationDate = pdf_date  # type: ignore[attr-defined]
    c._doc.info.modDate = pdf_date  # type: ignore[attr-defined]

    # Page geometry (per contracts/needs_map_card.layout.md)
    page_w = 210 * mm
    page_h = 297 * mm
    left = 15 * mm
    right = page_w - 15 * mm

    # A. Header
    y = page_h - 18 * mm
    c.setFont(font, 14)
    c.drawString(left, y, f"학번 {student_id}    분반 {section or '명단외'}")
    c.setFont(font, 10)
    c.drawString(left, y - 6 * mm, f"{course_name_kr} ({semester})    발행: {created_at_utc[:10]}")

    # B. Radar
    radar_top = y - 12 * mm
    radar_height = 100 * mm
    img = ImageReader(io.BytesIO(radar_png))
    c.drawImage(
        img, left, radar_top - radar_height, width=right - left, height=radar_height,
        preserveAspectRatio=True, mask="auto",
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
    c.setFont(font, 8)
    c.setFillGray(0.4)
    c.drawString(
        left, coach_top - 30 * mm,
        f"({'템플릿 기반' if coaching_source == 'template' else 'LLM 다듬음'})",
    )
    c.setFillGray(0.0)

    c.showPage()
    c.save()
    return buf.getvalue()
