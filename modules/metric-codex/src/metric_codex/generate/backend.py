"""T043 — LLM backend abstraction for metric-codex generate stage.

Mirrors the verified examen backend pattern, adapted so a *slot* is one student
(keyed by ``pseudonym``).  The LLM is an OPTIONAL polish over a deterministic,
already-cited bundle (헌장 I): the pipeline completes offline with the template,
and PII never reaches the LLM (the request carries only pseudonymized facts).

Provides:
- ``LLMBackend`` — ABC with a single ``generate(request) -> response`` method.
- ``GenerationRequest`` / ``GenerationResponse`` — typed request/response models.
- ``InputHashCache`` — wraps any backend; deterministic SHA-256 cache key prevents
  duplicate LLM calls and yields byte-identical re-runs (DET-03).
- ``SubscriptionBackend`` — file-based: writes the request bundle, reads a
  pre-filled response; missing response → ``RuntimeError`` (exit-3 territory).
- ``ApiBackend`` — Anthropic SDK with ``temperature=0``; any connection/API error
  is wrapped in ``BackendUnreachableError`` (exit-4 territory).
- ``BackendUnreachableError`` — sentinel exception for exit-code-4 mapping.

Cache-key normalization: ``GenerationRequest`` fields serialized to a JSON object
with ``sort_keys=True``, ``ensure_ascii=False``, ``separators=(",",":")`` (no
whitespace) → identical Python object → identical bytes → identical key.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import anthropic

from metric_codex.output.determinism import atomic_write

# ---------------------------------------------------------------------------
# Sentinel exception
# ---------------------------------------------------------------------------


class BackendUnreachableError(RuntimeError):
    """Raised when the API backend cannot be reached (exit-code-4 territory)."""


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationRequest:
    """A single LLM generation request for one student slot.

    The payload is PII-free: ``slot_id`` is a pseudonym and ``facts`` is the
    serialized pseudonymized evidence bundle (no student_id / name / email).

    Attributes:
        slot_id: The student's pseudonym (e.g. ``"S001"``).
        prompt: Full prompt text sent to the LLM.
        facts: Serialized pseudonymized bundle evidence (no PII).
        model: Model identifier string (e.g. ``"claude-sonnet-4-6"``).
        mode: Backend mode label (``"api"`` / ``"subscription"``).
    """

    slot_id: str
    prompt: str
    facts: str
    model: str
    mode: str


@dataclass
class GenerationResponse:
    """The LLM's response for a single student slot.

    Attributes:
        slot_id: Echo of the corresponding ``GenerationRequest.slot_id``.
        raw_text: Raw text returned by the model.
        model: Model identifier string.
        cache_hit: ``True`` if this response was served from the cache.
    """

    slot_id: str
    raw_text: str
    model: str
    cache_hit: bool = False


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LLMBackend(ABC):
    """Abstract LLM backend — single responsibility: one ``generate`` call."""

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a response for the given student slot request.

        Args:
            request: The generation request for one student slot.

        Returns:
            The LLM-generated response.

        Raises:
            RuntimeError: SubscriptionBackend raises when the response file
                is not yet present (exit-3 territory).
            BackendUnreachableError: ApiBackend raises on connection failure
                (exit-4 territory).
        """


# ---------------------------------------------------------------------------
# Input-hash cache
# ---------------------------------------------------------------------------


