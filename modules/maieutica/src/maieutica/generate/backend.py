"""T016 — LLM backend abstraction: interface, cache, backends, dry-run writer.

Ported from ``examen.generate.backend`` (T015) — keeps class names, method
signatures, normalization, and error-handling idioms identical.

Provides:
- ``LLMBackend`` — ABC with a single ``generate(request) -> response`` method.
- ``GenerationRequest`` / ``GenerationResponse`` — typed request/response models.
- ``InputHashCache`` — wraps any ``LLMBackend``; deterministic SHA-256 cache key
  prevents duplicate LLM calls and ensures byte-identical re-runs (SC-009).
- ``SubscriptionBackend`` — file-based: writes bundle, reads pre-filled response
  from a responses directory (filled by a Claude Code/subscription session).
  Raises ``RuntimeError`` if the response file is missing (exit-3 territory).
- ``ApiBackend`` — calls the Anthropic SDK with ``temperature=0``.  On any
  connection/API error raises ``BackendUnreachableError`` (exit-4 territory).
- ``dry_run_bundles`` — writes generation-request bundles deterministically to a
  staging area WITHOUT calling any backend (헌장 I — LLM 없어도 완주).
- ``BackendUnreachableError`` — canonical sentinel exception for exit-code-4
  mapping (imported by ``maieutica.cli.main``).

Design notes
------------
캐시 키 정규화: ``GenerationRequest`` 필드를 알파벳 순 정렬한 JSON 문자열의
SHA-256 hex digest. JSON 직렬화 시 ``sort_keys=True``, ``ensure_ascii=False``,
``separators=(",",":")`` (공백 없음) → 동일 Python 객체 → 동일 바이트 → 동일 키.

``SubscriptionBackend``의 번들 파일명은 ``{slot_id}.json``,
응답 파일명은 ``{slot_id}.json`` (responses_dir 하위).
사용자(또는 Claude Code 세션)가 응답 파일을 채워 넣으면 다음 ``generate()`` 호출 시
읽혀 캐시에 저장된다.

``ApiBackend``는 실제 네트워크 호출을 수행하므로 테스트에서는 monkeypatch 로
``anthropic.Anthropic`` 을 대체해 사용한다 (test_backend.py 참조).
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from maieutica.output.paths import atomic_write

# ---------------------------------------------------------------------------
# Sentinel exception
# ---------------------------------------------------------------------------


class BackendUnreachableError(RuntimeError):
    """Raised when the API backend cannot be reached (exit-code-4 territory)."""


# ---------------------------------------------------------------------------
# Request / Response models (plain dataclasses — no Pydantic, no I/O side-effects)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationRequest:
    """A single LLM generation request for one exam-slot.

    Args:
        slot_id: Unique slot identifier (e.g. ``"slot-001"``).
        prompt: Full prompt text sent to the LLM.
        context_refs: List of source-reference strings
            (e.g. ``["textbook_ch8.txt#line42"]``).
        metadata: Arbitrary key-value metadata (chapter, difficulty, …).
            Must be JSON-serialisable.
    """

    slot_id: str
    prompt: str
    # NOTE: ``frozen=True`` is *shallow* — the list/dict below are still mutable.
    # Callers MUST NOT mutate ``context_refs``/``metadata`` after construction,
    # or the cache key (derived from these fields) would diverge silently.
    context_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResponse:
    """The LLM's response for a single exam-slot.

    Args:
        slot_id: Echo of the corresponding ``GenerationRequest.slot_id``.
        raw_text: Raw text returned by the model.
        model: Model identifier string (e.g. ``"claude-sonnet-4-6"``).
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
        """Generate a response for the given slot request.

        Args:
            request: The generation request for one exam slot.

        Returns:
            The LLM-generated response.

        Raises:
            RuntimeError: SubscriptionBackend raises when the response file
                is not yet present (exit-3 territory).
            BackendUnreachableError: ApiBackend raises on connection failure
                (exit-4 territory).
        """

    def cache_salt(self, request: GenerationRequest) -> str:
        """Extra cache-key material that varies with an out-of-band source.

        The default is empty, so request-keyed caching is unchanged for pure
        backends (e.g. ``ApiBackend``).  File-backed backends override this to
        fold the on-disk response content into the cache key so an edited
        response is never shadowed by a stale cache entry (v0.1.2).

        Args:
            request: The generation request whose response source to fingerprint.

        Returns:
            A short fingerprint string, or ``""`` for no extra keying.
        """
        return ""


# ---------------------------------------------------------------------------
# Input-hash cache
# ---------------------------------------------------------------------------


