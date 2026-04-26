"""Deterministic UTF-8 → CP949 fallback for Korean text inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

EncodingLabel = Literal["utf-8", "cp949"]


def read_text_with_fallback(path: Path) -> tuple[str, EncodingLabel]:
    """Read a text file using a deterministic encoding fallback chain.

    The chain is UTF-8 (BOM-aware) → CP949. The detected encoding is
    returned alongside the decoded text so the caller can record it in
    the ingest manifest (research.md §3).

    Args:
        path: Path to the text file.

    Returns:
        Tuple ``(text, encoding_label)`` where ``encoding_label`` is one of
        ``"utf-8"`` or ``"cp949"``. UTF-8-with-BOM is normalized to
        ``"utf-8"`` for manifest consistency.

    Raises:
        TypeError: If path is not a pathlib.Path.
        FileNotFoundError: If the file does not exist.
        ValueError: If neither UTF-8 nor CP949 decodes successfully.
    """
    if not isinstance(path, Path):
        raise TypeError(
            f"read_text_with_fallback: expected pathlib.Path, got "
            f"{type(path).__name__}."
        )
    raw_bytes = path.read_bytes()
    for codec, label in (("utf-8-sig", "utf-8"), ("utf-8", "utf-8"), ("cp949", "cp949")):
        try:
            decoded = raw_bytes.decode(codec)
        except UnicodeDecodeError:
            continue
        return decoded, label  # type: ignore[return-value]
    raise ValueError(
        f"read_text_with_fallback: cannot decode {path} as utf-8 or cp949; "
        f"convert the file to UTF-8 before ingestion."
    )
