"""Unit tests for examen.generate.backend — T015.

TDD: failing tests written BEFORE implementation.

Covers:
- InputHashCache: miss→store→hit byte-identical (cache determinism).
- dry_run_bundles: writes deterministic bundles + calls backend zero times.
- SubscriptionBackend: missing-response raises a clear error (exit-3 territory).
- FakeBackend: deterministic canned responses for testing.
- ApiBackend: only tested via monkeypatch (never hits live API).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
    SubscriptionBackend,
    dry_run_bundles,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_request(slot_id: str = "slot-001") -> GenerationRequest:
    return GenerationRequest(
        slot_id=slot_id,
        prompt="Generate a question about cell biology.",
        context_refs=["textbook_ch8.txt#line42"],
        metadata={"chapter": "8", "difficulty": "medium"},
    )


# ---------------------------------------------------------------------------
# InputHashCache tests
# ---------------------------------------------------------------------------


class TestInputHashCache:
    def test_cache_miss_calls_backend(self, tmp_path: Path) -> None:
        """On cache miss, backend.generate() is called exactly once."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request()

        resp = cache.generate(req)

        assert fake.call_count == 1
        assert resp.raw_text == "fake generated text"
        assert resp.slot_id == "slot-001"

    def test_cache_miss_persists_response(self, tmp_path: Path) -> None:
        """After a cache miss, the response is written to cache_dir."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request()
        cache.generate(req)

        # At least one JSON file should exist in cache_dir
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) == 1

    def test_cache_hit_does_not_call_backend(self, tmp_path: Path) -> None:
        """On cache hit, backend.generate() is NOT called a second time."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request()

        # First call: miss
        resp1 = cache.generate(req)
        assert fake.call_count == 1
        assert resp1.cache_hit is False

        # Second call: hit — backend should NOT be called again
        resp2 = cache.generate(req)
        assert fake.call_count == 1, "backend was called on cache hit!"
        # The hit must be flagged so manifest cache_hit_rate is accurate.
        assert resp2.cache_hit is True
        # Response text must be byte-identical
        assert resp2.raw_text == resp1.raw_text

    def test_cache_hit_returns_byte_identical_response(self, tmp_path: Path) -> None:
        """Cache hit returns the same raw_text as the original miss."""
        fake = FakeBackend("unique response abc123")
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request("slot-xyz")

        resp1 = cache.generate(req)
        resp2 = cache.generate(req)

        assert resp1.raw_text == resp2.raw_text
        assert resp1.raw_text == "unique response abc123"

    def test_different_requests_get_different_cache_entries(self, tmp_path: Path) -> None:
        """Two distinct requests produce two distinct cache files."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)

        req1 = _make_request("slot-001")
        req2 = _make_request("slot-002")

        cache.generate(req1)
        cache.generate(req2)

        assert fake.call_count == 2
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) == 2

    def test_cache_hit_rate_increases_on_hit(self, tmp_path: Path) -> None:
        """cache_hit_rate() returns > 0 after a hit."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        req = _make_request()

        cache.generate(req)  # miss
        cache.generate(req)  # hit

        rate = cache.cache_hit_rate()
        assert rate == 0.5  # 1 hit / 2 total

    def test_cache_hit_rate_zero_initially(self, tmp_path: Path) -> None:
        """cache_hit_rate() returns 0.0 when no requests have been made."""
        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        assert cache.cache_hit_rate() == 0.0

    def test_same_inputs_identical_cache_key(self, tmp_path: Path) -> None:
        """Two GenerationRequest instances with identical fields produce the same key."""
        req_a = GenerationRequest(
            slot_id="s1",
            prompt="same prompt",
            context_refs=["ref1"],
            metadata={"k": "v"},
        )
        req_b = GenerationRequest(
            slot_id="s1",
            prompt="same prompt",
            context_refs=["ref1"],
            metadata={"k": "v"},
        )

        fake = FakeBackend()
        cache = InputHashCache(backend=fake, cache_dir=tmp_path)
        cache.generate(req_a)
        cache.generate(req_b)  # should be a cache hit

        assert fake.call_count == 1


# ---------------------------------------------------------------------------
# dry_run_bundles tests
# ---------------------------------------------------------------------------


