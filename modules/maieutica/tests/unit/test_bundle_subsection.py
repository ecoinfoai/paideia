"""T011 (RED) — subsection-scoped bundle context, key_concept, avoid_list.

Verifies the diversity fix (research R6/R7): an ASSIGNED quiz slot draws its
prompt context from ONLY its assigned subsection, its ``key_concept`` is
derived from that subsection (NOT the chapter name), and an injected
``avoid_list`` of prior subsection points is rendered into the prompt. The
UNASSIGNED (dry-run) slot falls back to whole-chapter context with
``key_concept == spec.chapter`` so the degrade path (FR-012) stays intact.
"""

from __future__ import annotations

from maieutica.plan.slots import Slot, assign_subsections, plan_slots
from paideia_shared.schemas import MaieuticaGenerationSpec, TextbookChunk


def _make_spec(
    *,
    week: int = 9,
    chapter_no: int = 8,
    chapter: str = "8장 호흡계통",
    quiz_count: int = 6,
    formative_count: int = 1,
) -> MaieuticaGenerationSpec:
    """Build a minimal valid MaieuticaGenerationSpec for testing."""
    return MaieuticaGenerationSpec(
        semester="2026-1",
        course_slug="anatomy",
        week=week,
        chapter_no=chapter_no,
        chapter=chapter,
        quiz_count=quiz_count,
        formative_count=formative_count,
    )


def _make_chunks() -> list[TextbookChunk]:
    """Two subsections with DISTINGUISHABLE bodies for the same chapter.

    Subsection A talks about 코 (nose); subsection B talks about 허파꽈리
    (alveoli). Each carries a unique sentinel phrase so a test can assert
    which subsection's text reached the prompt.
    """
    return [
        TextbookChunk(
            semester="2026-1",
            course_slug="anatomy",
            chunk_id="chunk0800",
            chapter_no=8,
            chapter="8장 호흡계통",
            section="1) 코",
            source_file="8장.txt",
            line_start=1,
            line_end=20,
            text="코는 공기를 데우고 거른다. SENTINEL_NOSE 외비강과 비강을 다룬다.",
            removed_spans=[],
        ),
        TextbookChunk(
            semester="2026-1",
            course_slug="anatomy",
            chunk_id="chunk0801",
            chapter_no=8,
            chapter="8장 호흡계통",
            section="2) 허파꽈리",
            source_file="8장.txt",
            line_start=21,
            line_end=40,
            text="허파꽈리에서 가스교환이 일어난다. SENTINEL_ALVEOLI 산소가 확산된다.",
            removed_spans=[],
        ),
    ]


def _assigned_slot_for_chunk(
    spec: MaieuticaGenerationSpec,
    chunks: list[TextbookChunk],
    chunk_id: str,
) -> Slot:
    """Return the first assigned slot bound to ``chunk_id``."""
    enriched = assign_subsections(plan_slots(spec), chunks)
    return next(s for s in enriched if s.subsection_chunk_id == chunk_id)


