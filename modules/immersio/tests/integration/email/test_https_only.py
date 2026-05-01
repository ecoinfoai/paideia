"""Integration test — HTTPS-only Gmail API client (T053).

The googleapiclient discovery URL and Gmail API endpoint MUST be HTTPS.
Plaintext fallback (HTTP) MUST NOT exist in any code path (FR-C06).
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]


def test_no_http_url_in_email_modules() -> None:
    """Reject ``http://`` (non-TLS) literals in any immersio/email module.

    Allowed: ``https://`` URLs, ``http://`` inside docstrings/comments
    that are tagged ALLOW_HARDCODING (none currently).
    """
    email_dir = _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email"
    pattern = re.compile(r'http://[^"\s]+', re.IGNORECASE)
    hits: list[tuple[str, int, str]] = []
    for py in email_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        lines = text.splitlines()
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            line = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
            if "ALLOW_HARDCODING" in line:
                continue
            hits.append((str(py.relative_to(_REPO_ROOT)), line_no, m.group(0)))
    assert not hits, (
        f"FR-C06: HTTP (plaintext) URL detected in email module(s):\n"
        + "\n".join(f"  {p}:{ln} {url!r}" for p, ln, url in hits)
    )


def test_googleapiclient_uses_default_https_endpoint() -> None:
    """Sanity: sender.py builds Gmail API service without explicit URL override.

    The default ``build("gmail", "v1", credentials=creds)`` resolves to
    ``https://gmail.googleapis.com/`` — no HTTP fallback. We verify by
    inspecting the source for the absence of ``api_endpoint=`` /
    ``discoveryServiceUrl=`` HTTP overrides.
    """
    sender = _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email" / "sender.py"
    text = sender.read_text(encoding="utf-8")
    # Defence: no override pointing at a non-googleapis.com host
    assert "api_endpoint=" not in text, (
        "sender.py must use the default Gmail API endpoint (https only)"
    )
    assert "discoveryServiceUrl=" not in text, (
        "sender.py must use the default discovery URL (https only)"
    )
