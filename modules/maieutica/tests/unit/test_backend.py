"""Unit tests for maieutica.generate.backend — T016 (ported from examen T015).

TDD: failing tests written BEFORE implementation.

Covers:
- LLMBackend: abstract — cannot be instantiated directly.
- InputHashCache: miss→store→hit byte-identical, no re-call on hit, key stability.
- SubscriptionBackend: writes bundle, reads response, missing-response raises.
- ApiBackend: temperature=0, unreachable → BackendUnreachableError (monkeypatched).
- Migration: cli.main.BackendUnreachableError is the backend module's class.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from maieutica.generate.backend import (
    ApiBackend,
    BackendUnreachableError,
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
    SubscriptionBackend,
)

# ---------------------------------------------------------------------------
# FakeBackend — deterministic canned backend used in all cache tests
# ---------------------------------------------------------------------------


class FakeBackend(LLMBackend):
    """Canned backend that returns a fixed response and counts calls."""

    def __init__(self, response_text: str = "fake generated text") -> None:
        self._text = response_text
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return a fixed response, incrementing call_count."""
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=self._text,
            model="fake-model",
            cache_hit=False,
        )


def _make_request(slot_id: str = "slot-001") -> GenerationRequest:
    return GenerationRequest(
        slot_id=slot_id,
        prompt="Generate a question about cell biology.",
        context_refs=["textbook_ch8.txt#line42"],
        metadata={"chapter": "8", "difficulty": "medium"},
    )


# ---------------------------------------------------------------------------
# LLMBackend abstract-ness
# ---------------------------------------------------------------------------


class TestLLMBackendAbstract:
    def test_cannot_instantiate_abc(self) -> None:
        """LLMBackend is abstract — direct instantiation raises TypeError."""
        with pytest.raises(TypeError):
            LLMBackend()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# InputHashCache tests
# ---------------------------------------------------------------------------


