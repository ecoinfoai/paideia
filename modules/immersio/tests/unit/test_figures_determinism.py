"""T033 — RED tests for `report/figures.py` (FR-022, R-11).

Two PNG figure builders, both deterministic:

* ``render_fig1_score_histogram(bins, output_path)`` — score histogram bar
  chart matching the ``1_히스토그램`` sheet's data; matplotlib Agg + dpi
  150 + bbox tight + ``Software=paideia`` metadata.
* ``render_fig2_metadata_correct_rates(rows, output_path)`` — grouped bar
  chart of mean score per metadata_kind/value.

Same input → byte-identical PNG (FR-023, SC-002). Both functions hard-
require NanumGothic resolution at call time so tests must monkeypatch
``immersio.fonts.resolve_korean_font_paths`` to return a real
``Path`` (the system's NanumGothic if installed, otherwise a synthetic
DejaVu fallback so the test still runs in environments without Korean
fonts — figures still byte-equal across two consecutive renders).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from paideia_shared.schemas import HistogramBin, MetadataAggregate

from immersio import fonts as _fonts
from immersio.report.figures import (
    render_fig1_score_histogram,
    render_fig2_metadata_correct_rates,
)


@pytest.fixture(autouse=True)
def _resolve_font(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass NanumGothic install requirement for byte-equality tests.

    Determinism is the property under test, not font resolution itself
    (which has its own fixture in needs-map). We swap in a vendored
    DejaVu Sans path that ships with matplotlib so the tests run on any
    CI host. The monkey-patch is reverted automatically.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager

    # DejaVu Sans is bundled with matplotlib's built-in fonts.
    deja_vu = font_manager.findfont("DejaVu Sans", fallback_to_default=True)
    deja_vu_path = Path(deja_vu)
    monkeypatch.setattr(
        _fonts, "resolve_korean_font_paths", lambda: (deja_vu_path, deja_vu_path)
    )


def _stub_bins() -> list[HistogramBin]:
    return [
        HistogramBin(bin_start=0.0, bin_end=10.0, count=0, cumulative=0, cumulative_pct=0.0),
        HistogramBin(bin_start=10.0, bin_end=20.0, count=2, cumulative=2, cumulative_pct=20.0),
        HistogramBin(bin_start=20.0, bin_end=30.0, count=8, cumulative=10, cumulative_pct=100.0),
    ]


def _stub_metadata() -> list[MetadataAggregate]:
    return [
        MetadataAggregate(
            metadata_kind="분반",
            metadata_value="A",
            n=46,
            mean=80.0,
            sd=5.0,
            test_kind="ANOVA",
            test_p_value=0.10,
            levene_p_value=None,
            note=None,
        ),
        MetadataAggregate(
            metadata_kind="분반",
            metadata_value="B",
            n=46,
            mean=70.0,
            sd=8.0,
            test_kind="ANOVA",
            test_p_value=0.10,
            levene_p_value=None,
            note=None,
        ),
        MetadataAggregate(
            metadata_kind="고교생물_이수",
            metadata_value="이수",
            n=70,
            mean=85.0,
            sd=5.0,
            test_kind="Welch t-test",
            test_p_value=0.001,
            levene_p_value=None,
            note=None,
        ),
        MetadataAggregate(
            metadata_kind="고교생물_이수",
            metadata_value="미이수",
            n=114,
            mean=72.0,
            sd=8.0,
            test_kind="Welch t-test",
            test_p_value=0.001,
            levene_p_value=None,
            note=None,
        ),
    ]


def test_fig1_renders_png(tmp_path: Path) -> None:
    out = tmp_path / "fig1.png"
    render_fig1_score_histogram(bins=_stub_bins(), output_path=out)
    assert out.is_file()
    head = out.read_bytes()[:8]
    assert head == b"\x89PNG\r\n\x1a\n", "fig1 must be a real PNG"


def test_fig1_two_calls_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "fig1_a.png"
    b = tmp_path / "fig1_b.png"
    render_fig1_score_histogram(bins=_stub_bins(), output_path=a)
    render_fig1_score_histogram(bins=_stub_bins(), output_path=b)
    sha_a = hashlib.sha256(a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(b.read_bytes()).hexdigest()
    assert sha_a == sha_b


def test_fig2_renders_png(tmp_path: Path) -> None:
    out = tmp_path / "fig2.png"
    render_fig2_metadata_correct_rates(rows=_stub_metadata(), output_path=out)
    assert out.is_file()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_fig2_two_calls_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "fig2_a.png"
    b = tmp_path / "fig2_b.png"
    render_fig2_metadata_correct_rates(rows=_stub_metadata(), output_path=a)
    render_fig2_metadata_correct_rates(rows=_stub_metadata(), output_path=b)
    sha_a = hashlib.sha256(a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(b.read_bytes()).hexdigest()
    assert sha_a == sha_b


def test_fig1_pin_software_metadata(tmp_path: Path) -> None:
    out = tmp_path / "fig1.png"
    render_fig1_score_histogram(bins=_stub_bins(), output_path=out)
    raw = out.read_bytes()
    # Metadata text chunks ('tEXt') containing 'Software' must appear in the PNG.
    assert b"Software" in raw
    assert b"paideia" in raw


def test_fig2_pin_software_metadata(tmp_path: Path) -> None:
    out = tmp_path / "fig2.png"
    render_fig2_metadata_correct_rates(rows=_stub_metadata(), output_path=out)
    raw = out.read_bytes()
    assert b"Software" in raw
    assert b"paideia" in raw
