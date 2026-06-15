"""T049 — Unit tests for validity/gate.py: chapter_validity + validity_signals.

RED phase: written before implementation.

Rules under test:
- 판정불가: chapter has < 2 items (insufficient data).
- 문항수선: majority (share >= 0.5) of items have
    discrimination_index < config.low_discrimination_threshold
  OR majority (share >= 0.5) of items have a bad distractor_label
    in {"역변별 의심 — 출제 재검토", "변별 기여 적음 — 차년도 교체 검토"}.
- 건전: otherwise (2+ items, passes both checks).

Signals verified:
- mean_discrimination: mean of discrimination_index across chapter items.
- low_disc_share: fraction of items with discrimination_index < threshold.
- bad_distractor_share: fraction of items with a bad distractor_label.
"""

from __future__ import annotations

from paideia_shared.schemas import ItemStatistics, RetroMesterConfig

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _make_item(
    item_no: int,
    chapter: str,
    discrimination_index: float = 0.30,
    distractor_label: str = "특이사항 없음",
) -> ItemStatistics:
    """Build a minimal ItemStatistics for the given chapter."""
    n_responders = 20
    n_correct = 10
    cr = n_correct / n_responders
    dist = {1: cr, 2: 0.15, 3: 0.15, 4: 0.10, 5: 0.10}
    return ItemStatistics(
        item_no=item_no,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=1,
        item_type="이해",
        difficulty_level=3,
        expected_difficulty="보통",
        source="형성평가",
        correct_answer=1,
        n_responders=n_responders,
        n_correct=n_correct,
        n_omit=0,
        correct_rate=cr,
        omit_rate=0.0,
        discrimination_index=discrimination_index,
        point_biserial=0.35,
        top_distractor_no=2,
        top_distractor_rate=0.20,
        is_top_distractor_adjacent=True,
        option_distribution=dist,
        distractor_label=distractor_label,  # type: ignore[arg-type]
    )


def _default_config() -> RetroMesterConfig:
    """Return a RetroMesterConfig with low_discrimination_threshold=0.2."""
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster={"2026000001": "학령기", "2026000002": "만학도"},
        unit_importance={"1장": "상"},
        gap_threshold=0.6,
        baseline_segment="만학도",
        low_discrimination_threshold=0.2,
    )


# -------------------------------------------------------------------------
# T049: chapter_validity
# -------------------------------------------------------------------------


class TestChapterValidityInsufficientItems:
    """판정불가 when < 2 items exist for a chapter."""

    def test_zero_items_returns_판정불가(self) -> None:
        """Zero items → 판정불가."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        result = chapter_validity([], config)
        # With empty list the chapter is effectively unknown
        assert result == {}

    def test_single_item_returns_판정불가(self) -> None:
        """Exactly 1 item → 판정불가 for that chapter."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [_make_item(1, "1장")]
        result = chapter_validity(items, config)
        assert result["1장"] == "판정불가"

    def test_two_items_not_판정불가(self) -> None:
        """2 items is sufficient — no 판정불가."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "1장", discrimination_index=0.30),
            _make_item(2, "1장", discrimination_index=0.35),
        ]
        result = chapter_validity(items, config)
        assert result["1장"] != "판정불가"


class TestChapterValidityLowDisc:
    """문항수선 when majority (≥ 0.5 share) have discrimination_index < threshold."""

    def test_all_low_disc_returns_문항수선(self) -> None:
        """All 3 items have disc < 0.2 → majority (1.0) → 문항수선."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "1장", discrimination_index=0.10),
            _make_item(2, "1장", discrimination_index=0.05),
            _make_item(3, "1장", discrimination_index=0.15),
        ]
        result = chapter_validity(items, config)
        assert result["1장"] == "문항수선"

    def test_exactly_half_low_disc_returns_문항수선(self) -> None:
        """2 of 4 items (share = 0.5) → 문항수선 (boundary case)."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "1장", discrimination_index=0.10),  # bad
            _make_item(2, "1장", discrimination_index=0.05),  # bad
            _make_item(3, "1장", discrimination_index=0.30),  # ok
            _make_item(4, "1장", discrimination_index=0.40),  # ok
        ]
        result = chapter_validity(items, config)
        assert result["1장"] == "문항수선"

    def test_minority_low_disc_returns_건전(self) -> None:
        """1 of 4 items (share = 0.25 < 0.5) low-disc → 건전."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "1장", discrimination_index=0.10),  # bad
            _make_item(2, "1장", discrimination_index=0.30),  # ok
            _make_item(3, "1장", discrimination_index=0.35),  # ok
            _make_item(4, "1장", discrimination_index=0.40),  # ok
        ]
        result = chapter_validity(items, config)
        assert result["1장"] == "건전"


