"""SHA-256 file digest helper for metric-codex ingest provenance.

Used by school_excel reader and paideia_sources to populate SourceRecord.sha256.
Kept in output/ so it sits next to other provenance helpers (manifest, paths,
determinism) and is easy to find from both ingest and output callers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of all bytes in ``path``.

    Reads the entire file into memory; acceptable for the Bronze-tier Excel
    files this pipeline ingests (typically < 10 MB each).

    Args:
        path: Path to the file whose digest is to be computed.

    Returns:
        64-character lowercase hex string (SHA-256 digest).
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["compute_sha256"]
