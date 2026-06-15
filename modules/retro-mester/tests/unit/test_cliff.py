"""T044 — Unit tests for align/cliff.py (cognitive-cliff detection).

RED phase: all tests must fail until align/cliff.py is implemented.

Cliff detection rule (authoritative spec):
- For each chapter, collect item_type rates from all items.
- Knowledge-anchor: the rate for '지식축적' items in that chapter.
- A cliff exists for item_types whose rate is BELOW
  (지식축적 rate - cognitive_cliff_drop) — i.e., comprehension/application
  collapsing relative to knowledge recall.
- If '지식축적' items are absent for a chapter, no cliff is detected for that chapter.
- dominant_failing_level: the item_type with the lowest rate among the failing
  ones; returns '미상' when no cliff exists.
"""

from __future__ import annotations

import json

from paideia_shared.schemas import ItemStatistics, RetroMesterConfig


def _make_item(
    item_no: int,
    chapter: str,
    item_type: str,
    correct_rate: float,
) -> ItemStatistics:
    return ItemStatistics(
        item_no=item_no,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=None,
        item_type=item_type,
        difficulty_level=3,
        expected_difficulty="보통",
        source="형성평가",
        correct_answer=1,
        n_responders=20,
        n_correct=round(correct_rate * 20),
        n_omit=0,
        correct_rate=correct_rate,
        omit_rate=0.0,
        discrimination_index=0.25,
        point_biserial=0.35,
        top_distractor_no=2,
        top_distractor_rate=0.20,
        is_top_distractor_adjacent=False,
        option_distribution={1: correct_rate, 2: 0.2, 3: 0.2, 4: 0.3, 5: 0.3 - correct_rate}
        if correct_rate <= 0.7 else {1: correct_rate, 2: 0.1, 3: 0.1, 4: 0.1, 5: 0.7 - correct_rate},
        distractor_label="특이사항 없음",
    )


def _make_config(cliff_drop: float = 0.15) -> RetroMesterConfig:
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster={"2026000001": "학령기"},
        unit_importance={"1장": "상"},
        gap_threshold=0.6,
        cognitive_cliff_drop=cliff_drop,
    )


class TestChapterItemTypeRates:
    """Tests for chapter_item_type_rates()."""

    def test_single_chapter_single_type(self) -> None:
        """Single item returns correct rate for that item_type."""
        from retro_mester.align.cliff import chapter_item_type_rates

        items = [_make_item(1, "1장", "지식축적", 0.80)]
        result = chapter_item_type_rates(items)
        assert "1장" in result
        assert abs(result["1장"]["지식축적"] - 0.80) < 1e-9

    def test_mean_across_multiple_items_same_type(self) -> None:
        """Multiple items of same type → mean correct_rate."""
        from retro_mester.align.cliff import chapter_item_type_rates

        items = [
            _make_item(1, "1장", "이해", 0.60),
            _make_item(2, "1장", "이해", 0.80),
        ]
        result = chapter_item_type_rates(items)
        assert abs(result["1장"]["이해"] - 0.70) < 1e-9

    def test_multiple_types_in_chapter(self) -> None:
        """Multiple item_types in one chapter all returned."""
        from retro_mester.align.cliff import chapter_item_type_rates

        items = [
            _make_item(1, "2장", "지식축적", 0.80),
            _make_item(2, "2장", "이해", 0.60),
            _make_item(3, "2장", "적용", 0.40),
        ]
        result = chapter_item_type_rates(items)
        assert "2장" in result
        assert abs(result["2장"]["지식축적"] - 0.80) < 1e-9
        assert abs(result["2장"]["이해"] - 0.60) < 1e-9
        assert abs(result["2장"]["적용"] - 0.40) < 1e-9

    def test_multiple_chapters_isolated(self) -> None:
        """Rates are isolated per chapter."""
        from retro_mester.align.cliff import chapter_item_type_rates

        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "2장", "지식축적", 0.50),
        ]
        result = chapter_item_type_rates(items)
        assert abs(result["1장"]["지식축적"] - 0.80) < 1e-9
        assert abs(result["2장"]["지식축적"] - 0.50) < 1e-9

    def test_empty_items_returns_empty(self) -> None:
        """Empty item list returns empty dict."""
        from retro_mester.align.cliff import chapter_item_type_rates

        assert chapter_item_type_rates([]) == {}


