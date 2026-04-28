"""Unit tests for immersio.analyze.timing.resolve_created_at_utc (T020).

Spec 004 research §R-10 — hash-derived ISO8601 시각.
- override 가 있으면 override 사용
- 미지정 시 sha256 → epoch + int 초
- 같은 input → 같은 시각 (결정성)
- 다른 input → 다른 시각
"""

from __future__ import annotations

import re

import pytest

from immersio.analyze.timing import resolve_created_at_utc

ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_resolve_created_at_utc_override_takes_precedence() -> None:
    out = resolve_created_at_utc(
        inputs_sha256="0" * 64, override="2026-04-28T10:00:00Z"
    )
    assert out == "2026-04-28T10:00:00Z"


def test_resolve_created_at_utc_override_invalid_format_rejected() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        resolve_created_at_utc(inputs_sha256="0" * 64, override="2026-04-28")


def test_resolve_created_at_utc_default_format() -> None:
    out = resolve_created_at_utc(inputs_sha256="a" * 64, override=None)
    assert ISO8601_UTC_RE.match(out), f"output {out!r} not ISO 8601 UTC"


def test_resolve_created_at_utc_deterministic_same_hash() -> None:
    h = "abc" * 21 + "d"  # 64 chars
    a = resolve_created_at_utc(inputs_sha256=h, override=None)
    b = resolve_created_at_utc(inputs_sha256=h, override=None)
    assert a == b


def test_resolve_created_at_utc_different_hashes_differ() -> None:
    a = resolve_created_at_utc(inputs_sha256="a" * 64, override=None)
    b = resolve_created_at_utc(inputs_sha256="b" * 64, override=None)
    assert a != b


def test_resolve_created_at_utc_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="sha256"):
        resolve_created_at_utc(inputs_sha256="too-short", override=None)
