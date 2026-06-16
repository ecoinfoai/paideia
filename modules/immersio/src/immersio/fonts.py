"""NanumGothic font resolution for immersio (T041/T043 prereq).

Spec 004 quickstart §0.2 + tasks T041 (pdf_writer) + T043 (figures) +
T077 polish (`paideia_shared.fonts (이미 land)`). The shared module
referenced by the spec has not been promoted yet; the helpers below
mirror the needs-map v0.1.1 implementation 1:1 so the runtime contract
is identical and can be replaced by ``from paideia_shared.fonts import
...`` once the promotion lands (Phase 10 polish).

Resolution order (per spec FR-022 + needs-map R-01):

1. ``PAIDEIA_KR_FONT_PATH`` env-var (Regular) /
   ``PAIDEIA_KR_FONT_BOLD_PATH`` env-var (Bold).
2. ``fc-match -f '%{file}' NanumGothic`` /
   ``fc-match -f '%{file}' NanumGothic:style=Bold``.

If neither produces a path whose string contains ``NanumGothic``,
``KoreanFontUnavailableError`` is raised with a multi-line operator-
actionable message; the CLI surfaces this as exit 6.

Hardening (per needs-map adversary follow-up):
* env-var paths are resolved with ``Path.resolve(strict=True)`` to
  reject dangling symlinks.
* extension whitelist (.ttf / .otf / .ttc / .otc) — refuse executables.
* 50 MB size cap — refuse oversize blobs.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

_REGULAR_FAMILY_NAME = "NanumGothic"
_REGULAR_FONT_NAME = "NanumGothic"
_BOLD_FONT_NAME = "NanumGothic-Bold"

_FC_MATCH_REGULAR_PATTERN = "NanumGothic"
_FC_MATCH_BOLD_PATTERN = "NanumGothic:style=Bold"

_REGULAR_ENV_VAR = "PAIDEIA_KR_FONT_PATH"
_BOLD_ENV_VAR = "PAIDEIA_KR_FONT_BOLD_PATH"

_FC_MATCH_TIMEOUT_SECONDS = 5.0

_FONT_EXTENSION_WHITELIST: frozenset[str] = frozenset({".ttf", ".otf", ".ttc", ".otc"})
_FONT_SIZE_CAP_BYTES: int = 50 * 1024 * 1024

FaceKind = Literal["Regular", "Bold"]


class KoreanFontUnavailableError(RuntimeError):
    """Raised when NanumGothic Regular or Bold cannot be resolved.

    The exception's first argument carries the multi-line operator-
    actionable block; the CLI streams it to stderr verbatim and exits
    with code 6.
    """


def _format_error_block(
    *,
    face: FaceKind,
    env_var: str,
    env_var_status: str,
    fc_pattern: str,
    fc_match_status: str,
) -> str:
    family_label = f"NanumGothic {face}"
    return "\n".join(
        [
            f"ERROR: Required Korean font {family_label!r} not resolved.",
            "  Tried (in order):",
            f"    1. {env_var} (env-var)            → {env_var_status}",
            f"    2. fc-match {fc_pattern!r}              → {fc_match_status}",
            "  Install:",
            "    NixOS:        home.packages = [ pkgs.nanum ];",
            "    Ubuntu/Debian: sudo apt install fonts-nanum",
            "    macOS:         brew install --cask font-nanum-gothic",
            f"  Then re-run, or set {env_var} to a verified {face} .ttf path.",
            "Exit code: 6",
        ]
    )


def _run_fc_match(pattern: str) -> Path | None:
    try:
        cmd = ["fc-match", "-f", "%{file}", pattern]  # noqa: S607
        completed = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=_FC_MATCH_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    output = completed.stdout.strip()
    if not output:
        return None
    return Path(output)


def _resolve_env_var_path(face: FaceKind, env_var: str, env_value: str, fc_pattern: str) -> Path:
    candidate = Path(env_value)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError):
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status=f"set → {env_value} (file not found / unresolvable)",
                fc_pattern=fc_pattern,
                fc_match_status="not consulted (env-var set)",
            )
        ) from None
    if not resolved.is_file():
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status=f"set → {resolved} (not a regular file)",
                fc_pattern=fc_pattern,
                fc_match_status="not consulted (env-var set)",
            )
        )
    if resolved.suffix.lower() not in _FONT_EXTENSION_WHITELIST:
        allowed = ", ".join(sorted(_FONT_EXTENSION_WHITELIST))
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status=(
                    f"set → {resolved} (extension {resolved.suffix!r} not in "
                    f"allowed font extensions: {allowed})"
                ),
                fc_pattern=fc_pattern,
                fc_match_status="not consulted (env-var set)",
            )
        )
    size_bytes = resolved.stat().st_size
    if size_bytes > _FONT_SIZE_CAP_BYTES:
        cap_mb = _FONT_SIZE_CAP_BYTES // (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status=(
                    f"set → {resolved} (size {actual_mb:.1f} MB exceeds "
                    f"{cap_mb} MB cap — refusing to load)"
                ),
                fc_pattern=fc_pattern,
                fc_match_status="not consulted (env-var set)",
            )
        )
    return resolved


def _resolve_face(face: FaceKind, env_var: str, fc_pattern: str) -> Path:
    env_value = os.environ.get(env_var)
    if env_value:
        return _resolve_env_var_path(face, env_var, env_value, fc_pattern)
    fc_match_path = _run_fc_match(fc_pattern)
    if fc_match_path is None:
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status="not set",
                fc_pattern=fc_pattern,
                fc_match_status="fc-match command failed (subprocess unavailable)",
            )
        )
    if "NanumGothic" not in str(fc_match_path):
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status="not set",
                fc_pattern=fc_pattern,
                fc_match_status=(
                    f"matched {fc_match_path.name!r} (NanumGothic not in result path)"
                ),
            )
        )
    if not fc_match_path.is_file():
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status="not set",
                fc_pattern=fc_pattern,
                fc_match_status=f"matched {fc_match_path} but the file does not exist",
            )
        )
    return fc_match_path


def resolve_korean_font_paths() -> tuple[Path, Path]:
    """Resolve NanumGothic Regular + Bold paths, or raise.

    Returns:
        ``(regular_path, bold_path)`` — both ``Path`` to existing
        ``.ttf``/``.otf``/``.ttc``/``.otc`` files containing ``NanumGothic``
        in their resolved path.

    Raises:
        KoreanFontUnavailableError: When either face cannot be resolved.
    """
    regular = _resolve_face("Regular", _REGULAR_ENV_VAR, _FC_MATCH_REGULAR_PATTERN)
    bold = _resolve_face("Bold", _BOLD_ENV_VAR, _FC_MATCH_BOLD_PATTERN)
    return regular, bold


def register_for_matplotlib(regular_path: Path) -> str:
    """Register the Regular font with matplotlib and return its family name."""
    from matplotlib import font_manager, rcParams

    font_manager.fontManager.addfont(str(regular_path))
    rcParams["font.family"] = _REGULAR_FAMILY_NAME
    return _REGULAR_FAMILY_NAME


def register_for_reportlab(regular_path: Path, bold_path: Path) -> tuple[str, str]:
    """Register both faces with reportlab and return their (regular, bold) names."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont(_REGULAR_FONT_NAME, str(regular_path)))
    pdfmetrics.registerFont(TTFont(_BOLD_FONT_NAME, str(bold_path)))
    return _REGULAR_FONT_NAME, _BOLD_FONT_NAME


__all__ = [
    "KoreanFontUnavailableError",
    "register_for_matplotlib",
    "register_for_reportlab",
    "resolve_korean_font_paths",
]
