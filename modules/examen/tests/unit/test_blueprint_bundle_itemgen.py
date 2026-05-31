"""Unit tests for T024 blueprint solver, T025 bundle, T026 item_gen.

TDD: failing tests written BEFORE implementation.

Covers:
- T024 solve(): chapter-even slot allocation, difficulty distribution within
  tolerance, source counts == source_mix, determinism.
- T025 build_bundle(): byte-identical for same input, contains chunk text,
  교과서-only instruction, correct GenerationRequest shape.
- T026 generate_item(): FakeBackend yields schema-valid ExamItemDraft
  (source=textbook, 5 options, evidence anchored), non-textbook raises
  NotImplementedError, cache re-run is byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
)
from examen.silver.evidence_index import EvidenceIndex
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    ExamenBlueprint,
    ExamItemDraft,
    TextbookChunk,
)

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

def _make_blueprint(
    *,
    total_items: int = 40,
    chapters: list[str] | None = None,
    source_mix: dict[str, int] | None = None,
    difficulty_targets: dict[str, float] | None = None,
) -> ExamenBlueprint:
    """Build a minimal valid ExamenBlueprint for testing."""
    if chapters is None:
        chapters = [
            "8장 호흡계통",
            "9장 근육계통",
            "10장 내분비계통",
            "11장 순환계통",
            "12장 소화계통",
            "13장 신경계통",
        ]
    if source_mix is None:
        # textbook-only for US1 tests
        source_mix = {"textbook": total_items, "formative": 0, "quiz": 0}
    if difficulty_targets is None:
        difficulty_targets = {"easy": 0.45, "medium": 0.35, "hard": 0.20}
    return ExamenBlueprint(
        semester="2026-1",
        course_slug="anatomy",
        exam_name="2026-1학기 기말고사",
        total_items=total_items,
        chapters=chapters,
        difficulty_targets=difficulty_targets,
        source_mix=source_mix,
    )


def _make_curriculum_map(
    chapters: list[str] | None = None,
) -> CurriculumMap:
    """Build a CurriculumMap matching the default blueprint chapters."""
    if chapters is None:
        chapters = [
            "8장 호흡계통",
            "9장 근육계통",
            "10장 내분비계통",
            "11장 순환계통",
            "12장 소화계통",
            "13장 신경계통",
        ]
    entries = []
    for i, ch in enumerate(chapters):
        ch_no = i + 8
        entries.append(
            CurriculumEntry(
                week=i + 1,
                chapter=ch,
                chapter_no=ch_no,
                subtopic=None,
                sections=["1. 절일", "2. 절이"],
            )
        )
    return CurriculumMap(
        semester="2026-1",
        course_slug="anatomy",
        entries=entries,
    )


def _make_chunks(
    chapter_no: int = 10,
    chapter: str = "10장 내분비계통",
    n: int = 2,
) -> list[TextbookChunk]:
    """Build stub TextbookChunk list for a given chapter."""
    chunks = []
    for i in range(n):
        # Fabricate a unique chunk_id deterministically
        chunk_id = f"fakeid{chapter_no:02d}{i:02d}"
        chunks.append(
            TextbookChunk(
                semester="2026-1",
                course_slug="anatomy",
                chunk_id=chunk_id,
                chapter_no=chapter_no,
                chapter=chapter,
                section=f"{i + 1}. 절{i + 1}",
                source_file=f"{chapter_no}장.txt",
                line_start=1 + i * 20,
                line_end=20 + i * 20,
                text=f"Chapter {chapter_no} section {i + 1} 내용입니다. "
                     f"호르몬이 조절한다. 뇌하수체에서 분비된다.",
                removed_spans=[],
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# FakeBackend: returns a canned structured JSON matching ExamItemDraft shape
# ---------------------------------------------------------------------------

_CANNED_ITEM_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "1_쉬움",
    "stem_polarity": "부정형",
    "text": "다음 중 뇌하수체에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① 뇌하수체는 터키안장에 위치한다.",
        "② 전엽과 후엽으로 구성된다.",
        "③ 뇌하수체 전엽에서는 GH가 분비된다.",
        "④ 후엽은 신경 조직으로 이루어진다.",
        "⑤ 뇌하수체는 복막 안에 위치한다.",
    ],
    "answer_no": 5,
    "distractor_rationale": [
        "옳은 진술: 뇌하수체는 터키안장에 위치한다.",
        "옳은 진술: 전엽과 후엽으로 구성된다.",
        "옳은 진술: GH가 전엽에서 분비된다.",
        "옳은 진술: 후엽은 신경성이다.",
        "틀린 진술: 뇌하수체는 두개골 안에 있다.",
    ],
    "wrong_explanation": (
        "뇌하수체는 간뇌 아래의 터키안장(접형골의 오목)에 위치하며, "
        "복막과는 전혀 무관하다. 복막은 복강 장기를 둘러싸는 장막으로, "
        "뇌하수체가 위치하는 두개강과는 다른 체강에 속한다. "
        "이 문항에서 틀린 진술을 고르지 못하는 경우 뇌하수체의 해부학적 위치에 "
        "대한 기본 개념이 부족한 것이다. 교재 10장 내분비계통 절을 재검토하라."
    ),
    "leap_explanation": (
        "정답을 맞혔다면 뇌하수체의 해부학적 위치를 정확히 알고 있는 것이다. "
        "나아가 뇌하수체 전엽(샘성 뇌하수체)과 후엽(신경성 뇌하수체)의 구분, "
        "각각에서 분비되는 호르몬(전엽: GH, TSH, ACTH, FSH, LH, PRL; "
        "후엽: ADH, 옥시토신)까지 정리해 두면 관련 문항에서 강점을 가질 수 있다."
    ),
    "intent": "뇌하수체의 해부학적 위치를 정확히 알고 있는지 확인한다.",
    "key_concept": "뇌하수체",
}


class FakeBackend(LLMBackend):
    """Returns a canned structured JSON for textbook items; counts calls."""

    def __init__(self, raw_json: dict[str, Any] | None = None) -> None:
        self._raw = raw_json if raw_json is not None else _CANNED_ITEM_JSON
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return canned JSON, incrementing call_count."""
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=json.dumps(self._raw, ensure_ascii=False),
            model="fake-model",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# T024: blueprint solver
