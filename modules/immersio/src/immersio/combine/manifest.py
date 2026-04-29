"""``manifest_phase3.json`` writer + schema_version verification (T017).

FR-021 (manifest field set), FR-024 (exit-5 schema mismatch fail-fast),
research §R13 + contracts/manifest_phase3.md determinism policy.

Three public callables:

- :func:`compute_input_sha256` — SHA-256 of an input silver file's bytes.
  Lifts the manifest's six ``*_sha256`` fields out of the writer so
  callers (combine.cli) can probe individual files for stderr reporting
  (FR-024 exit-3 missing input).
- :func:`verify_schema_version` — ``packaging.version.Version`` comparison
  (NOT string lexicographic). Raises :class:`SchemaVersionMismatch` when
  ``actual < minimum`` so callers can surface the FR-024 exit-5 trigger.
- :func:`serialize_manifest_json` / :func:`write_manifest` — canonical
  JSON serialisation (``indent=2, ensure_ascii=False, sort_keys=True`` +
  trailing ``\n``) for byte-identical re-runs (research §R13 vector #1).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packaging.version import InvalidVersion, Version

from paideia_shared.schemas.combined_analysis_manifest import (
    CombinedAnalysisManifest,
)


class SchemaVersionMismatch(ValueError):
    """Raised when a needs-map / immersio Phase 2 silver schema_version is
    lower than the minimum this Phase 3 release requires (FR-024 exit 5)."""


def compute_input_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of an input silver file.

    Uses ``hashlib.sha256(file.read_bytes()).hexdigest()`` rather than a
    streaming hash to keep parity with the contract reference example —
    Phase 3 input files are all small (parquet < 1 MB, json < 10 KB).

    Args:
        path: Existing file path (parquet / json sidecar / manifest).

    Returns:
        Lowercase 64-character hex digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_schema_version(
    actual: str, *, minimum: str, name: str
) -> None:
    """Reject ``actual < minimum`` per ``packaging.version.Version`` semver.

    String lexicographic comparison is *insufficient*: '0.1.10' < '0.1.2'
    by string compare but should be accepted by semver. This wrapper
    enforces the correct ordering.

    Args:
        actual: Version string read from a needs-map / Phase 2 manifest.
        minimum: Lower bound this Phase 3 release expects (inclusive).
        name: Source label for the error message (e.g. "needs-map",
            "immersio Phase 2") — surfaces in the stderr formatter.

    Raises:
        SchemaVersionMismatch: When ``actual < minimum`` or the strings
            cannot be parsed as semver.
    """
    try:
        a = Version(actual)
        m = Version(minimum)
    except InvalidVersion as exc:
        raise SchemaVersionMismatch(
            f"verify_schema_version: {name} schema_version "
            f"{actual!r} is not a valid PEP 440 version (cause: {exc})"
        ) from exc

    if a < m:
        raise SchemaVersionMismatch(
            f"verify_schema_version: {name} schema_version {actual!r} "
            f"is below minimum {minimum!r} required by Phase 3"
        )


def serialize_manifest_json(manifest: CombinedAnalysisManifest) -> str:
    """Serialise a manifest to canonical JSON bytes (as a ``str``).

    Output policy (research §R13 vector #1 + contracts/manifest_phase3.md):
    - ``indent=2`` (matches contract example formatting)
    - ``ensure_ascii=False`` (Korean cluster_label / posthoc literals
      stay readable as-is)
    - ``sort_keys=True`` (key order independent of Pydantic field order)
    - single trailing ``\n`` (POSIX text-file convention; ``Path.write_text``
      does NOT auto-add)

    Args:
        manifest: Validated :class:`CombinedAnalysisManifest`.

    Returns:
        Canonical JSON text terminated by ``\n``.
    """
    payload = manifest.model_dump(mode="json")
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_manifest(manifest: CombinedAnalysisManifest, path: Path) -> None:
    """Write the manifest to ``path`` in canonical form.

    Creates parent directories if absent. Caller is responsible for
    archival — overwrites in place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_manifest_json(manifest), encoding="utf-8")


__all__ = [
    "SchemaVersionMismatch",
    "compute_input_sha256",
    "serialize_manifest_json",
    "verify_schema_version",
    "write_manifest",
]
