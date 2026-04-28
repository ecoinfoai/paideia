"""Hash-derived ISO 8601 timestamp resolver for immersio Phase 1+2.

Spec 004 research §R-10 — manifest.generated_at_utc 단일 소스.

Same input hash → same UTC timestamp; this lets xlsx/pdf/png/parquet emit
byte-identical Producer/CreationDate/Software metadata even when run on
different machines or different days.
"""

from __future__ import annotations

import datetime as _dt
import re

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def resolve_created_at_utc(inputs_sha256: str, override: str | None) -> str:
    """Resolve the canonical ``generated_at_utc`` string for one analyze run.

    Args:
        inputs_sha256: 64-char hex sha256 of concatenated input artefacts
            (exam_item.yaml + omr_xls_concat + attendance + ruleset_version).
            Required: must match ``^[0-9a-f]{64}$``.
        override: When set, must be ISO 8601 UTC (``YYYY-MM-DDTHH:MM:SSZ``)
            and is returned verbatim. Useful for ``--created-at-utc`` CLI
            override.

    Returns:
        ISO 8601 UTC string (``YYYY-MM-DDTHH:MM:SSZ``).

    Raises:
        ValueError: When ``override`` is not ISO 8601, or when
            ``inputs_sha256`` is not a 64-char lowercase hex string.
    """
    if override is not None:
        if not _ISO8601_RE.match(override):
            raise ValueError(
                f"override must be ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ'), got {override!r}"
            )
        return override

    if not _SHA256_RE.match(inputs_sha256):
        raise ValueError(
            f"inputs_sha256 must be 64-char lowercase hex sha256, got {inputs_sha256!r}"
        )

    head = inputs_sha256[:8]
    epoch_seconds = int(head, 16)
    derived = _dt.datetime.fromtimestamp(epoch_seconds, tz=_dt.timezone.utc)
    return derived.strftime("%Y-%m-%dT%H:%M:%SZ")