# ---------------------------------------------------------------------------


class TestBlueprintSolver:
    """Tests for examen.plan.blueprint.solve()."""

    def _solve(
        self,
        blueprint: ExamenBlueprint | None = None,
        curriculum_map: CurriculumMap | None = None,
    ):  # type: ignore[return]
        from examen.plan.blueprint import solve

        if blueprint is None:
            blueprint = _make_blueprint()
        if curriculum_map is None:
            curriculum_map = _make_curriculum_map()
        return solve(blueprint, curriculum_map)

    # --- Basic shape tests ---

    def test_returns_list_of_slots(self) -> None:
        """solve() returns a non-empty list of Slot objects."""
        slots = self._solve()
        assert len(slots) > 0

    def test_total_slot_count_equals_total_items(self) -> None:
        """Number of slots == blueprint.total_items."""
        bp = _make_blueprint(total_items=40)
        slots = self._solve(blueprint=bp)
        assert len(slots) == 40

    def test_total_slot_count_for_50_items(self) -> None:
        """Works for total_items=50 as well."""
        bp = _make_blueprint(total_items=50)
        slots = self._solve(blueprint=bp)
        assert len(slots) == 50

    # --- Chapter-even allocation ---

    def test_chapter_counts_max_diff_one(self) -> None:
        """Each chapter's slot count differs from others by at most 1."""
        from collections import Counter
        bp = _make_blueprint(total_items=40)  # 6 chapters → 6 or 7 each
        slots = self._solve(blueprint=bp)
        counts = Counter(s.chapter for s in slots)
        max_c = max(counts.values())
        min_c = min(counts.values())
        assert max_c - min_c <= 1, (
            f"Chapter allocation not chapter-even: {dict(counts)}"
        )

    def test_chapter_counts_for_45_items(self) -> None:
        """45 items / 6 chapters → (7,7,7,8,8,8) or similar max-diff-1."""
        from collections import Counter
        bp = _make_blueprint(total_items=45)
        slots = self._solve(blueprint=bp)
        counts = Counter(s.chapter for s in slots)
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_all_blueprint_chapters_represented(self) -> None:
        """Every chapter in blueprint.chapters has at least one slot."""
        bp = _make_blueprint()
        slots = self._solve(blueprint=bp)
        chapter_set = {s.chapter for s in slots}
        for ch in bp.chapters:
            assert ch in chapter_set, f"Chapter '{ch}' has no slots"

    # --- Source counts ---

    def test_source_counts_match_source_mix_textbook_only(self) -> None:
        """Textbook-only blueprint: all slots have source='textbook'."""
        from collections import Counter
        bp = _make_blueprint(source_mix={"textbook": 40, "formative": 0, "quiz": 0})
        slots = self._solve(blueprint=bp)
        counts = Counter(s.source for s in slots)
        assert counts["textbook"] == 40
        assert counts.get("formative", 0) == 0
        assert counts.get("quiz", 0) == 0

    def test_source_counts_mixed(self) -> None:
        """Mixed source_mix: source counts match blueprint."""
        from collections import Counter
        bp = _make_blueprint(
            total_items=40,
            source_mix={"textbook": 20, "formative": 12, "quiz": 8},
        )
        slots = self._solve(blueprint=bp)
        counts = Counter(s.source for s in slots)
        assert counts["textbook"] == 20
        assert counts["formative"] == 12
        assert counts["quiz"] == 8

    # --- Difficulty distribution ---

    def test_difficulty_labels_cover_all_targets(self) -> None:
        """Slots have difficulty labels; no unknown values."""
        bp = _make_blueprint(total_items=40)
        slots = self._solve(blueprint=bp)
        valid = {"1_쉬움", "2_보통", "3_어려움"}
        for s in slots:
            assert s.difficulty in valid, f"unexpected difficulty: {s.difficulty}"

    def test_difficulty_distribution_within_tolerance(self) -> None:
        """easy/medium/hard slot fractions within ±0.10 of blueprint targets."""
        from collections import Counter
        bp = _make_blueprint(
            total_items=40,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        )
        slots = self._solve(blueprint=bp)
        n = len(slots)
        counts = Counter(s.difficulty for s in slots)
        easy_frac = counts.get("1_쉬움", 0) / n
        med_frac = counts.get("2_보통", 0) / n
        hard_frac = counts.get("3_어려움", 0) / n
        assert abs(easy_frac - 0.45) <= 0.10, f"easy fraction {easy_frac:.2f} out of tolerance"
        assert abs(med_frac - 0.35) <= 0.10, f"medium fraction {med_frac:.2f} out of tolerance"
        assert abs(hard_frac - 0.20) <= 0.10, f"hard fraction {hard_frac:.2f} out of tolerance"

    # --- Slot shape ---

    def test_slot_has_required_fields(self) -> None:
        """Each Slot has slot_id, chapter, chapter_no, source, difficulty."""
        slots = self._solve()
        for s in slots:
            assert hasattr(s, "slot_id"), "missing slot_id"
            assert hasattr(s, "chapter"), "missing chapter"
            assert hasattr(s, "chapter_no"), "missing chapter_no"
            assert hasattr(s, "source"), "missing source"
            assert hasattr(s, "difficulty"), "missing difficulty"

    def test_slot_ids_are_unique(self) -> None:
        """All slot_ids are unique."""
        slots = self._solve()
        ids = [s.slot_id for s in slots]
        assert len(ids) == len(set(ids)), "duplicate slot_ids"

    def test_slot_chapter_no_matches_curriculum_map(self) -> None:
        """Each slot's chapter_no is consistent with the curriculum_map."""
        cm = _make_curriculum_map()
        ch_to_no = {e.chapter: e.chapter_no for e in cm.entries}
        slots = self._solve(curriculum_map=cm)
        for s in slots:
            if s.chapter in ch_to_no:
                assert s.chapter_no == ch_to_no[s.chapter], (
                    f"chapter_no mismatch for {s.chapter}: "
                    f"got {s.chapter_no}, expected {ch_to_no[s.chapter]}"
                )

    # --- Determinism ---

    def test_solve_is_deterministic(self) -> None:
        """Same inputs → identical slot list (same order, same values)."""
        from examen.plan.blueprint import solve
        bp = _make_blueprint()
        cm = _make_curriculum_map()
        slots_a = solve(bp, cm)
        slots_b = solve(bp, cm)
        assert len(slots_a) == len(slots_b)
        for a, b in zip(slots_a, slots_b, strict=True):
            assert a.slot_id == b.slot_id
            assert a.chapter == b.chapter
            assert a.source == b.source
            assert a.difficulty == b.difficulty


