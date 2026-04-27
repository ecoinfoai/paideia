"""Korean font (NanumGothic) resolution + matplotlib/reportlab registration.

v0.1.1 US1 (T022). Two NanumGothic faces — Regular + Bold — are required
at every needs-map run. Their paths are resolved at CLI entry and pinned
into the run's ``manifest.font_resolution`` (T026) so a re-run can detect
font changes via the optional sha256 fields.

Resolution order, per spec FR-002 + R-01:

1. ``PAIDEIA_KR_FONT_PATH`` env-var (Regular) /
   ``PAIDEIA_KR_FONT_BOLD_PATH`` env-var (Bold) — operator override.
2. ``fc-match -f '%{file}' <pattern>`` for ``'NanumGothic'`` /
   ``'NanumGothic:style=Bold'``.
3. The result string MUST contain ``NanumGothic``; otherwise fontconfig
   silently fell back to e.g. DejaVu Sans and the resolver refuses
   (``KoreanFontUnavailableError``) so the pipeline aborts atomically
   (CLI exit 6).

The resolver returns ``(regular_path, bold_path)`` and is paired with
two registration helpers that hand the resolved paths to matplotlib
(card radar + group distribution PDF) and reportlab (card layout + manual
PDF). Both helpers are idempotent — registering twice is harmless because
matplotlib / reportlab dedupe by font name.

Spec: 003-needs-map-v0-1-1/tasks.md T022; contracts/cli.md "폰트 미해상
메시지 형식"; data-model.md §6 FontResolutionInfo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

_REGULAR_FAMILY_NAME = "NanumGothic"
_BOLD_FAMILY_NAME = "NanumGothic"  # same family, different reportlab face
_REGULAR_FONT_NAME = "NanumGothic"
_BOLD_FONT_NAME = "NanumGothic-Bold"

_FC_MATCH_REGULAR_PATTERN = "NanumGothic"
_FC_MATCH_BOLD_PATTERN = "NanumGothic:style=Bold"

_REGULAR_ENV_VAR = "PAIDEIA_KR_FONT_PATH"
_BOLD_ENV_VAR = "PAIDEIA_KR_FONT_BOLD_PATH"

_FC_MATCH_TIMEOUT_SECONDS = 5.0


class KoreanFontUnavailableError(RuntimeError):
    """Raised when NanumGothic Regular or Bold cannot be resolved.

    The exception's first argument carries the operator-actionable
    multi-line block from contracts/cli.md "폰트 미해상 메시지 형식". The
    CLI entry-point (T023) writes ``str(exc)`` to stderr verbatim and
    exits with code 6.
    """


FaceKind = Literal["Regular", "Bold"]


def resolve_korean_font_paths() -> tuple[Path, Path]:
    """Resolve NanumGothic Regular + Bold paths or raise KoreanFontUnavailableError.

    Returns:
        ``(regular_path, bold_path)`` — both ``Path`` objects pointing at
        existing files whose path strings contain ``NanumGothic``.

    Raises:
        KoreanFontUnavailableError: When either face cannot be resolved.
        The exception message carries the multi-line block defined in
        contracts/cli.md so the CLI can stream it to stderr unchanged.
    """
    regular = _resolve_face("Regular", _REGULAR_ENV_VAR, _FC_MATCH_REGULAR_PATTERN)
    bold = _resolve_face("Bold", _BOLD_ENV_VAR, _FC_MATCH_BOLD_PATTERN)
    return regular, bold


def _resolve_face(face: FaceKind, env_var: str, fc_pattern: str) -> Path:
    """Resolve one face. env-var first, then fc-match, then validate."""
    env_value = os.environ.get(env_var)
    if env_value:
        env_path = Path(env_value)
        if not env_path.is_file():
            raise KoreanFontUnavailableError(
                _format_error_block(
                    face=face,
                    env_var=env_var,
                    env_var_status=f"set → {env_value} (file not found)",
                    fc_pattern=fc_pattern,
                    fc_match_status="not consulted (env-var set)",
                    fc_match_path=None,
                )
            )
        return env_path

    # fc-match path
    fc_match_path = _run_fc_match(fc_pattern)
    if fc_match_path is None:
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status="not set",
                fc_pattern=fc_pattern,
                fc_match_status="fc-match command failed (subprocess unavailable)",
                fc_match_path=None,
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
                fc_match_path=fc_match_path,
            )
        )
    if not fc_match_path.is_file():
        raise KoreanFontUnavailableError(
            _format_error_block(
                face=face,
                env_var=env_var,
                env_var_status="not set",
                fc_pattern=fc_pattern,
                fc_match_status=(
                    f"matched {fc_match_path} but the file does not exist"
                ),
                fc_match_path=fc_match_path,
            )
        )
    return fc_match_path


def _run_fc_match(pattern: str) -> Path | None:
    """Invoke ``fc-match -f '%{file}' <pattern>`` and return the resulting Path.

    Returns ``None`` if fc-match is missing or exits non-zero.
    """
    try:
        # fc-match is a fixed system binary; ``pattern`` is a literal
        # fontconfig query string controlled by this module (no operator
        # input flows into it). Tests monkeypatch ``subprocess.run`` so the
        # real fc-match is never called from the test suite.
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


def _format_error_block(
    *,
    face: FaceKind,
    env_var: str,
    env_var_status: str,
    fc_pattern: str,
    fc_match_status: str,
    fc_match_path: Path | None,
) -> str:
    """Build the multi-line stderr block per contracts/cli.md "폰트 미해상 메시지 형식"."""
    family_label = f"NanumGothic {face}"
    lines = [
        f"ERROR: Required Korean font {family_label!r} not resolved.",
        "  Tried (in order):",
        f"    1. {env_var} (env-var)            → {env_var_status}",
        f"    2. fc-match {fc_pattern!r}              → {fc_match_status}",
    ]
    if fc_match_path is not None and "NanumGothic" not in str(fc_match_path):
        lines.append(
            "                                                       "
            "(NanumGothic not in result path)"
        )
    lines.extend(
        [
            "  Install:",
            "    NixOS:        home.packages = [ pkgs.nanum ];        # or pkgs.nanum-coding",
            "    Ubuntu/Debian: sudo apt install fonts-nanum",
            "    macOS:         brew install --cask font-nanum-gothic",
            f"  Then re-run, or set {env_var} to a verified {face} .ttf path.",
            "Exit code: 6",
        ]
    )
    return "\n".join(lines)


def register_for_matplotlib(regular_path: Path) -> str:
    """Register the Regular font with matplotlib and return its family name.

    matplotlib needs the family name in ``rcParams['font.family']``. Bold is
    drawn from the same family via the ``weight='bold'`` attribute, so we
    only register Regular here. The function is idempotent — calling it
    twice is a no-op because ``font_manager.fontManager.addfont`` dedupes
    by file path.
    """
    # Imported lazily so import-time cost stays low for non-card paths.
    from matplotlib import font_manager, rcParams

    font_manager.fontManager.addfont(str(regular_path))
    rcParams["font.family"] = _REGULAR_FAMILY_NAME
    return _REGULAR_FAMILY_NAME


def register_for_reportlab(
    regular_path: Path, bold_path: Path
) -> tuple[str, str]:
    """Register both faces with reportlab and return their (regular, bold) names.

    Reportlab tracks faces by *name*, not family. Card layout / manual PDF
    code feeds these names into ParagraphStyle / TableStyle.
    Idempotent — reportlab raises if the same name is registered twice with
    a different file, but registering with the same path is silently
    ignored, which is what we want.
    """
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
