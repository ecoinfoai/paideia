"""Unit tests for ``needs_map.fonts.resolve_korean_font_paths`` (T020 RED).

Per spec FR-001~FR-004 (US1 Korean font fail-fast):
- env-var ``PAIDEIA_KR_FONT_PATH`` / ``PAIDEIA_KR_FONT_BOLD_PATH`` take
  precedence over ``fc-match``.
- ``fc-match`` is invoked with ``-f '%{file}'`` and the patterns
  ``'NanumGothic'`` / ``'NanumGothic:style=Bold'``.
- The resolver MUST refuse a fc-match result whose path string does not
  contain ``NanumGothic`` (the system fell back to e.g. DejaVu Sans);
  raises ``KoreanFontUnavailableError`` instead of returning the bad path.
- A partial install (only Bold present, only Regular present, or only one
  env-var set with the other path missing) MUST be detected and named in
  the error message so operators know which file is missing.

These tests use ``subprocess`` mocking (``monkeypatch``) and never invoke
real fc-match. ``importlib.reload`` is unnecessary because each test
constructs the resolver inputs explicitly.

Spec: 003-needs-map-v0-1-1/tasks.md T020.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest


def _make_real_path(tmp_path: Path, name: str) -> Path:
    """Create a real file under tmp so resolver path-existence checks pass."""
    target = tmp_path / name
    target.write_bytes(b"\0\0\0\0")  # not a real font, just a non-empty file
    return target


def _patch_fc_match(
    monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str | Exception]
) -> None:
    """Replace ``subprocess.run`` so calls to fc-match return ``mapping[pattern]``.

    ``mapping`` maps the second positional argument (the fontconfig pattern,
    e.g. ``'NanumGothic'``) to the stdout the fake fc-match should emit.
    Raise an Exception value to simulate fc-match raising.
    """

    def _fake_run(
        cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "fc-match", f"unexpected exec target: {cmd!r}"
        # cmd shape: ['fc-match', '-f', '%{file}', pattern]
        pattern = cmd[-1]
        result = mapping.get(pattern)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise AssertionError(f"unexpected fc-match pattern: {pattern!r}")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=result, stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)


def _clear_font_envvars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure both font-path env-vars are unset for the duration of a test."""
    for var in ("PAIDEIA_KR_FONT_PATH", "PAIDEIA_KR_FONT_BOLD_PATH"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_returns_paths_when_fc_match_finds_nanumgothic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: fc-match returns paths whose strings contain ``NanumGothic``."""
    from needs_map.fonts import resolve_korean_font_paths

    _clear_font_envvars(monkeypatch)
    regular = _make_real_path(tmp_path, "NanumGothic.ttf")
    bold = _make_real_path(tmp_path, "NanumGothicBold.ttf")
    _patch_fc_match(
        monkeypatch,
        {
            "NanumGothic": f"{regular}\n",  # fc-match output trails with newline
            "NanumGothic:style=Bold": f"{bold}\n",
        },
    )

    regular_path, bold_path = resolve_korean_font_paths()
    assert regular_path == regular
    assert bold_path == bold


def test_resolve_rejects_fc_match_dejavu_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If fc-match falls back to DejaVu (no NanumGothic in path), raise."""
    from needs_map.fonts import KoreanFontUnavailableError, resolve_korean_font_paths

    _clear_font_envvars(monkeypatch)
    fallback = _make_real_path(tmp_path, "DejaVuSans.ttf")
    nanum_bold = _make_real_path(tmp_path, "NanumGothicBold.ttf")
    _patch_fc_match(
        monkeypatch,
        {
            "NanumGothic": f"{fallback}\n",  # fallback — string has no 'NanumGothic'
            "NanumGothic:style=Bold": f"{nanum_bold}\n",
        },
    )

    with pytest.raises(KoreanFontUnavailableError) as exc:
        resolve_korean_font_paths()
    msg = str(exc.value)
    assert "NanumGothic" in msg
    assert "Regular" in msg or "regular" in msg.lower()


def test_resolve_env_var_overrides_fc_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When env-var is set, it MUST beat fc-match unconditionally."""
    from needs_map.fonts import resolve_korean_font_paths

    fc_match_regular = _make_real_path(tmp_path, "NanumGothic.ttf")
    env_regular = _make_real_path(tmp_path, "custom-NanumGothic.ttf")
    fc_match_bold = _make_real_path(tmp_path, "NanumGothicBold.ttf")

    monkeypatch.setenv("PAIDEIA_KR_FONT_PATH", str(env_regular))
    monkeypatch.delenv("PAIDEIA_KR_FONT_BOLD_PATH", raising=False)
    _patch_fc_match(
        monkeypatch,
        {
            "NanumGothic": f"{fc_match_regular}\n",
            "NanumGothic:style=Bold": f"{fc_match_bold}\n",
        },
    )

    regular_path, bold_path = resolve_korean_font_paths()
    assert regular_path == env_regular  # env-var wins
    assert bold_path == fc_match_bold  # fc-match still used for the unset side


def test_resolve_partial_bold_only_env_with_regular_fc_match_fallback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bold env-var set but Regular only resolves to fallback → name 'Regular'."""
    from needs_map.fonts import KoreanFontUnavailableError, resolve_korean_font_paths

    bold_env = _make_real_path(tmp_path, "NanumGothicBold-env.ttf")
    fallback_regular = _make_real_path(tmp_path, "DejaVuSans.ttf")

    monkeypatch.delenv("PAIDEIA_KR_FONT_PATH", raising=False)
    monkeypatch.setenv("PAIDEIA_KR_FONT_BOLD_PATH", str(bold_env))
    _patch_fc_match(
        monkeypatch,
        {
            "NanumGothic": f"{fallback_regular}\n",  # fallback — fail
            # 'NanumGothic:style=Bold' should NOT be consulted (env-var wins)
        },
    )

    with pytest.raises(KoreanFontUnavailableError) as exc:
        resolve_korean_font_paths()
    msg = str(exc.value)
    assert "Regular" in msg or "regular" in msg.lower()


def test_resolve_env_var_to_nonexistent_path_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env-var pointing to a missing file MUST be rejected per env-var name."""
    from needs_map.fonts import KoreanFontUnavailableError, resolve_korean_font_paths

    bogus = tmp_path / "does_not_exist.ttf"
    real_bold = _make_real_path(tmp_path, "NanumGothicBold.ttf")

    monkeypatch.setenv("PAIDEIA_KR_FONT_PATH", str(bogus))
    monkeypatch.setenv("PAIDEIA_KR_FONT_BOLD_PATH", str(real_bold))
    _patch_fc_match(monkeypatch, {})

    with pytest.raises(KoreanFontUnavailableError) as exc:
        resolve_korean_font_paths()
    msg = str(exc.value)
    assert "PAIDEIA_KR_FONT_PATH" in msg
    assert str(bogus) in msg


def test_resolve_fc_match_subprocess_failure_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If fc-match subprocess fails (FileNotFoundError, CalledProcessError), raise."""
    from needs_map.fonts import KoreanFontUnavailableError, resolve_korean_font_paths

    _clear_font_envvars(monkeypatch)
    _patch_fc_match(
        monkeypatch,
        {
            "NanumGothic": FileNotFoundError("fc-match not installed"),
            "NanumGothic:style=Bold": FileNotFoundError("fc-match not installed"),
        },
    )

    with pytest.raises(KoreanFontUnavailableError) as exc:
        resolve_korean_font_paths()
    assert "fc-match" in str(exc.value).lower()
