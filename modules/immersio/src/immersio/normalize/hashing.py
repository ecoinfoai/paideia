"""SHA-256 file hashing utility for manifest provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 64 * 1024


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file (chunked, 64KiB).

    Args:
        path: Path to the file.

    Returns:
        64-character lowercase hex digest.

    Raises:
        TypeError: If path is not a pathlib.Path.
        FileNotFoundError: If the file does not exist (propagated from open).
    """
    if not isinstance(path, Path):
        raise TypeError(f"sha256_file: expected pathlib.Path, got {type(path).__name__}.")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