class TestDetectCliff:
    """Tests for detect_cliff()."""

    def test_cliff_detected_when_comprehension_drops(self) -> None:
        """이해 rate drops more than cliff_drop below 지식축적 rate → cliff."""
        from retro_mester.align.cliff import detect_cliff

        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "1장", "이해", 0.50),  # 0.80 - 0.50 = 0.30 > 0.15
        ]
        config = _make_config(cliff_drop=0.15)
        result = detect_cliff(items, config)
        assert "1장" in result
        assert "이해" in result["1장"]

    def test_no_cliff_when_drop_is_small(self) -> None:
        """Drop less than cliff_drop → no cliff."""
        from retro_mester.align.cliff import detect_cliff

        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "1장", "이해", 0.70),  # 0.80 - 0.70 = 0.10 < 0.15
        ]
        config = _make_config(cliff_drop=0.15)
        result = detect_cliff(items, config)
        # Either 1장 not in result, or 이해 not failing
        assert "1장" not in result or "이해" not in result.get("1장", [])

    def test_cliff_threshold_boundary_strict(self) -> None:
        """Exactly at threshold (equal) → NOT a cliff (strict less-than)."""
        from retro_mester.align.cliff import detect_cliff

        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "1장", "이해", 0.65),  # 0.80 - 0.65 = 0.15 exactly
        ]
        config = _make_config(cliff_drop=0.15)
        result = detect_cliff(items, config)
        # Strict: equal does NOT trigger cliff
        assert "1장" not in result or "이해" not in result.get("1장", [])

    def test_multiple_failing_types(self) -> None:
        """Both 이해 and 적용 can fail in same chapter."""
        from retro_mester.align.cliff import detect_cliff

        items = [
            _make_item(1, "1장", "지식축적", 0.85),
            _make_item(2, "1장", "이해", 0.60),   # 0.85 - 0.60 = 0.25 > 0.15
            _make_item(3, "1장", "적용", 0.45),   # 0.85 - 0.45 = 0.40 > 0.15
        ]
        config = _make_config(cliff_drop=0.15)
        result = detect_cliff(items, config)
        assert "1장" in result
        assert "이해" in result["1장"]
        assert "적용" in result["1장"]

    def test_no_cliff_when_knowledge_absent(self) -> None:
        """Chapter with no 지식축적 items → no cliff (no anchor)."""
        from retro_mester.align.cliff import detect_cliff

        items = [
            _make_item(1, "1장", "이해", 0.40),
            _make_item(2, "1장", "적용", 0.30),
        ]
        config = _make_config(cliff_drop=0.15)
        result = detect_cliff(items, config)
        assert "1장" not in result

    def test_cliff_only_for_chapter_with_drop(self) -> None:
        """Only the chapter with the drop is flagged, not the other."""
        from retro_mester.align.cliff import detect_cliff

        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "1장", "이해", 0.50),   # cliff
            _make_item(3, "2장", "지식축적", 0.80),
            _make_item(4, "2장", "이해", 0.75),   # no cliff
        ]
        config = _make_config(cliff_drop=0.15)
        result = detect_cliff(items, config)
        assert "1장" in result
        assert "2장" not in result

    def test_empty_items_returns_empty(self) -> None:
        """Empty items → empty dict."""
        from retro_mester.align.cliff import detect_cliff

        config = _make_config()
        assert detect_cliff([], config) == {}


class TestDominantFailingLevel:
    """Tests for dominant_failing_level()."""

    def test_returns_lowest_rate_type(self) -> None:
        """Lowest rate among failing types is returned."""
        from retro_mester.align.cliff import dominant_failing_level, chapter_item_type_rates

        items = [
            _make_item(1, "1장", "지식축적", 0.85),
            _make_item(2, "1장", "이해", 0.60),
            _make_item(3, "1장", "적용", 0.40),
        ]
        rates = chapter_item_type_rates(items)
        cliff = {"1장": ["이해", "적용"]}
        result = dominant_failing_level("1장", cliff, rates)
        assert result == "적용"  # 0.40 < 0.60

    def test_returns_미상_when_no_cliff(self) -> None:
        """No cliff for chapter → '미상'."""
        from retro_mester.align.cliff import dominant_failing_level

        cliff: dict[str, list[str]] = {}
        result = dominant_failing_level("1장", cliff, {})
        assert result == "미상"

    def test_single_failing_type(self) -> None:
        """Single failing type is returned directly."""
        from retro_mester.align.cliff import dominant_failing_level, chapter_item_type_rates

        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "1장", "이해", 0.50),
        ]
        rates = chapter_item_type_rates(items)
        cliff = {"1장": ["이해"]}
        result = dominant_failing_level("1장", cliff, rates)
        assert result == "이해"