def _canonical_key(request: GenerationRequest) -> str:
    """Return the SHA-256 hex digest of the canonical JSON form of ``request``.

    Canonical form: all fields serialized to a JSON object with
    ``sort_keys=True``, ``ensure_ascii=False``, ``separators=(",",":")``
    (no trailing whitespace) → identical inputs → identical key.

    Args:
        request: The generation request to hash.

    Returns:
        64-character lowercase hex digest.
    """
    payload = {
        "facts": request.facts,
        "mode": request.mode,
        "model": request.model,
        "prompt": request.prompt,
        "slot_id": request.slot_id,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InputHashCache:
    """Wraps any ``LLMBackend`` with a filesystem-backed deterministic cache.

    Cache-key: ``sha256(canonical(request))`` → ``{cache_dir}/{key}.json``.

    On a cache **miss** the request is forwarded to the wrapped backend and the
    response is persisted atomically.  On a **hit** the response is read from
    disk — the wrapped backend is NOT called — so re-runs with identical inputs
    produce byte-identical Gold outputs (DET-03).

    Args:
        backend: The backend to delegate to on a cache miss.
        cache_dir: Directory where response JSON files are stored.
    """

    def __init__(self, backend: LLMBackend, cache_dir: Path) -> None:
        self._backend = backend
        self._cache_dir = cache_dir
        self._total_calls: int = 0
        self._cache_hits: int = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return a (cached or fresh) response for ``request``.

        Args:
            request: The generation request.

        Returns:
            ``GenerationResponse`` with ``cache_hit=True`` on a cache hit.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        key = _canonical_key(request)
        cache_file = self._cache_dir / f"{key}.json"

        self._total_calls += 1

        if cache_file.exists():
            self._cache_hits += 1
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            return GenerationResponse(
                slot_id=raw["slot_id"],
                raw_text=raw["raw_text"],
                model=raw["model"],
                cache_hit=True,
            )

        response = self._backend.generate(request)
        serialized = json.dumps(
            {
                "slot_id": response.slot_id,
                "raw_text": response.raw_text,
                "model": response.model,
                "cache_hit": False,
            },
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        )
        # Atomic write so a crash mid-write can never leave a corrupt cache .json
        # that a later run would read and skip the backend (헌장 V: no partial output).
        def _write_cache(tmp: Path) -> None:
            tmp.write_text(serialized, encoding="utf-8")

        atomic_write(cache_file, _write_cache)
        return response

    def cache_hit_rate(self) -> float:
        """Return the fraction of calls served from cache since construction.

        Returns:
            Float in ``[0.0, 1.0]``; ``0.0`` if no calls have been made.
        """
        if self._total_calls == 0:
            return 0.0
        return self._cache_hits / self._total_calls


# ---------------------------------------------------------------------------
# Subscription backend (file-based)
# ---------------------------------------------------------------------------


class SubscriptionBackend(LLMBackend):
    """File-based backend for the Claude Code / subscription workflow.

    1. Writes a deterministic *request bundle* JSON to
       ``staging_dir/{slot_id}.json`` (so the operator / Claude Code session
       knows what to polish — PII-free, since slot_id is a pseudonym).
    2. Reads the response from ``responses_dir/{slot_id}.json`` on ``generate``.

    A missing response file raises ``RuntimeError`` (exit-3 territory) with the
    expected path so the operator knows exactly what to fill in.

    Args:
        staging_dir: Where request bundle JSON files are written.
        responses_dir: Where pre-filled response JSON files are expected.
    """

    def __init__(self, staging_dir: Path, responses_dir: Path) -> None:
        self._staging_dir = staging_dir
        self._responses_dir = responses_dir

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Write the request bundle and read the pre-filled response.

        Args:
            request: The generation request for one student slot.

        Returns:
            The ``GenerationResponse`` read from the responses directory.

        Raises:
            RuntimeError: If the response file for ``request.slot_id`` does not
                exist; the message includes the expected path and the slot_id.
        """
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        bundle_data = {
            "facts": request.facts,
            "mode": request.mode,
            "model": request.model,
            "prompt": request.prompt,
            "slot_id": request.slot_id,
        }
        bundle_file = self._staging_dir / f"{request.slot_id}.json"
        bundle_content = json.dumps(bundle_data, sort_keys=True, ensure_ascii=False, indent=2)

        def _write_bundle(tmp: Path) -> None:
            tmp.write_text(bundle_content, encoding="utf-8")

        atomic_write(bundle_file, _write_bundle)

        resp_file = self._responses_dir / f"{request.slot_id}.json"
        if not resp_file.exists():
            raise RuntimeError(
                f"SubscriptionBackend: response not yet provided for slot "
                f"'{request.slot_id}'. "
                f"Expected file: {resp_file}. "
                f"Fill in the response JSON and re-run generate."
            )

        raw = json.loads(resp_file.read_text(encoding="utf-8"))
        return GenerationResponse(
            slot_id=raw["slot_id"],
            raw_text=raw["raw_text"],
            model=raw.get("model", "claude-subscription"),
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# API backend (Anthropic SDK)
# ---------------------------------------------------------------------------


class ApiBackend(LLMBackend):
    """Anthropic SDK backend — calls the API with ``temperature=0``.

    ``temperature=0`` maximizes determinism on the API side; combined with
    ``InputHashCache``, identical inputs produce byte-identical Gold outputs.

    Args:
        model: The Anthropic model ID (e.g. ``"claude-sonnet-4-6"``).
        max_tokens: Maximum tokens in the completion.

    Raises:
        BackendUnreachableError: Wraps any connection/API error so the CLI can
            map it to exit code 4.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Call the Anthropic API and return the response.

        Args:
            request: The generation request.

        Returns:
            ``GenerationResponse`` with the model's text output.

        Raises:
            BackendUnreachableError: On any network or API failure.
        """
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": request.prompt}],
            )
        except Exception as exc:
            raise BackendUnreachableError(
                f"ApiBackend: failed to reach LLM (model={self._model}): {exc}"
            ) from exc

        raw_text = message.content[0].text if message.content else ""
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw_text,
            model=self._model,
            cache_hit=False,
        )


__all__ = [
    "ApiBackend",
    "BackendUnreachableError",
    "GenerationRequest",
    "GenerationResponse",
    "InputHashCache",
    "LLMBackend",
    "SubscriptionBackend",
]
