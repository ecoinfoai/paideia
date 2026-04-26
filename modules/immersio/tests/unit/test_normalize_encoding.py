"""Unit tests for read_text_with_fallback."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from immersio.normalize import read_text_with_fallback


def test_utf8_no_bom(tmp_path: Path) -> None:
    target = tmp_path / "u.csv"
    text = "학번,이름\n2026194999,홍길동\n"
    target.write_bytes(text.encode("utf-8"))
    decoded, label = read_text_with_fallback(target)
    assert decoded == text
    assert label == "utf-8"


def test_utf8_with_bom(tmp_path: Path) -> None:
    target = tmp_path / "u_bom.csv"
    text = "학번,이름\n"
    target.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    decoded, label = read_text_with_fallback(target)
    assert decoded == text
    assert label == "utf-8"


def test_cp949_fallback(tmp_path: Path) -> None:
    target = tmp_path / "c.csv"
    text = "학번,이름\n2026194999,홍길동\n"
    target.write_bytes(text.encode("cp949"))
    decoded, label = read_text_with_fallback(target)
    assert decoded == text
    assert label == "cp949"


def test_undecodable_raises(tmp_path: Path) -> None:
    target = tmp_path / "bad.bin"
    target.write_bytes(b"\xff\xfe\xfd\xfc")
    with pytest.raises(ValueError, match="cannot decode"):
        read_text_with_fallback(target)


def test_path_type_check() -> None:
    with pytest.raises(TypeError, match="pathlib.Path"):
        read_text_with_fallback("/tmp/x.csv")  # type: ignore[arg-type]


@given(text=st.text(min_size=1, max_size=200))
@settings(max_examples=30, deadline=500)
def test_utf8_roundtrip_property(tmp_path_factory: pytest.TempPathFactory, text: str) -> None:
    target = tmp_path_factory.mktemp("hyp") / "f.txt"
    target.write_bytes(text.encode("utf-8"))
    decoded, label = read_text_with_fallback(target)
    assert decoded == text
    assert label == "utf-8"
