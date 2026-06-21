"""LLM backend abstraction for metric-codex generate stage.

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
- ``ApiBackend`` — Anthropic SDK backend; config errors surface as
  ``LocatedInputError`` (exit-2); genuine unreachability surfaces as
  ``BackendUnreachableError`` (exit-4).
- ``BackendUnreachableError`` — sentinel exception for exit-code-4 mapping.

Cache-key normalization: ``GenerationRequest`` fields (including ``max_tokens``)
serialized to a JSON object with ``sort_keys=True``, ``ensure_ascii=False``,
``separators=(",",":")`` (no whitespace) → identical Python object → identical
bytes → identical key.

Note on determinism: ``InputHashCache`` provides cache-hit reproducibility
(DET-03); ``temperature`` is intentionally absent — modern Anthropic models
reject it with a 400, and sampling temperature is not the source of determinism.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import anthropic

from metric_codex.errors import LocatedInputError
from metric_codex.output.determinism import atomic_write

# ---------------------------------------------------------------------------
# Sentinel exceptions
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
        max_tokens: Maximum tokens in the completion (included in cache key so
            requests with different limits never share a cache entry).
    """

    slot_id: str
    prompt: str
    facts: str
    model: str
    mode: str
    max_tokens: int = 2048


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
        "max_tokens": request.max_tokens,
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
        try:
            slot_id_val: str = raw["slot_id"]
            raw_text_val: str = raw["raw_text"]
        except KeyError as exc:
            raise LocatedInputError(
                f"SubscriptionBackend: response file is missing required field {exc}",
                file=str(resp_file),
                expected="JSON object with 'slot_id' and 'raw_text' fields",
                actual=f"keys present: {sorted(raw.keys())}",
            ) from exc
        return GenerationResponse(
            slot_id=slot_id_val,
            raw_text=raw_text_val,
            model=raw.get("model", "claude-subscription"),
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# API backend (Anthropic SDK)
# ---------------------------------------------------------------------------


class ApiBackend(LLMBackend):
    """Anthropic SDK backend.

    Determinism is provided by ``InputHashCache`` (cache-hit reproducibility,
    DET-03).  ``temperature`` is intentionally absent: current Anthropic models
    reject it with a 400 ``BadRequestError``.

    Args:
        model: The Anthropic model ID (e.g. ``"claude-sonnet-4-6"``).
        max_tokens: Maximum tokens in the completion (defaults to 2048;
            threaded from ``GenerationRequest.max_tokens`` at call time).

    Raises:
        LocatedInputError: On config/request errors (``BadRequestError``,
            ``AuthenticationError``, ``PermissionDeniedError``) — exit-2.
        BackendUnreachableError: On genuine unreachability
            (``APIConnectionError``, ``APITimeoutError``, ``ConnectionError``,
            ``TimeoutError``) — exit-4.
    """

    # Refusal stop_reason values — any of these surfaces as a LocatedInputError.
    _REFUSAL_STOP_REASONS = frozenset({"refusal"})

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
            request: The generation request; ``request.max_tokens`` is used
                if the caller overrides the default.

        Returns:
            ``GenerationResponse`` with the model's text output.

        Raises:
            LocatedInputError: On config/request errors (exit-2 territory).
            BackendUnreachableError: On genuine unreachability (exit-4 territory).
        """
        max_tokens = request.max_tokens if request.max_tokens else self._max_tokens
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": request.prompt}],
            )
        except (
            anthropic.BadRequestError,
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
        ) as exc:
            raise LocatedInputError(
                f"ApiBackend: LLM request rejected — check model/API-key config "
                f"(model={self._model}): {exc}",
                expected="valid model ID and API key with permission",
                actual=type(exc).__name__,
            ) from exc
        except (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            ConnectionError,
            TimeoutError,
        ) as exc:
            raise BackendUnreachableError(
                f"ApiBackend: failed to reach LLM (model={self._model}): {exc}"
            ) from exc

        # Guard: refusal stop_reason surfaces as a located error (not silent empty text).
        stop_reason = getattr(message, "stop_reason", None)
        if stop_reason in self._REFUSAL_STOP_REASONS:
            raise LocatedInputError(
                f"ApiBackend: LLM refused the request (stop_reason={stop_reason!r}, "
                f"model={self._model}, slot_id={request.slot_id!r})",
                expected="stop_reason 'end_turn' or 'max_tokens'",
                actual=str(stop_reason),
            )

        # Select the first text block; raise a located error if none is found.
        raw_text: str | None = None
        for block in (message.content or []):
            if getattr(block, "type", None) == "text":
                raw_text = block.text
                break

        if not raw_text:
            raise LocatedInputError(
                f"ApiBackend: LLM returned no usable text block "
                f"(stop_reason={stop_reason!r}, model={self._model}, "
                f"slot_id={request.slot_id!r})",
                expected="at least one text block in content",
                actual=f"content length {len(message.content or [])}",
            )

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