class TestSubsectionScopedContext:
    """ASSIGNED slot → only its subsection text reaches the prompt."""

    def test_assigned_slot_uses_only_its_subsection(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0800")

        req = build_bundle(slot, spec, chunks)

        assert "SENTINEL_NOSE" in req.prompt
        assert "SENTINEL_ALVEOLI" not in req.prompt
        assert req.context_refs == ["8장.txt#chunk0800"]

    def test_assigned_key_concept_is_subsection_not_chapter(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0800")

        req = build_bundle(slot, spec, chunks)

        assert req.metadata["key_concept"] != spec.chapter
        # The numbering marker "1) " is stripped to the bare concept term.
        assert req.metadata["key_concept"] == "코"

    def test_metadata_has_subsection_fields(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0801")

        req = build_bundle(slot, spec, chunks)

        assert req.metadata["subsection_chunk_id"] == "chunk0801"
        assert req.metadata["intra_ordinal"] == slot.intra_ordinal


class TestAvoidListInjection:
    """avoid_list is rendered into the prompt + recorded in metadata."""

    def test_avoid_list_rendered_and_in_metadata(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0801")

        req = build_bundle(slot, spec, chunks, avoid_list=["폐포의 가스교환 기능"])

        assert "폐포의 가스교환 기능" in req.prompt
        assert req.metadata["avoid_list"] == ["폐포의 가스교환 기능"]

    def test_empty_avoid_list_renders_neutral(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0800")

        req = build_bundle(slot, spec, chunks)

        assert "(없음)" in req.prompt
        assert req.metadata["avoid_list"] == []

    def test_avoid_list_order_preserved(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0800")

        avoid = ["둘째 포인트", "첫째 포인트"]
        req = build_bundle(slot, spec, chunks, avoid_list=avoid)

        assert req.metadata["avoid_list"] == avoid
        # Rendered in given order (NOT sorted).
        assert req.prompt.index("둘째 포인트") < req.prompt.index("첫째 포인트")


class TestUnassignedFallback:
    """UNASSIGNED slot (dry-run) → whole-chapter context + chapter key_concept."""

    def test_unassigned_slot_uses_all_chapter_chunks(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        # plan_slots leaves subsection_chunk_id == "" (UNASSIGNED).
        slot = next(s for s in plan_slots(spec) if s.kind == "quiz")
        assert slot.subsection_chunk_id == ""

        req = build_bundle(slot, spec, chunks)

        assert "SENTINEL_NOSE" in req.prompt
        assert "SENTINEL_ALVEOLI" in req.prompt
        assert req.metadata["key_concept"] == spec.chapter

    def test_unassigned_when_chunk_id_absent_from_chunks(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        # subsection_chunk_id set but not present in chunks → fallback.
        slot = Slot(
            slot_id="quiz-9-001",
            kind="quiz",
            week=9,
            chapter_no=8,
            ordinal=1,
            subsection_chunk_id="chunk-missing",
            subsection_section="1) 코",
            intra_ordinal=1,
        )

        req = build_bundle(slot, spec, chunks)

        assert "SENTINEL_NOSE" in req.prompt
        assert "SENTINEL_ALVEOLI" in req.prompt
        assert req.metadata["key_concept"] == spec.chapter


class TestKeyConceptDerivation:
    """_derive_key_concept strips numbering markers deterministically."""

    def test_strips_various_markers(self) -> None:
        from maieutica.generate.bundle import _derive_key_concept

        assert _derive_key_concept("1) 코", "FB") == "코"
        assert _derive_key_concept("가) 외비강", "FB") == "외비강"
        assert _derive_key_concept("2.1 가스 교환", "FB") == "가스 교환"

    def test_falls_back_when_empty(self) -> None:
        from maieutica.generate.bundle import _derive_key_concept

        assert _derive_key_concept(None, "8장 호흡계통") == "8장 호흡계통"
        assert _derive_key_concept("", "8장 호흡계통") == "8장 호흡계통"
        # All-marker label → nothing left → fall back.
        assert _derive_key_concept("1)", "8장 호흡계통") == "8장 호흡계통"


class TestDeterminism:
    """Identical inputs → byte-identical prompt (cache stability)."""

    def test_same_inputs_same_prompt(self) -> None:
        from maieutica.generate.bundle import build_bundle

        spec = _make_spec()
        chunks = _make_chunks()
        slot = _assigned_slot_for_chunk(spec, chunks, "chunk0801")
        avoid = ["포인트1", "포인트2"]

        req_a = build_bundle(slot, spec, chunks, avoid_list=avoid)
        req_b = build_bundle(slot, spec, chunks, avoid_list=avoid)

        assert req_a.prompt == req_b.prompt
        assert req_a.metadata == req_b.metadata
        assert req_a.context_refs == req_b.context_refs