def _canonical_key(request: GenerationRequest) -> str:
    """Return the SHA-256 hex digest of the canonical JSON form of ``request``.

    Canonical form: all fields serialised to a JSON object with
    ``sort_keys=True``, ``ensure_ascii=False``, ``separators=(",",":")``
    (no trailing whitespace).  ``context_refs`` list order is preserved
    (order matters — same order → same key).

    Args:
        request: The generation request to hash.

    Returns:
        64-character lowercase hex digest.
    """
    # context_refs list 는 순서 보존 (항목 순서가 프롬프트에 의미 있음)
    payload: dict[str, Any] = {
        "context_refs": list(request.context_refs),
        "metadata": request.metadata,
        "prompt": request.prompt,
        "slot_id": request.slot_id,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InputHashCache:
    """Wraps any ``LLMBackend`` with a filesystem-backed deterministic cache.

    Cache-key: ``sha256(canonical(request))`` → ``{cache_dir}/{key}.json``.

    On a cache **miss** the request is forwarded to the wrapped backend and
    the response is persisted.  On a **hit** the response is read from disk —
    the wrapped backend is not called.  This guarantees that re-runs with
    identical inputs produce byte-identical Gold outputs (SC-009).

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
        # Fold any backend-supplied salt (e.g. a file-backed response's content
        # hash) into the key so an edited out-of-band response is not shadowed
        # by a stale cache entry. Empty salt → key unchanged (api determinism).
        salt = self._backend.cache_salt(request)
        if salt:
            key = hashlib.sha256(f"{key}:{salt}".encode("utf-8")).hexdigest()
        cache_file = self._cache_dir / f"{key}.json"

        self._total_calls += 1

        if cache_file.exists():
            # 캐시 히트 — 백엔드 호출 없이 디스크에서 읽기
            self._cache_hits += 1
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            return GenerationResponse(
                slot_id=raw["slot_id"],
                raw_text=raw["raw_text"],
                model=raw["model"],
                cache_hit=True,
            )

        # 캐시 미스 — 백엔드 호출 후 응답 저장
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
        # Atomic write (temp→os.replace) so a crash mid-write can never leave a
        # corrupt/partial cache .json — a later run would otherwise read garbage
        # and skip the backend (constitution V: 부분 산출 금지).
        atomic_write(cache_file, lambda tmp: tmp.write_text(serialized, encoding="utf-8"))
        return response

    def cache_hit_rate(self) -> float:
        """Return the fraction of calls served from cache since construction.

        Returns:
            Float in ``[0.0, 1.0]``.  Returns ``0.0`` if no calls have been made.
        """
        if self._total_calls == 0:
            return 0.0
        return self._cache_hits / self._total_calls


# ---------------------------------------------------------------------------
# Subscription backend (file-based)
# ---------------------------------------------------------------------------


class SubscriptionBackend(LLMBackend):
    """File-based backend for the Claude Code / subscription workflow.

    This backend:
    1. Writes a deterministic *request bundle* JSON to ``staging_dir/{slot_id}.json``
       (so the user / Claude Code session knows what to generate).
    2. Reads the response from ``responses_dir/{slot_id}.json`` when
       ``generate()`` is called.

    If the response file is missing, a ``RuntimeError`` is raised with a
    clear message indicating which file is expected — this is exit-3 territory
    in the CLI (generation/verify step failure).

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
            request: The generation request for one exam slot.

        Returns:
            The ``GenerationResponse`` read from the responses directory.

        Raises:
            RuntimeError: If the response file for ``request.slot_id`` does
                not exist.  The message includes the expected file path and
                the slot_id so the operator knows exactly what to fill in.
        """
        # 번들 파일 기록 (staging 디렉터리)
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        bundle_data = {
            "context_refs": list(request.context_refs),
            "metadata": request.metadata,
            "prompt": request.prompt,
            "slot_id": request.slot_id,
        }
        bundle_file = self._staging_dir / f"{request.slot_id}.json"
        bundle_content = json.dumps(bundle_data, sort_keys=True, ensure_ascii=False, indent=2)
        bundle_file.write_text(bundle_content, encoding="utf-8")

        # 응답 파일 읽기
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

    def cache_salt(self, request: GenerationRequest) -> str:
        """Fingerprint the on-disk response so edits are not cache-shadowed.

        Returns the SHA-256 of ``responses_dir/{slot_id}.json`` bytes when the
        file is present, else ``""``.  An unchanged response keeps a stable key
        (byte-identical re-runs, SC-009); an edited/corrected response yields a
        fresh key so :class:`InputHashCache` re-reads it instead of replaying a
        stale entry (v0.1.2).

        Args:
            request: The generation request whose response file to fingerprint.

        Returns:
            The hex digest of the response file, or ``""`` when it is absent.
        """
        resp_file = self._responses_dir / f"{request.slot_id}.json"
        if not resp_file.exists():
            return ""
        return hashlib.sha256(resp_file.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# API backend (Anthropic SDK)
# ---------------------------------------------------------------------------


class ApiBackend(LLMBackend):
    """Anthropic SDK backend — calls the API with ``temperature=0``.

    This backend uses ``temperature=0`` for maximum determinism on the API
    side.  Combined with ``InputHashCache``, identical inputs produce
    byte-identical Gold outputs.

    Args:
        model: The Anthropic model ID (e.g. ``"claude-sonnet-4-6"``).
        max_tokens: Maximum tokens in the completion.

    Raises:
        BackendUnreachableError: Wraps any connection/API error so the CLI
            can map it to exit code 4.
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


# ---------------------------------------------------------------------------
# dry-run bundle writer
# ---------------------------------------------------------------------------


def dry_run_bundles(
    requests: list[GenerationRequest],
    staging_dir: Path,
) -> None:
    """Write generation-request bundles deterministically WITHOUT calling any backend.

    Each request is serialised to ``staging_dir/{slot_id}.json``.  The files
    are byte-identical across runs for identical inputs (헌장 I 결정론 완주).
    No LLM backend is instantiated or called.

    Args:
        requests: List of generation requests (one per planned exam slot).
        staging_dir: Directory where bundle JSON files are written.
            Created if it does not exist.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)

    for req in requests:
        bundle = {
            "context_refs": list(req.context_refs),
            "metadata": req.metadata,
            "prompt": req.prompt,
            "slot_id": req.slot_id,
        }
        content = json.dumps(bundle, sort_keys=True, ensure_ascii=False, indent=2)
        out = staging_dir / f"{req.slot_id}.json"
        out.write_text(content, encoding="utf-8")


__all__ = [
    "ApiBackend",
    "BackendUnreachableError",
    "GenerationRequest",
    "GenerationResponse",
    "InputHashCache",
    "LLMBackend",
    "SubscriptionBackend",
    "dry_run_bundles",
]