class TestChapterValidityBadDistractor:
    """문항수선 when majority (≥ 0.5) have a bad distractor_label."""

    _BAD_1 = "역변별 의심 — 출제 재검토"
    _BAD_2 = "변별 기여 적음 — 차년도 교체 검토"

    def test_majority_역변별_returns_문항수선(self) -> None:
        """2 of 3 items labeled '역변별 의심' → 문항수선."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "2장", discrimination_index=0.30, distractor_label=self._BAD_1),
            _make_item(2, "2장", discrimination_index=0.25, distractor_label=self._BAD_1),
            _make_item(3, "2장", discrimination_index=0.28),  # ok
        ]
        result = chapter_validity(items, config)
        assert result["2장"] == "문항수선"

    def test_majority_변별기여적음_returns_문항수선(self) -> None:
        """2 of 3 items labeled '변별 기여 적음' → 문항수선."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "2장", discrimination_index=0.30, distractor_label=self._BAD_2),
            _make_item(2, "2장", discrimination_index=0.25, distractor_label=self._BAD_2),
            _make_item(3, "2장", discrimination_index=0.28),  # ok
        ]
        result = chapter_validity(items, config)
        assert result["2장"] == "문항수선"

    def test_mixed_bad_labels_majority_returns_문항수선(self) -> None:
        """2 of 4 items (0.5 share) with mixed bad labels → 문항수선."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "3장", discrimination_index=0.30, distractor_label=self._BAD_1),
            _make_item(2, "3장", discrimination_index=0.25, distractor_label=self._BAD_2),
            _make_item(3, "3장", discrimination_index=0.28),  # ok
            _make_item(4, "3장", discrimination_index=0.35),  # ok
        ]
        result = chapter_validity(items, config)
        assert result["3장"] == "문항수선"

    def test_minority_bad_distractor_good_disc_returns_건전(self) -> None:
        """1 of 4 bad distractor but all disc ok → 건전."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "3장", discrimination_index=0.30, distractor_label=self._BAD_1),
            _make_item(2, "3장", discrimination_index=0.30),
            _make_item(3, "3장", discrimination_index=0.35),
            _make_item(4, "3장", discrimination_index=0.40),
        ]
        result = chapter_validity(items, config)
        assert result["3장"] == "건전"


class TestChapterValidityHealthyItems:
    """건전 when 2+ items and neither psychometric check triggers."""

    def test_all_high_disc_no_bad_label_returns_건전(self) -> None:
        """All items have high disc and ok labels → 건전."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "4장", discrimination_index=0.35),
            _make_item(2, "4장", discrimination_index=0.40),
            _make_item(3, "4장", discrimination_index=0.30),
        ]
        result = chapter_validity(items, config)
        assert result["4장"] == "건전"


class TestChapterValidityMultiChapter:
    """Multiple chapters in one call are handled independently."""

    def test_mixed_chapters_independent(self) -> None:
        """One chapter healthy, one bad-disc — verdicts are independent."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "1장", discrimination_index=0.35),
            _make_item(2, "1장", discrimination_index=0.40),
            _make_item(3, "2장", discrimination_index=0.05),  # bad
            _make_item(4, "2장", discrimination_index=0.08),  # bad
        ]
        result = chapter_validity(items, config)
        assert result["1장"] == "건전"
        assert result["2장"] == "문항수선"

    def test_one_item_chapter_returns_판정불가(self) -> None:
        """1-item chapter is 판정불가, 3-item chapter can be 건전."""
        from retro_mester.validity.gate import chapter_validity

        config = _default_config()
        items = [
            _make_item(1, "X장"),  # singleton
            _make_item(2, "Y장", discrimination_index=0.30),
            _make_item(3, "Y장", discrimination_index=0.35),
        ]
        result = chapter_validity(items, config)
        assert result["X장"] == "판정불가"
        assert result["Y장"] == "건전"


# -------------------------------------------------------------------------
# T049: validity_signals
# -------------------------------------------------------------------------


class TestValiditySignals:
    """validity_signals returns correct numeric measurements."""

    def test_signals_mean_discrimination(self) -> None:
        """mean_discrimination is the mean of all items' discrimination_index."""
        from retro_mester.validity.gate import validity_signals

        config = _default_config()
        items = [
            _make_item(1, "1장", discrimination_index=0.10),
            _make_item(2, "1장", discrimination_index=0.30),
        ]
        sigs = validity_signals(items, config)
        assert abs(sigs["mean_discrimination"] - 0.20) < 1e-6

    def test_signals_low_disc_share(self) -> None:
        """low_disc_share is the fraction of items with disc < threshold."""
        from retro_mester.validity.gate import validity_signals

        config = _default_config()  # threshold = 0.2
        items = [
            _make_item(1, "1장", discrimination_index=0.10),  # below
            _make_item(2, "1장", discrimination_index=0.30),  # above
            _make_item(3, "1장", discrimination_index=0.40),  # above
        ]
        sigs = validity_signals(items, config)
        assert abs(sigs["low_disc_share"] - 1 / 3) < 1e-6

    def test_signals_bad_distractor_share(self) -> None:
        """bad_distractor_share is the fraction of items with a bad label."""
        from retro_mester.validity.gate import validity_signals

        config = _default_config()
        items = [
            _make_item(1, "2장", distractor_label="역변별 의심 — 출제 재검토"),
            _make_item(2, "2장"),  # ok
            _make_item(3, "2장"),  # ok
            _make_item(4, "2장"),  # ok
        ]
        sigs = validity_signals(items, config)
        assert abs(sigs["bad_distractor_share"] - 0.25) < 1e-6

    def test_signals_all_clean(self) -> None:
        """Signals are 0 for a perfectly clean chapter."""
        from retro_mester.validity.gate import validity_signals

        config = _default_config()
        items = [
            _make_item(1, "5장", discrimination_index=0.35),
            _make_item(2, "5장", discrimination_index=0.40),
        ]
        sigs = validity_signals(items, config)
        assert sigs["low_disc_share"] == 0.0
        assert sigs["bad_distractor_share"] == 0.0

    def test_signals_empty_items(self) -> None:
        """Empty item list returns all-zero signals."""
        from retro_mester.validity.gate import validity_signals

        config = _default_config()
        sigs = validity_signals([], config)
        assert sigs["mean_discrimination"] == 0.0
        assert sigs["low_disc_share"] == 0.0
        assert sigs["bad_distractor_share"] == 0.0