class TestInputHashCache:
    def test_cache_miss_calls_backend(self, tmp_path: Path) -> None:
        """On cache miss, backend.generate() is called exactly once."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        resp = cache.generate(_make_request())

        assert fake.call_count == 1
        assert resp.raw_text == "fake generated text"
        assert resp.slot_id == "slot-001"

    def test_cache_miss_persists_response(self, tmp_path: Path) -> None:
        """After a cache miss, the response is written to cache_dir."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        cache.generate(_make_request())

        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_cache_hit_does_not_call_backend(self, tmp_path: Path) -> None:
        """On cache hit, backend.generate() is NOT called a second time."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request()

        resp1 = cache.generate(req)
        assert fake.call_count == 1
        assert resp1.cache_hit is False

        resp2 = cache.generate(req)
        assert fake.call_count == 1, "backend was called on cache hit!"
        assert resp2.cache_hit is True
        assert resp2.raw_text == resp1.raw_text

    def test_cache_hit_returns_byte_identical_response(self, tmp_path: Path) -> None:
        """Cache hit returns the same raw_text as the original miss (SC-009)."""
        fake = FakeBackend("unique response abc123")
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request("slot-xyz")

        resp1 = cache.generate(req)
        resp2 = cache.generate(req)

        assert resp1.raw_text == resp2.raw_text == "unique response abc123"

    def test_different_requests_get_different_cache_entries(self, tmp_path: Path) -> None:
        """Two distinct requests produce two distinct cache files (different keys)."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)

        cache.generate(_make_request("slot-001"))
        cache.generate(_make_request("slot-002"))

        assert fake.call_count == 2
        assert len(list(tmp_path.glob("*.json"))) == 2

    def test_cache_hit_rate(self, tmp_path: Path) -> None:
        """cache_hit_rate() reflects hits/total; 0.0 before any call."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        assert cache.cache_hit_rate() == 0.0

        req = _make_request()
        cache.generate(req)  # miss
        cache.generate(req)  # hit
        assert cache.cache_hit_rate() == 0.5

    def test_same_inputs_identical_cache_key(self, tmp_path: Path) -> None:
        """Identical-field requests produce the same key → second call is a hit."""
        req_a = GenerationRequest(
            slot_id="s1", prompt="same prompt", context_refs=["ref1"], metadata={"k": "v"}
        )
        req_b = GenerationRequest(
            slot_id="s1", prompt="same prompt", context_refs=["ref1"], metadata={"k": "v"}
        )
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        cache.generate(req_a)
        cache.generate(req_b)

        assert fake.call_count == 1


# ---------------------------------------------------------------------------
# SubscriptionBackend tests
# ---------------------------------------------------------------------------


class TestSubscriptionBackend:
    def test_read_response_when_present(self, tmp_path: Path) -> None:
        """SubscriptionBackend reads the response JSON when it exists."""
        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        staging.mkdir()
        responses.mkdir()

        req = _make_request("slot-001")
        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)

        resp_data = {
            "slot_id": "slot-001",
            "raw_text": "Claude's generated answer here.",
            "model": "claude-sonnet-4-6",
            "cache_hit": False,
        }
        (responses / "slot-001.json").write_text(json.dumps(resp_data), encoding="utf-8")

        resp = backend.generate(req)
        assert resp.slot_id == "slot-001"
        assert resp.raw_text == "Claude's generated answer here."
        assert resp.model == "claude-sonnet-4-6"

    def test_writes_request_bundle_to_staging(self, tmp_path: Path) -> None:
        """generate() writes the request bundle to staging/{slot_id}.json."""
        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        staging.mkdir()
        responses.mkdir()

        req = _make_request("slot-001")
        resp_data = {"slot_id": "slot-001", "raw_text": "x", "model": "m"}
        (responses / "slot-001.json").write_text(json.dumps(resp_data), encoding="utf-8")

        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)
        backend.generate(req)

        bundle = staging / "slot-001.json"
        assert bundle.exists()
        data = json.loads(bundle.read_text(encoding="utf-8"))
        assert data["slot_id"] == "slot-001"
        assert data["prompt"] == req.prompt

    def test_missing_response_raises_naming_slot(self, tmp_path: Path) -> None:
        """Missing response file raises RuntimeError naming the slot + path."""
        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        staging.mkdir()
        responses.mkdir()

        req = _make_request("slot-missing")
        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)

        with pytest.raises(RuntimeError, match="slot-missing") as exc_info:
            backend.generate(req)
        assert str(responses) in str(exc_info.value)


# ---------------------------------------------------------------------------
# ApiBackend tests (monkeypatched — never hits live API)
# ---------------------------------------------------------------------------


class TestApiBackend:
    def test_api_backend_uses_temperature_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ApiBackend calls the Anthropic SDK with temperature=0."""
        captured_kwargs: list[dict] = []

        class _FakeMessage:
            content = [type("Block", (), {"text": "api response"})()]

        class _FakeMessages:
            def create(self, **kwargs: object) -> _FakeMessage:
                captured_kwargs.append(dict(kwargs))
                return _FakeMessage()

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(
            "maieutica.generate.backend.anthropic.Anthropic", lambda **_: _FakeClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        resp = backend.generate(_make_request("slot-api"))

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0].get("temperature") == 0
        assert resp.raw_text == "api response"

    def test_api_backend_raises_on_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ApiBackend raises BackendUnreachableError on connection failure (exit-4)."""

        class _BrokenMessages:
            def create(self, **kwargs: object) -> None:
                raise ConnectionError("cannot reach anthropic")

        class _BrokenClient:
            messages = _BrokenMessages()

        monkeypatch.setattr(
            "maieutica.generate.backend.anthropic.Anthropic", lambda **_: _BrokenClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(BackendUnreachableError):
            backend.generate(_make_request("slot-fail"))


# ---------------------------------------------------------------------------
# Migration — cli.main.BackendUnreachableError IS the backend module's class
# ---------------------------------------------------------------------------


def test_cli_main_reexports_backend_unreachable_error() -> None:
    """cli.main.BackendUnreachableError must be the SAME object as the backend's.

    Python ``except`` matches by identity, not name — a local duplicate would
    silently fail to catch the backend's exception.
    """
    from maieutica.cli import main

    assert main.BackendUnreachableError is BackendUnreachableError
