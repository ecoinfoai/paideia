"""T052 — Integration: blank review_note after generation, filled after review (US6).

TDD (RED phase): tests written before implementation.

Tests:
- A freshly generated item has review_note == ""
- After review_items with a FakeBackend that returns a finding for that item,
  its review_note contains the finding.
- An item the reviewer passes stays clean (review_note stays empty or unchanged
  from generation).
- review_items appends to existing review_note (does not overwrite).
- review_items is deterministic (same input → same output, run 2-3×).
"""

from __future__ import annotations

import json
from pathlib import Path

from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
)
from paideia_shared.schemas import (
    ExamItemDraft,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"


# ---------------------------------------------------------------------------
# Helpers to build minimal ExamItemDraft items
# ---------------------------------------------------------------------------


def _make_item(
    item_no: int,
    review_note: str = "",
    *,
    key_concept: str | None = None,
) -> ExamItemDraft:
    """Create a minimal valid ExamItemDraft."""
    return ExamItemDraft(
        semester=_SEMESTER,
        course_slug=_COURSE,
        item_no=item_no,
        source="textbook",
        chapter="8장 호흡계통",
        chapter_no=8,
        question_type="지식축적",
        difficulty="2_보통",
        stem_polarity="부정형",
        text="다음 중 폐포에 대한 설명으로 가장 옳지 않은 것은?",
        options=[
            "① " + "가" * 28,
            "② " + "나" * 28,
            "③ " + "다" * 28,
            "④ " + "라" * 28,
            "⑤ " + "마" * 28,
        ],
        answer_no=3,
        distractor_rationale=[
            "옳은 진술: 가.",
            "옳은 진술: 나.",
            "틀린 진술: 다.",
            "옳은 진술: 라.",
            "옳은 진술: 마.",
        ],
        wrong_explanation="오답 설명 텍스트입니다." * 20,
        leap_explanation="도약 설명 텍스트입니다." * 20,
        intent="기본 구조와 기능을 확인한다.",
        option_length_ok=True,
        review_note=review_note,
        key_concept=key_concept,
    )


# ---------------------------------------------------------------------------
# Fake backends for review agent
# ---------------------------------------------------------------------------

# Determines whether item_no has a finding: odd item_nos get a finding.
_FINDING_TEXT = "[review_agent] 정답 모호: 보기 ①과 ③이 유사한 내용을 담고 있습니다."


class FakeReviewBackend(LLMBackend):
    """Returns a canned finding for odd item_nos; passes even item_nos."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        item_no = request.metadata.get("item_no", 0)
        raw_text = _FINDING_TEXT if int(item_no) % 2 == 1 else ""
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw_text,
            model="fake-review",
            cache_hit=False,
        )


class FakeReviewBackendAllFindings(LLMBackend):
    """Returns a canned finding for EVERY item."""

    def __init__(self, finding: str = _FINDING_TEXT) -> None:
        self._finding = finding
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=self._finding,
            model="fake-review-all",
            cache_hit=False,
        )


class FakeReviewBackendNoFindings(LLMBackend):
    """Returns empty text (no issues) for all items."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text="",
            model="fake-review-clean",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# T052 tests
# ---------------------------------------------------------------------------


class TestInitialReviewNoteBlank:
    """US6 SC1: freshly generated item has review_note == ''."""

    def test_generated_item_review_note_is_blank(self) -> None:
        """A freshly created ExamItemDraft has review_note='' by default."""
        item = _make_item(1)
        assert item.review_note == "", (
            f"Expected empty review_note, got {item.review_note!r}"
        )

    def test_generated_item_review_note_is_empty_string(self) -> None:
        """review_note defaults to '' not None."""
        item = _make_item(2)
        assert item.review_note is not None
        assert item.review_note == ""


class TestReviewAgentFillsNote:
    """US6 SC2: after review_items, problematic items get review_note filled."""

    def test_finding_item_gets_note(self, tmp_path: Path) -> None:
        """Item with odd item_no (triggers finding) gets review_note filled."""
        from examen.verify.review_agent import review_items

        items = [_make_item(1), _make_item(2), _make_item(3)]
        backend = FakeReviewBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        reviewed = review_items(items, backend=backend, cache=cache)

        # item_no=1 (odd) → should have a finding
        item_1 = next(i for i in reviewed if i.item_no == 1)
        assert item_1.review_note != "", (
            "item_no=1 expected a review finding but review_note is empty"
        )
        assert _FINDING_TEXT in item_1.review_note, (
            f"Expected finding text in review_note, got: {item_1.review_note!r}"
        )

    def test_clean_item_stays_clean(self, tmp_path: Path) -> None:
        """Item with even item_no (passes review) has empty review_note."""
        from examen.verify.review_agent import review_items

        items = [_make_item(1), _make_item(2), _make_item(3)]
        backend = FakeReviewBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        reviewed = review_items(items, backend=backend, cache=cache)

        # item_no=2 (even) → should stay clean
        item_2 = next(i for i in reviewed if i.item_no == 2)
        assert item_2.review_note == "", (
            f"item_no=2 should stay clean but got review_note={item_2.review_note!r}"
        )

    def test_all_items_reviewed(self, tmp_path: Path) -> None:
        """review_items returns a list of same length as input."""
        from examen.verify.review_agent import review_items

        items = [_make_item(i) for i in range(1, 6)]
        backend = FakeReviewBackendAllFindings()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        reviewed = review_items(items, backend=backend, cache=cache)
        assert len(reviewed) == len(items), (
            f"Expected {len(items)} items, got {len(reviewed)}"
        )

    def test_item_nos_preserved(self, tmp_path: Path) -> None:
        """review_items preserves item order and item_no values."""
        from examen.verify.review_agent import review_items

        items = [_make_item(i) for i in range(1, 6)]
        backend = FakeReviewBackendAllFindings()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        reviewed = review_items(items, backend=backend, cache=cache)
        for orig, rev in zip(items, reviewed, strict=True):
            assert orig.item_no == rev.item_no


class TestReviewAgentAppendsNotOverwrites:
    """review_agent appends to review_note, not overwrites."""

    def test_review_appends_to_existing_review_note(self, tmp_path: Path) -> None:
        """If an item already has a review_note, the finding is appended."""
        from examen.verify.review_agent import review_items

        existing_note = "[format_check] stem_polarity 불일치 감지됨"
        item = _make_item(1, review_note=existing_note)  # odd → finding
        backend = FakeReviewBackendAllFindings()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        reviewed = review_items([item], backend=backend, cache=cache)
        result = reviewed[0]

        assert existing_note in result.review_note, (
            "Original review_note was overwritten instead of appended"
        )
        assert _FINDING_TEXT in result.review_note, (
            "New finding was not appended to review_note"
        )

    def test_no_finding_does_not_clear_existing_note(self, tmp_path: Path) -> None:
        """If reviewer finds nothing, existing review_note is unchanged."""
        from examen.verify.review_agent import review_items

        existing_note = "[format_check] some prior note"
        item = _make_item(1, review_note=existing_note)
        backend = FakeReviewBackendNoFindings()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        reviewed = review_items([item], backend=backend, cache=cache)
        result = reviewed[0]

        assert result.review_note == existing_note, (
            f"Expected unchanged review_note={existing_note!r}, "
            f"got {result.review_note!r}"
        )


class TestReviewAgentDeterminism:
    """review_items is deterministic (same input → same output, 2-3×)."""

    def test_deterministic_run1_equals_run2(self, tmp_path: Path) -> None:
        """Two consecutive review_items calls with same input give same output."""
        from examen.verify.review_agent import review_items

        items = [_make_item(i) for i in range(1, 6)]
        backend1 = FakeReviewBackend()
        backend2 = FakeReviewBackend()
        cache1 = InputHashCache(backend=backend1, cache_dir=tmp_path / "cache1")
        cache2 = InputHashCache(backend=backend2, cache_dir=tmp_path / "cache2")

        result1 = review_items(items, backend=backend1, cache=cache1)
        result2 = review_items(items, backend=backend2, cache=cache2)

        for r1, r2 in zip(result1, result2, strict=True):
            assert r1.review_note == r2.review_note, (
                f"item_no={r1.item_no}: review_note differs "
                f"({r1.review_note!r} vs {r2.review_note!r})"
            )

    def test_cache_hit_reproducibility(self, tmp_path: Path) -> None:
        """Second run on same cache dir hits cache and gets same review_note."""
        from examen.verify.review_agent import review_items

        items = [_make_item(1)]  # odd → finding
        backend = FakeReviewBackend()
        shared_cache = InputHashCache(backend=backend, cache_dir=tmp_path / "shared_cache")

        result1 = review_items(items, backend=backend, cache=shared_cache)
        # Second call — backend is same; cache may be hit
        result2 = review_items(items, backend=backend, cache=shared_cache)

        assert result1[0].review_note == result2[0].review_note, (
            "review_note changed between cached runs"
        )

    def test_third_run_stable(self, tmp_path: Path) -> None:
        """Three consecutive runs all produce the same review_note values."""
        from examen.verify.review_agent import review_items

        items = [_make_item(i) for i in range(1, 4)]
        backend = FakeReviewBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        run1 = review_items(items, backend=backend, cache=cache)
        run2 = review_items(items, backend=backend, cache=cache)
        run3 = review_items(items, backend=backend, cache=cache)

        for r1, r2, r3 in zip(run1, run2, run3, strict=True):
            assert r1.review_note == r2.review_note == r3.review_note, (
                f"item_no={r1.item_no}: review_note unstable across 3 runs"
            )


class TestReviewAgentWithBuildPipeline:
    """Integration: review_items correctly processes items from build_exam output."""

    def test_build_items_all_start_with_empty_review_note(self, tmp_path: Path) -> None:
        """Items from build_exam have review_note='' before adversarial review.

        Note: format_checks may add notes to review_note during build — this test
        checks that review_agent-specific findings (tagged [review_agent]) are absent
        at build time.
        """
        from examen.generate.backend import GenerationResponse
        from examen.pipeline import build_exam
        from paideia_shared.schemas import (
            CurriculumEntry,
            CurriculumMap,
            ExamenBlueprint,
        )

        chapters_local = [
            "8장 호흡계통",
            "9장 근육계통",
            "10장 소화계통",
            "11장 순환계통",
            "12장 비뇨계통",
            "13장 신경계통",
        ]
        chapter_nos_local = [8, 9, 10, 11, 12, 13]
        weeks_local = [8, 9, 10, 11, 12, 13]
        total_local = 40  # minimum valid for ExamenBlueprint

        class MinimalFakeBackend(LLMBackend):
            def generate(self, request: GenerationRequest) -> GenerationResponse:
                canned = {
                    "question_type": "지식축적",
                    "difficulty": "2_보통",
                    "stem_polarity": "부정형",
                    "text": "다음 중 가장 옳지 않은 것은?",
                    "options": [
                        "① " + "가" * 28,
                        "② " + "나" * 28,
                        "③ " + "다" * 28,
                        "④ " + "라" * 28,
                        "⑤ " + "마" * 28,
                    ],
                    "answer_no": 1,
                    "distractor_rationale": [
                        "틀린 진술: 가." if j == 0 else "옳은 진술."
                        for j in range(5)
                    ],
                    "wrong_explanation": "오답 설명." * 20,
                    "leap_explanation": "도약 설명." * 20,
                    "intent": "기본 구조와 기능을 확인한다.",
                    "key_concept": None,
                    "wrong_option_no": 1,
                }
                return GenerationResponse(
                    slot_id=request.slot_id,
                    raw_text=json.dumps(canned, ensure_ascii=False),
                    model="fake-minimal",
                    cache_hit=False,
                )

        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="테스트 기말고사",
            total_items=total_local,
            chapters=chapters_local,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": total_local, "formative": 0, "quiz": 0},
        )
        curriculum_map = CurriculumMap(
            semester=_SEMESTER,
            course_slug=_COURSE,
            entries=[
                CurriculumEntry(
                    week=w,
                    chapter=ch,
                    chapter_no=cn,
                    subtopic=None,
                    sections=["1. 기본구조"],
                )
                for w, ch, cn in zip(weeks_local, chapters_local, chapter_nos_local, strict=False)
            ],
        )
        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        bronze_dir.mkdir(parents=True, exist_ok=True)
        for cn, ch in zip(chapter_nos_local, chapters_local, strict=False):
            fname = f"{cn}장 {ch.split(' ', 1)[1]}.txt"
            (bronze_dir / fname).write_text(
                f"{cn}장 {ch}\n내용\n기능\n", encoding="utf-8"
            )

        items, _ = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=MinimalFakeBackend(),
        )

        # review_agent findings are tagged [review_agent]; build_exam shouldn't add them
        for item in items:
            assert "[review_agent]" not in (item.review_note or ""), (
                f"item_no={item.item_no}: [review_agent] tag found in review_note "
                f"before adversarial review pass. review_note={item.review_note!r}"
            )
