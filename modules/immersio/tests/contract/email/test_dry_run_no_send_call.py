"""Contract test — dry-run modules MUST NOT call Gmail API send (AV-S4).

The static-search guard complements the runtime ``responses.assert_call_count == 0``
in test_dry_run_184_preview.py: even if integration coverage drops, a bare
``messages().send(`` call site appearing in any of the dry-run-path
modules (roster, pdf_scan, master_check, pdf_verify, composer, preview,
manifest, report, pipeline) is detected and fails this test.

Phase 4 (US2 self-test) and beyond legitimately use the call site in
``sender.py`` — that file is *not* part of the dry-run scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]

_DRY_RUN_MODULES: tuple[Path, ...] = (
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "roster.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "pdf_scan.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "master_check.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "pdf_verify.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "composer.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "preview.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "manifest.py",
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "report.py",
    # pipeline.py is included until Phase 4 wires sender.py — at that point
    # the call site lives in sender.py and pipeline only delegates.
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "pipeline.py",
)

_SEND_CALL_RE = re.compile(r"messages\(\)\.send\(")
_GOOGLEAPICLIENT_IMPORT_RE = re.compile(
    r"^\s*(import|from)\s+googleapiclient\b", re.MULTILINE
)


def test_dry_run_modules_have_no_gmail_send_call() -> None:
    """No ``messages().send(`` literal in any dry-run-path module."""
    hits: list[tuple[str, str]] = []
    for path in _DRY_RUN_MODULES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for m in _SEND_CALL_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append((str(path.relative_to(_REPO_ROOT)), str(line_no)))
    assert not hits, (
        "AV-S4: Gmail API send() call site detected in dry-run module(s):\n"
        + "\n".join(f"  {p}:{ln}" for p, ln in hits)
    )


def test_dry_run_modules_do_not_import_googleapiclient() -> None:
    """No ``import googleapiclient`` in any dry-run-path module."""
    hits: list[tuple[str, str]] = []
    for path in _DRY_RUN_MODULES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for m in _GOOGLEAPICLIENT_IMPORT_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append((str(path.relative_to(_REPO_ROOT)), str(line_no)))
    assert not hits, (
        "AV-S4: googleapiclient import detected in dry-run module(s):\n"
        + "\n".join(f"  {p}:{ln}" for p, ln in hits)
    )
