"""T053 — RED tests for ``retro_mester.llm.cache.InputHashCache``.

Tests must FAIL until the implementation is in place.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_facts() -> dict:
    return {
        "top_changes": [{"chapter": "1장", "segment": "학령기", "cause_hypothesis": "C"}],
        "alignment_flags": [],
        "uncovered_ratio": 0.1,
        "forward_summary": "서약 1건",
    }


# ---------------------------------------------------------------------------
# InputHashCache tests
# ---------------------------------------------------------------------------


class TestInputHashCache:
    """Unit tests for ``retro_mester.llm.cache.InputHashCache``."""

    def test_miss_returns_none(self, tmp_path: Path) -> None:
        """Cache miss returns None on first lookup."""
        from retro_mester.llm.cache import InputHashCache

        cache = InputHashCache(tmp_path / "cache")
        result = cache.get("some prompt", _make_facts())
        assert result is None, "Fresh cache must return None on miss"

    def test_put_then_get_same_key(self, tmp_path: Path) -> None:
        """put() then get() with same inputs returns the stored text."""
        from retro_mester.llm.cache import InputHashCache

        cache = InputHashCache(tmp_path / "cache")
        facts = _make_facts()
        prompt = "주요 빈틈 요약:"
        cache.put(prompt, facts, "cached insight text")

        result = cache.get(prompt, facts)
        assert result == "cached insight text"

    def test_same_inputs_same_hash(self, tmp_path: Path) -> None:
        """Two cache instances with same inputs resolve to same cached value."""
        from retro_mester.llm.cache import InputHashCache

        cache_dir = tmp_path / "cache"
        facts = _make_facts()
        prompt = "요약:"

        # Write via instance 1
        c1 = InputHashCache(cache_dir)
        c1.put(prompt, facts, "result A")

        # Read via instance 2 (new object, same dir)
        c2 = InputHashCache(cache_dir)
        result = c2.get(prompt, facts)
        assert result == "result A", "Same inputs must resolve to same cache file"

    def test_different_facts_different_cache_slot(self, tmp_path: Path) -> None:
        """Different facts produce different cache slots (no collision)."""
        from retro_mester.llm.cache import InputHashCache

        cache = InputHashCache(tmp_path / "cache")
        facts_a = _make_facts()
        facts_b = {**_make_facts(), "uncovered_ratio": 0.9}
        prompt = "요약:"

        cache.put(prompt, facts_a, "result A")
        cache.put(prompt, facts_b, "result B")

        assert cache.get(prompt, facts_a) == "result A"
        assert cache.get(prompt, facts_b) == "result B"

    def test_cache_dir_created_on_put(self, tmp_path: Path) -> None:
        """Cache directory is created automatically on first put."""
        from retro_mester.llm.cache import InputHashCache

        cache_dir = tmp_path / "nested" / "cache"
        assert not cache_dir.exists()

        cache = InputHashCache(cache_dir)
        cache.put("p", _make_facts(), "text")
        assert cache_dir.exists()

    def test_cache_hit_avoids_backend_call(self, tmp_path: Path) -> None:
        """Cache hit: backend callable is NOT invoked on second call.

        Simulates the pattern: first call writes to cache; second call
        with same inputs should return cached value without calling the backend.
        """
        from retro_mester.llm.cache import InputHashCache

        call_count = 0

        def stub_backend(prompt: str, facts: dict) -> str:
            nonlocal call_count
            call_count += 1
            return "backend result"

        cache = InputHashCache(tmp_path / "cache")
        facts = _make_facts()
        prompt = "요약:"

        # First call — cache miss → backend invoked → stored
        result1 = cache.get(prompt, facts)
        if result1 is None:
            result1 = stub_backend(prompt, facts)
            cache.put(prompt, facts, result1)

        # Second call — cache hit → backend NOT invoked
        result2 = cache.get(prompt, facts)
        if result2 is None:
            result2 = stub_backend(prompt, facts)
            cache.put(prompt, facts, result2)

        assert call_count == 1, "Backend must be called exactly once (cache hit on 2nd)"
        assert result1 == result2 == "backend result"
