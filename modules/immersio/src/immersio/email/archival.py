"""Archival helper for immersio-email gold outputs (T031).

Reuses the analyze-pipeline pattern (``modules/immersio/src/immersio/
analyze/archival.py``): move every prior-run artefact into ``_archive/
{ISO8601_UTC}__v{schema}/`` BEFORE writing new outputs. Constitution V
"부분 산출 금지" — re-runs preserve every prior run losslessly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..analyze.archival import ArchivalError, _archive_one, _detect_schema_version

# Names that the email pipeline writes — archive these on re-run so
# prior-run outputs are preserved losslessly. The Phase 6 PDF directory
# (``이메일_발송용/``) is *not* in this set: it carries student PDFs
# produced upstream and remains in place across re-runs.
_EMAIL_GOLD_OUTPUT_NAMES: frozenset[str] = frozenset({
    "메일_발송로그.csv",
    "메일_발송보고서.md",
    "manifest_email.json",
    "cohort_명단.md",
    "cohort_저득점_명단.md",
    "cohort_나머지_명단.md",
    "_test",  # test-mode subdirectory
})


def archive_previous_run(gold_dir: Path) -> str | None:
    """Move prior-run email outputs into ``_archive/{ISO}__v{ver}/``.

    Args:
        gold_dir: Canonical email gold dir, e.g.
            ``data/gold/immersio/2026-1-anatomy/``. May not exist on
            first run (no-op). The Phase 6 PDF subdirectory
            (``이메일_발송용/``) is preserved in place — it is *input*
            to email, not output.

    Returns:
        Relative archive path string ``"_archive/{name}"`` on success;
        ``None`` on first-run / empty-of-outputs.

    Raises:
        ArchivalError: On any partial failure. Pipeline must abort
            before writing new outputs.
    """
    if not isinstance(gold_dir, Path):
        raise TypeError(
            f"archive_previous_run: gold_dir must be pathlib.Path, got "
            f"{type(gold_dir).__name__}."
        )

    schema_version = _detect_schema_version(gold_dir)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    subdir_name = f"{timestamp}__v{schema_version}"

    # Whitelist mode — only the 7 email-specific output names move.
    return _archive_one(
        gold_dir, subdir_name, only_names=_EMAIL_GOLD_OUTPUT_NAMES
    )


__all__ = ["ArchivalError", "archive_previous_run"]
