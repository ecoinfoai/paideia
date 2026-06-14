"""T026 (RED) — unit tests for ``maieutica.generate.bundle.build_bundle``.

Verifies that a quiz slot + generation spec + chunks produce a deterministic
``GenerationRequest``: byte-identical for identical inputs, prompt carries the
filled chapter/section context, context_refs are stably ordered, and metadata
carries downstream-traceability fields.
"""

from __future__ import annotations

from maieutica.generate.backend import GenerationRequest
from maieutica.plan.slots import Slot, plan_slots
from paideia_shared.schemas import MaieuticaGenerationSpec, TextbookChunk


def _make_spec(
    *,
    week: int = 9,
    chapter_no: int = 8,
    chapter: str = "8장 호흡계통",
    quiz_count: int = 20,
    formative_count: int = 3,
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


def _make_chunks(
    chapter_no: int = 8,
    chapter: str = "8장 호흡계통",
    n: int = 2,
) -> list[TextbookChunk]:
    """Build stub TextbookChunk list for a given chapter."""
    chunks: list[TextbookChunk] = []
    for i in range(n):
        chunks.append(
            TextbookChunk(
                semester="2026-1",
                course_slug="anatomy",
                chunk_id=f"chunk{chapter_no:02d}{i:02d}",
                chapter_no=chapter_no,
                chapter=chapter,
                section=f"{i + 1}. 절{i + 1}",
                source_file=f"{chapter_no}장.txt",
                line_start=1 + i * 20,
                line_end=20 + i * 20,
                text=(
                    f"Chapter {chapter_no} section {i + 1} 내용입니다. "
                    "허파꽈리에서 가스교환이 일어난다. 산소가 확산된다."
                ),
                removed_spans=[],
            )
        )
    return chunks


def _first_quiz_slot(spec: MaieuticaGenerationSpec) -> Slot:
    """Return the first quiz slot for a spec."""
    return next(s for s in plan_slots(spec) if s.kind == "quiz")


def _build(slot: Slot | None = None, spec=None, chunks=None) -> GenerationRequest:
    from maieutica.generate.bundle import build_bundle

    if spec is None:
        spec = _make_spec()
    if slot is None:
        slot = _first_quiz_slot(spec)
    if chunks is None:
        chunks = _make_chunks(chapter_no=spec.chapter_no)
    return build_bundle(slot, spec, chunks)


class TestBuildBundle:
    """Tests for build_bundle()."""

    def test_returns_generation_request(self) -> None:
        """build_bundle returns a GenerationRequest."""
        assert isinstance(self._build_req(), GenerationRequest)

    def _build_req(self) -> GenerationRequest:
        return _build()

    def test_slot_id_preserved(self) -> None:
        """GenerationRequest.slot_id matches the slot's slot_id."""
        spec = _make_spec()
        slot = _first_quiz_slot(spec)
        req = _build(slot=slot, spec=spec)
        assert req.slot_id == slot.slot_id

    def test_prompt_contains_chapter_context(self) -> None:
        """Prompt contains the chapter name from the spec."""
        spec = _make_spec(chapter="8장 호흡계통")
        req = _build(spec=spec)
        assert "8장 호흡계통" in req.prompt

    def test_prompt_contains_chunk_text(self) -> None:
        """Prompt contains the relevant chunk text (교재 근거)."""
        chunks = _make_chunks(chapter_no=8)
        req = _build(chunks=chunks)
        assert any(c.text[:20] in req.prompt for c in chunks)

    def test_prompt_contains_section_context(self) -> None:
        """Prompt carries section information from the matching chunks."""
        chunks = _make_chunks(chapter_no=8)
        req = _build(chunks=chunks)
        # The first chunk's section label must appear in the rendered prompt.
        assert chunks[0].section is not None
        assert chunks[0].section in req.prompt

    def test_prompt_no_unfilled_placeholders(self) -> None:
        """No ``{placeholder}`` braces remain after rendering."""
        req = _build()
        # Template uses {{ }} for the literal JSON braces, so a single { that is
        # immediately followed by a word char would indicate an unfilled field.
        import re

        leftovers = re.findall(r"\{[a-z_]+\}", req.prompt)
        assert not leftovers, f"unfilled placeholders: {leftovers}"

    def test_context_refs_not_empty_and_stable_order(self) -> None:
        """context_refs is non-empty and stably ordered (sorted/deterministic)."""
        chunks = _make_chunks(chapter_no=8, n=3)
        req_a = _build(chunks=list(reversed(chunks)))
        req_b = _build(chunks=chunks)
        assert len(req_a.context_refs) == 3
        # Order must not depend on input list order.
        assert req_a.context_refs == req_b.context_refs

    def test_metadata_contains_traceability_fields(self) -> None:
        """metadata carries slot_id, week, chapter, chapter_no."""
        spec = _make_spec(week=9, chapter_no=8)
        req = _build(spec=spec)
        assert req.metadata["chapter_no"] == 8
        assert req.metadata["week"] == 9
        assert req.metadata["slot_id"] == req.slot_id
        assert req.metadata["chapter"] == spec.chapter

    def test_build_bundle_deterministic_same_input(self) -> None:
        """Identical inputs produce identical request fields."""
        spec = _make_spec()
        slot = _first_quiz_slot(spec)
        chunks = _make_chunks(chapter_no=8)
        req_a = _build(slot=slot, spec=spec, chunks=chunks)
        req_b = _build(slot=slot, spec=spec, chunks=chunks)
        assert req_a.prompt == req_b.prompt
        assert req_a.context_refs == req_b.context_refs
        assert req_a.metadata == req_b.metadata

    def test_filters_chunks_to_correct_chapter(self) -> None:
        """Only chunks matching the slot's chapter_no appear in the prompt."""
        spec = _make_spec(chapter_no=8)
        chunks_8 = _make_chunks(chapter_no=8, chapter="8장 호흡계통")
        chunks_9 = _make_chunks(chapter_no=9, chapter="9장 순환계통")
        req = _build(spec=spec, chunks=chunks_8 + chunks_9)
        for c in chunks_9:
            assert c.text[:30] not in req.prompt


def test_prompt_requires_verbatim_option_evidence() -> None:
    """Prompt instructs option_evidence to be verbatim textbook quotes (FR-009/010 seam).

    The groundedness verifier anchors on ``option_evidence[answer_no-1]``, so the
    prompt must tell the model that each evidence — especially the correct
    option's — is a verbatim contiguous textbook substring, not a paraphrase or
    meta-note.  Without this the answer-anchor is often 미확인 and excluded.
    """
    req = _build()
    p = req.prompt
    assert "option_evidence" in p
    assert "글자 그대로" in p
    assert "정답 보기" in p
