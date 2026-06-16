"""NanumGothic font resolution for retro-mester PDF output.

Self-contained copy of ``immersio.fonts`` so retro-mester has no
runtime dependency on the immersio module.  API is identical; sync
manually if immersio's version changes.

Resolution order:
1. ``PAIDEIA_KR_FONT_PATH`` / ``PAIDEIA_KR_FONT_BOLD_PATH`` env-vars.
2. ``fc-match -f '%{{file}}' NanumGothic`` / ``NanumGothic:style=Bold``.

Raises ``KoreanFontUnavailableError`` when neither source yields a
``NanumGothic`` path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

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
    """Raised when NanumGothic Regular or Bold cannot be resolved."""


def _format_error_block(
    *,
    face: FaceKind,
    env_var: str,
    env_var_status: str,
    fc_pattern: str,
    fc_match_status: str,
) -> str:
    return "\n".join(
        [
            f"ERROR: Required Korean font 'NanumGothic {face}' not resolved.",
            "  Tried (in order):",
            f"    1. {env_var} (env-var)            → {env_var_status}",
            f"    2. fc-match {fc_pattern!r}              → {fc_match_status}",
            "  Install: NixOS: home.packages = [ pkgs.nanum ];",
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
    return Path(output) if output else None


def _resolve_face(face: FaceKind, env_var: str, fc_pattern: str) -> Path:
    env_value = os.environ.get(env_var)
    if env_value:
        candidate = Path(env_value)
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError):
            raise KoreanFontUnavailableError(
                _format_error_block(
                    face=face,
                    env_var=env_var,
                    env_var_status=f"set → {env_value} (file not found)",
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
            raise KoreanFontUnavailableError(
                _format_error_block(
                    face=face,
                    env_var=env_var,
                    env_var_status=f"set → {resolved} (invalid extension)",
                    fc_pattern=fc_pattern,
                    fc_match_status="not consulted (env-var set)",
                )
            )
        size = resolved.stat().st_size
        if size > _FONT_SIZE_CAP_BYTES:
            raise KoreanFontUnavailableError(
                _format_error_block(
                    face=face,
                    env_var=env_var,
                    env_var_status=f"set → {resolved} (exceeds 50 MB cap)",
                    fc_pattern=fc_pattern,
                    fc_match_status="not consulted (env-var set)",
                )
            )
        return resolved

    fc_path = _run_fc_match(fc_pattern)
    if fc_path is None or "NanumGothic" not in str(fc_path) or not fc_path.is_file():
        status = f"matched {fc_path!r} (not valid)" if fc_path else "fc-match failed"
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status="not set",
                fc_pattern=fc_pattern,
                fc_match_status=status,
            )
        )
    return fc_path


def resolve_korean_font_paths() -> tuple[Path, Path]:
    """Resolve NanumGothic Regular + Bold paths, or raise.

    Returns:
        ``(regular_path, bold_path)`` tuple.

    Raises:
        KoreanFontUnavailableError: When either face cannot be resolved.
    """
    regular = _resolve_face("Regular", _REGULAR_ENV_VAR, _FC_MATCH_REGULAR_PATTERN)
    bold = _resolve_face("Bold", _BOLD_ENV_VAR, _FC_MATCH_BOLD_PATTERN)
    return regular, bold


def register_for_reportlab(regular_path: Path, bold_path: Path) -> tuple[str, str]:
    """Register both NanumGothic faces with reportlab.

    Args:
        regular_path: Path to the Regular .ttf/.otf file.
        bold_path: Path to the Bold .ttf/.otf file.

    Returns:
        Tuple of ``(regular_name, bold_name)`` as registered with reportlab.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont(_REGULAR_FONT_NAME, str(regular_path)))
    pdfmetrics.registerFont(TTFont(_BOLD_FONT_NAME, str(bold_path)))
    return _REGULAR_FONT_NAME, _BOLD_FONT_NAME


__all__ = [
    "KoreanFontUnavailableError",
    "register_for_reportlab",
    "resolve_korean_font_paths",
]
