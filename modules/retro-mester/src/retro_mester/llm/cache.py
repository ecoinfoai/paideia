"""T053 — SHA-256 content-addressed cache for LLM responses.

``InputHashCache`` persists LLM response text keyed by SHA-256 of the
(prompt, facts) pair under the Silver ``cache/`` directory.  Same input →
same cache file → reproducible outputs (FR-025).

Design:
- Key = SHA-256(prompt + canonical JSON of facts).
- Storage = one ``.txt`` file per key under ``cache_dir/``.
- Thread-safe writes via atomic temp-file + rename.
- No expiry; invalidation is manual (delete the cache dir).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class InputHashCache:
    """File-based LLM response cache keyed by SHA-256 of (prompt, facts).

    Args:
        cache_dir: Directory under which cache files are stored.  Created
            automatically on first ``put`` if it does not exist.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, prompt: str, facts: dict) -> str | None:
        """Return cached text for ``(prompt, facts)`` or ``None`` on miss.

        Args:
            prompt: The exact prompt string passed to the LLM backend.
            facts: Structured facts dict used to build the prompt.

        Returns:
            Cached response text, or ``None`` if not present.
        """
        cache_file = self._key_path(prompt, facts)
        if not cache_file.exists():
            return None
        try:
            return cache_file.read_text(encoding="utf-8")
        except OSError:
            return None

    def put(self, prompt: str, facts: dict, text: str) -> None:
        """Store ``text`` in the cache for ``(prompt, facts)``.

        Writes atomically (temp file + os.replace) so a concurrent reader
        never sees a partial file.

        Args:
            prompt: The exact prompt string passed to the LLM backend.
            facts: Structured facts dict used to build the prompt.
            text: LLM response text to cache.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._key_path(prompt, facts)
        # Atomic write via temp file in same directory.
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, cache_file)
        except Exception:
            # Clean up temp file on failure; do not propagate — cache miss
            # is always safe (the caller will regenerate the value).
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cache_key(self, prompt: str, facts: dict) -> str:
        """Compute the SHA-256 hex digest for ``(prompt, facts)``.

        Args:
            prompt: Prompt string.
            facts: Facts dict (serialised canonically via ``json.dumps``
                with ``sort_keys=True``).

        Returns:
            64-character lowercase hex digest string.
        """
        facts_json = json.dumps(facts, sort_keys=True, ensure_ascii=False)
        payload = prompt + "\x00" + facts_json
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _key_path(self, prompt: str, facts: dict) -> Path:
        """Return the Path for the cache file corresponding to ``(prompt, facts)``.

        Args:
            prompt: Prompt string.
            facts: Facts dict.

        Returns:
            Path under ``cache_dir`` for this key.
        """
        return self._dir / (self._cache_key(prompt, facts) + ".txt")


__all__ = ["InputHashCache"]