# ---------------------------------------------------------------------------
# T025: bundle builder
# ---------------------------------------------------------------------------


class TestBuildBundle:
    """Tests for examen.generate.bundle.build_bundle()."""

    def _make_slot(
        self,
        slot_id: str = "slot-001",
        chapter: str = "10장 내분비계통",
        chapter_no: int = 10,
        source: str = "textbook",
        difficulty: str = "1_쉬움",
    ):  # type: ignore[return]
        from examen.plan.blueprint import Slot
        return Slot(
            slot_id=slot_id,
            chapter=chapter,
            chapter_no=chapter_no,
            source=source,
            difficulty=difficulty,
            section=None,
        )

    def _build(self, slot=None, chunks=None):  # type: ignore[return]
        from examen.generate.bundle import build_bundle
        if slot is None:
            slot = self._make_slot()
        if chunks is None:
            chunks = _make_chunks(chapter_no=10)
        return build_bundle(slot, chunks)

    # --- Basic shape ---

    def test_returns_generation_request(self) -> None:
        """build_bundle returns a GenerationRequest."""
        req = self._build()
        assert isinstance(req, GenerationRequest)

    def test_slot_id_preserved(self) -> None:
        """GenerationRequest.slot_id matches the slot's slot_id."""
        slot = self._make_slot(slot_id="slot-xyz")
        req = self._build(slot=slot)
        assert req.slot_id == "slot-xyz"

    def test_prompt_contains_chunk_text(self) -> None:
        """Prompt contains the chunk text (교재 근거)."""
        chunks = _make_chunks(chapter_no=10)
        req = self._build(chunks=chunks)
        # At least one chunk's text must appear in the prompt
        found = any(c.text[:20] in req.prompt for c in chunks)
        assert found, "no chunk text found in prompt"

    def test_prompt_contains_textbook_only_instruction(self) -> None:
        """Prompt explicitly instructs to use only provided textbook text."""
        req = self._build()
        # Must contain Korean instruction about 교과서 exclusivity
        prompt_lower = req.prompt
        assert "교과서" in prompt_lower or "교재" in prompt_lower, (
            "prompt must mention 교과서/교재 exclusivity"
        )
        # Also must instruct not to use outside knowledge
        outside_cues = ["외부", "outside", "only", "제공된"]
        assert any(cue in prompt_lower for cue in outside_cues), (
            f"prompt must instruct textbook-only: {req.prompt[:200]}"
        )

    def test_prompt_contains_5_option_instruction(self) -> None:
        """Prompt instructs 5-option single-answer format."""
        req = self._build()
        assert "5" in req.prompt or "다섯" in req.prompt, (
            "prompt must specify 5 options"
        )

    def test_prompt_contains_negative_polarity_instruction(self) -> None:
        """Prompt specifies 부정형 stem ('가장 옳지 않은 것')."""
        req = self._build()
        assert "부정형" in req.prompt or "옳지 않은" in req.prompt, (
            "prompt must specify 부정형 발문"
        )

    def test_context_refs_contain_chunk_ids(self) -> None:
        """context_refs includes references from the slot's chapter chunks."""
        chunks = _make_chunks(chapter_no=10)
        req = self._build(chunks=chunks)
        # context_refs should mention chunk_ids or source_file
        assert len(req.context_refs) > 0, "context_refs must not be empty"

    def test_metadata_contains_chapter_info(self) -> None:
        """metadata includes chapter, chapter_no, difficulty, source."""
        slot = self._make_slot(chapter_no=10, difficulty="2_보통")
        req = self._build(slot=slot)
        assert "chapter_no" in req.metadata or "chapter" in req.metadata
        assert "difficulty" in req.metadata

    # --- Determinism ---

    def test_build_bundle_deterministic_same_input(self) -> None:
        """build_bundle called twice with identical input produces identical output."""
        from examen.generate.bundle import build_bundle
        from examen.plan.blueprint import Slot
        slot = Slot(slot_id="s1", chapter="10장", chapter_no=10,
                    source="textbook", difficulty="1_쉬움", section=None)
        chunks = _make_chunks(chapter_no=10)
        req_a = build_bundle(slot, chunks)
        req_b = build_bundle(slot, chunks)
        assert req_a.prompt == req_b.prompt
        assert req_a.context_refs == req_b.context_refs
        assert req_a.metadata == req_b.metadata

    def test_different_slots_produce_different_prompts(self) -> None:
        """Different slot_ids produce different GenerationRequests."""
        from examen.generate.bundle import build_bundle
        from examen.plan.blueprint import Slot
        s1 = Slot(slot_id="s1", chapter="10장", chapter_no=10,
                  source="textbook", difficulty="1_쉬움", section=None)
        s2 = Slot(slot_id="s2", chapter="10장", chapter_no=10,
                  source="textbook", difficulty="3_어려움", section=None)
        chunks = _make_chunks(chapter_no=10)
        r1 = build_bundle(s1, chunks)
        r2 = build_bundle(s2, chunks)
        # slot_id differs
        assert r1.slot_id != r2.slot_id
        # The differing difficulty must change the prompt text itself
        assert r1.prompt != r2.prompt

    def test_filters_chunks_to_correct_chapter(self) -> None:
        """Only chunks matching the slot's chapter_no are included."""
        from examen.generate.bundle import build_bundle
        from examen.plan.blueprint import Slot
        # Mix chunks from chapters 10 and 11
        chunks_10 = _make_chunks(chapter_no=10, chapter="10장 내분비계통")
        chunks_11 = _make_chunks(chapter_no=11, chapter="11장 순환계통")
        all_chunks = chunks_10 + chunks_11
        slot = Slot(slot_id="s1", chapter="10장 내분비계통", chapter_no=10,
                    source="textbook", difficulty="1_쉬움", section=None)
        req = build_bundle(slot, all_chunks)
        # Chapter 11 text should NOT appear in the prompt
        for c in chunks_11:
            assert c.text[:30] not in req.prompt, "ch11 text leaked into ch10 bundle"