class TestDryRunBundles:
    def test_dry_run_writes_bundle_files(self, tmp_path: Path) -> None:
        """dry_run_bundles writes one JSON file per request."""
        requests = [_make_request("slot-001"), _make_request("slot-002")]
        staging = tmp_path / "staging"

        dry_run_bundles(requests, staging_dir=staging)

        written = sorted(staging.glob("*.json"))
        assert len(written) == 2

    def test_dry_run_does_not_call_backend(self, tmp_path: Path) -> None:
        """dry_run_bundles must not call any LLM backend — zero calls."""
        requests = [_make_request("slot-001"), _make_request("slot-002")]
        staging = tmp_path / "staging"
        fake = FakeBackend()

        # dry_run does not accept a backend at all — it writes files only
        dry_run_bundles(requests, staging_dir=staging)

        assert fake.call_count == 0

    def test_dry_run_bundle_is_valid_json(self, tmp_path: Path) -> None:
        """Each bundle file written by dry_run is valid JSON."""
        req = _make_request("slot-abc")
        staging = tmp_path / "staging"

        dry_run_bundles([req], staging_dir=staging)

        files = list(staging.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert "slot_id" in data
        assert data["slot_id"] == "slot-abc"

    def test_dry_run_deterministic(self, tmp_path: Path) -> None:
        """Two dry_run calls with identical inputs produce byte-identical files."""
        req = _make_request("slot-det")
        staging_a = tmp_path / "run_a"
        staging_b = tmp_path / "run_b"

        dry_run_bundles([req], staging_dir=staging_a)
        dry_run_bundles([req], staging_dir=staging_b)

        files_a = sorted(staging_a.glob("*.json"))
        files_b = sorted(staging_b.glob("*.json"))
        assert len(files_a) == len(files_b) == 1
        assert files_a[0].read_bytes() == files_b[0].read_bytes()

    def test_dry_run_creates_staging_dir(self, tmp_path: Path) -> None:
        """dry_run_bundles creates staging_dir if it does not exist."""
        staging = tmp_path / "new" / "staging" / "dir"
        assert not staging.exists()
        dry_run_bundles([], staging_dir=staging)
        assert staging.exists()


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

        # Simulate a pre-filled response file
        resp_data = {
            "slot_id": "slot-001",
            "raw_text": "Claude's generated answer here.",
            "model": "claude-sonnet-4-6",
            "cache_hit": False,
        }
        resp_file = responses / "slot-001.json"
        resp_file.write_text(json.dumps(resp_data), encoding="utf-8")

        resp = backend.generate(req)
        assert resp.slot_id == "slot-001"
        assert resp.raw_text == "Claude's generated answer here."

    def test_missing_response_raises_clear_error(self, tmp_path: Path) -> None:
        """SubscriptionBackend raises RuntimeError when response is missing."""
        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        staging.mkdir()
        responses.mkdir()

        req = _make_request("slot-missing")
        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)

        with pytest.raises(RuntimeError, match="slot-missing"):
            backend.generate(req)

    def test_missing_response_error_mentions_path(self, tmp_path: Path) -> None:
        """SubscriptionBackend error message includes the expected file path."""
        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        staging.mkdir()
        responses.mkdir()

        req = _make_request("slot-xyz")
        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)

        with pytest.raises(RuntimeError) as exc_info:
            backend.generate(req)

        # Error should mention the responses directory so the user knows what to fill
        assert str(responses) in str(exc_info.value) or "slot-xyz" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ApiBackend tests (monkeypatched — never hits live API)
# ---------------------------------------------------------------------------


class TestApiBackend:
    def test_api_backend_uses_temperature_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ApiBackend calls the Anthropic SDK with temperature=0."""
        from examen.generate.backend import ApiBackend

        # Monkeypatch anthropic.Anthropic to avoid any network call
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
            "examen.generate.backend.anthropic.Anthropic", lambda **_: _FakeClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        req = _make_request("slot-api")
        resp = backend.generate(req)

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0].get("temperature") == 0
        assert resp.raw_text == "api response"

    def test_api_backend_raises_on_connection_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ApiBackend raises BackendUnreachableError on connection failure (exit-4)."""
        from examen.generate.backend import ApiBackend, BackendUnreachableError

        class _BrokenMessages:
            def create(self, **kwargs: object) -> None:
                raise ConnectionError("cannot reach anthropic")

        class _BrokenClient:
            messages = _BrokenMessages()

        monkeypatch.setattr(
            "examen.generate.backend.anthropic.Anthropic", lambda **_: _BrokenClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        req = _make_request("slot-fail")

        with pytest.raises(BackendUnreachableError):
            backend.generate(req)
