"""Phase E manifest writer (T046)."""

from __future__ import annotations

import json
from pathlib import Path

from paideia_shared.schemas import EmailManifest


def write_email_manifest(manifest: EmailManifest, gold_dir: Path) -> Path:
    """Serialise ``EmailManifest`` to ``manifest_email.json`` deterministically.

    Args:
        manifest: Validated manifest model.
        gold_dir: Gold output directory. Parent dirs created if missing.

    Returns:
        Path to the written manifest file.

    Determinism: ``json.dumps(sort_keys=True, ensure_ascii=False, indent=2)``
    so re-runs produce byte-identical bytes when inputs are identical.
    """
    if not isinstance(gold_dir, Path):
        raise TypeError(
            f"write_email_manifest: gold_dir must be Path, got {type(gold_dir).__name__}"
        )
    gold_dir.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json")
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    out = gold_dir / "manifest_email.json"
    out.write_text(text, encoding="utf-8")
    return out


__all__ = ["write_email_manifest"]