# ---------------------------------------------------------------------------
# T026: item generator
# ---------------------------------------------------------------------------


class TestGenerateItem:
    """Tests for examen.generate.item_gen.generate_item()."""

    def _make_slot(
        self,
        slot_id: str = "slot-001",
        source: str = "textbook",
        chapter_no: int = 10,
        chapter: str = "10장 내분비계통",
        difficulty: str = "1_쉬움",
    ):  # type: ignore[return]
        from examen.plan.blueprint import Slot
        return Slot(
            slot_id=slot_id,
            chapter=chapter,
            chapter_no=chapter_no,
            source=source,
            difficulty=difficulty,
            section=None,
        )

    def _make_evidence_index(self) -> EvidenceIndex:
        lines = [
            "뇌하수체는 터키안장에 위치한다.",
            "뇌하수체 전엽과 후엽으로 구성된다.",
            "갑상샘은 목 앞쪽에 위치한다.",
        ]
        return EvidenceIndex.build(lines, source_file="10장.txt")

    def _generate(
        self,
        slot=None,
        chunks=None,
        evidence_index=None,
        backend=None,
        cache_dir: Path | None = None,
        tmp_path: Path | None = None,
    ) -> ExamItemDraft:
        from examen.generate.item_gen import generate_item
        if slot is None:
            slot = self._make_slot()
        if chunks is None:
            chunks = _make_chunks(chapter_no=10)
        if evidence_index is None:
            evidence_index = self._make_evidence_index()
        if backend is None:
            backend = FakeBackend()
        if cache_dir is None and tmp_path is not None:
            cache_dir = tmp_path / "cache"
        elif cache_dir is None:
            import tempfile
            td = tempfile.mkdtemp()
            cache_dir = Path(td)
        cache = InputHashCache(backend=backend, cache_dir=cache_dir)
        return generate_item(
            slot=slot,
            chunks=chunks,
            evidence_index=evidence_index,
            backend=backend,
            cache=cache,
        )

    # --- Basic schema validity ---

    def test_returns_exam_item_draft(self, tmp_path: Path) -> None:
        """generate_item returns an ExamItemDraft instance."""
        item = self._generate(tmp_path=tmp_path)
        assert isinstance(item, ExamItemDraft)

    def test_source_is_textbook(self, tmp_path: Path) -> None:
        """Source field is 'textbook' for a textbook slot."""
        item = self._generate(tmp_path=tmp_path)
        assert item.source == "textbook"

    def test_has_five_options(self, tmp_path: Path) -> None:
        """ExamItemDraft has exactly 5 options."""
        item = self._generate(tmp_path=tmp_path)
        assert len(item.options) == 5

    def test_answer_no_in_range(self, tmp_path: Path) -> None:
        """answer_no is between 1 and 5 inclusive."""
        item = self._generate(tmp_path=tmp_path)
        assert 1 <= item.answer_no <= 5

    def test_has_five_distractor_rationales(self, tmp_path: Path) -> None:
        """distractor_rationale has exactly 5 entries."""
        item = self._generate(tmp_path=tmp_path)
        assert len(item.distractor_rationale) == 5

    def test_chapter_and_chapter_no_from_slot(self, tmp_path: Path) -> None:
        """chapter and chapter_no are taken from the slot."""
        slot = self._make_slot(chapter="10장 내분비계통", chapter_no=10)
        item = self._generate(slot=slot, tmp_path=tmp_path)
        assert item.chapter == "10장 내분비계통"
        assert item.chapter_no == 10

    def test_difficulty_from_slot(self, tmp_path: Path) -> None:
        """difficulty is set from the slot, not just from LLM response."""
        slot = self._make_slot(difficulty="3_어려움")
        item = self._generate(slot=slot, tmp_path=tmp_path)
        assert item.difficulty == "3_어려움"

    def test_semester_and_course_slug_present(self, tmp_path: Path) -> None:
        """semester and course_slug are correctly populated."""
        item = self._generate(tmp_path=tmp_path)
        assert item.semester == "2026-1"
        assert item.course_slug == "anatomy"

    def test_item_no_is_positive(self, tmp_path: Path) -> None:
        """item_no is a positive integer."""
        item = self._generate(tmp_path=tmp_path)
        assert item.item_no >= 1

    # --- Evidence anchoring ---

    def test_textbook_evidence_present_for_textbook_source(self, tmp_path: Path) -> None:
        """textbook_evidence is populated (not None) for source=textbook."""
        item = self._generate(tmp_path=tmp_path)
        assert item.textbook_evidence is not None

    def test_evidence_status_is_found_when_concept_in_index(self, tmp_path: Path) -> None:
        """Evidence status is '확인' when key_concept is found in evidence_index."""
        # The canned item has key_concept='뇌하수체' which IS in the evidence index.
        item = self._generate(tmp_path=tmp_path)
        assert item.textbook_evidence is not None
        assert item.textbook_evidence.status == "확인"

    def test_evidence_status_not_found_when_concept_absent(self, tmp_path: Path) -> None:
        """Evidence status is '미확인' when key_concept is absent from evidence."""
        # Override canned item to use a term that is NOT in the evidence index
        custom_item = dict(_CANNED_ITEM_JSON)
        custom_item["key_concept"] = "존재하지않는단어XYZ"
        backend = FakeBackend(raw_json=custom_item)
        evidence_index = self._make_evidence_index()
        slot = self._make_slot()
        chunks = _make_chunks(chapter_no=10)
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_miss")
        from examen.generate.item_gen import generate_item
        item = generate_item(
            slot=slot,
            chunks=chunks,
            evidence_index=evidence_index,
            backend=backend,
            cache=cache,
        )
        assert item.textbook_evidence is not None
        assert item.textbook_evidence.status == "미확인"

    def test_evidence_source_file_is_set(self, tmp_path: Path) -> None:
        """TextbookEvidence.source_file is set to the evidence index source."""
        item = self._generate(tmp_path=tmp_path)
        assert item.textbook_evidence is not None
        assert item.textbook_evidence.source_file  # non-empty

    # --- Non-textbook raises NotImplementedError ---

    def test_formative_source_raises_not_implemented(self, tmp_path: Path) -> None:
        """generate_item raises NotImplementedError for source='formative'."""
        from examen.generate.item_gen import generate_item
        slot = self._make_slot(source="formative")
        chunks = _make_chunks(chapter_no=10)
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_f")
        with pytest.raises(NotImplementedError, match="US2"):
            generate_item(
                slot=slot,
                chunks=chunks,
                evidence_index=self._make_evidence_index(),
                backend=backend,
                cache=cache,
            )

    def test_quiz_source_raises_not_implemented(self, tmp_path: Path) -> None:
        """generate_item raises NotImplementedError for source='quiz'."""
        from examen.generate.item_gen import generate_item
        slot = self._make_slot(source="quiz")
        chunks = _make_chunks(chapter_no=10)
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_q")
        with pytest.raises(NotImplementedError, match="US3"):
            generate_item(
                slot=slot,
                chunks=chunks,
                evidence_index=self._make_evidence_index(),
                backend=backend,
                cache=cache,
            )

    # --- Empty / mismatched chunk guard (fail loud, never silently wrong) ---

    def test_empty_chunks_raises_located_value_error(self, tmp_path: Path) -> None:
        """An empty chunk list raises a ValueError naming the slot, no backend call."""
        from examen.generate.item_gen import generate_item
        slot = self._make_slot(slot_id="slot-007", chapter_no=10)
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_empty")
        with pytest.raises(ValueError, match="slot-007"):
            generate_item(
                slot=slot,
                chunks=[],
                evidence_index=self._make_evidence_index(),
                backend=backend,
                cache=cache,
            )
        # Guard must fire BEFORE the backend is called (no hallucinated context).
        assert backend.call_count == 0

    def test_no_matching_chapter_chunks_raises(self, tmp_path: Path) -> None:
        """Chunks present but none matching the slot's chapter → ValueError."""
        from examen.generate.item_gen import generate_item
        slot = self._make_slot(slot_id="slot-009", chapter_no=10)
        # Provide chunks for chapter 11 only — none match chapter 10.
        chunks = _make_chunks(chapter_no=11, chapter="11장 순환계통")
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_nomatch")
        with pytest.raises(ValueError, match="chapter_no=10"):
            generate_item(
                slot=slot,
                chunks=chunks,
                evidence_index=self._make_evidence_index(),
                backend=backend,
                cache=cache,
            )
        assert backend.call_count == 0

    # --- Malformed LLM response (fail loud) ---

    def test_null_answer_no_raises_located_value_error(self, tmp_path: Path) -> None:
        """LLM returning answer_no=null raises a located ValueError, not TypeError."""
        from examen.generate.item_gen import generate_item
        custom_item = dict(_CANNED_ITEM_JSON)
        custom_item["answer_no"] = None
        backend = FakeBackend(raw_json=custom_item)
        slot = self._make_slot(slot_id="slot-011")
        chunks = _make_chunks(chapter_no=10)
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_null")
        with pytest.raises(ValueError, match="slot-011"):
            generate_item(
                slot=slot,
                chunks=chunks,
                evidence_index=self._make_evidence_index(),
                backend=backend,
                cache=cache,
            )

    # --- Cache determinism ---

    def test_cache_rerun_produces_byte_identical_item(self, tmp_path: Path) -> None:
        """Two calls with identical input return identical ExamItemDraft."""
        from examen.generate.item_gen import generate_item
        slot = self._make_slot(slot_id="s-det")
        chunks = _make_chunks(chapter_no=10)
        evidence_index = self._make_evidence_index()
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_det")
        item1 = generate_item(
            slot=slot, chunks=chunks,
            evidence_index=evidence_index, backend=backend, cache=cache,
        )
        item2 = generate_item(
            slot=slot, chunks=chunks,
            evidence_index=evidence_index, backend=backend, cache=cache,
        )
        # Serialise to dict for field-by-field comparison
        assert item1.model_dump() == item2.model_dump()
        # Backend called once (second call is cache hit)
        assert backend.call_count == 1

    def test_second_call_is_cache_hit(self, tmp_path: Path) -> None:
        """Re-running with same input: backend called only once (cache hit)."""
        from examen.generate.item_gen import generate_item
        slot = self._make_slot(slot_id="s-hit")
        chunks = _make_chunks(chapter_no=10)
        evidence_index = self._make_evidence_index()
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache_hit")
        generate_item(
            slot=slot, chunks=chunks,
            evidence_index=evidence_index, backend=backend, cache=cache,
        )
        generate_item(
            slot=slot, chunks=chunks,
            evidence_index=evidence_index, backend=backend, cache=cache,
        )
        assert backend.call_count == 1, (
            f"Backend called {backend.call_count} times; expected 1 (cache should hit)"
        )

    # --- Defaults for quality flags ---

    def test_adoption_status_default_generated(self, tmp_path: Path) -> None:
        """adoption_status defaults to '생성'."""
        item = self._generate(tmp_path=tmp_path)
        assert item.adoption_status == "생성"

    def test_duplicate_flag_default_false(self, tmp_path: Path) -> None:
        """duplicate_flag defaults to False."""
        item = self._generate(tmp_path=tmp_path)
        assert item.duplicate_flag is False
