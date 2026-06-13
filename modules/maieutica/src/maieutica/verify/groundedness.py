"""T028 — Groundedness verification: anchor the answer-point in the textbook.

``verify_groundedness(item, evidence_index) -> QuizItemCandidate``

quiz_gen (T027) freezes a complete ``QuizItemCandidate`` with
``textbook_evidence=None``.  This stage FINALIZES that field (SC-007 /
FR-002 / FR-003 authority): it searches the candidate's answer-point — its
``key_concept`` — against the CHAPTER-SCOPED
:class:`~maieutica.silver.evidence_index.EvidenceIndex`, producing a
:class:`~paideia_shared.schemas.MaieuticaTextbookEvidence` with the owning
chunk_id and ORIGINAL char range when found, or ``status="미확인"`` otherwise,
and sets it via ``model_copy`` (the model is frozen; in-place mutation raises).

Sentinel handling (FR-002 / SC-007)
-----------------------------------
``key_concept`` may be (or be padded with) ``quiz_gen.MISSING_EVIDENCE_PLACEHOLDER``
— LLM under-fill padding rather than a real term.  Such a value is NEVER passed
to the index search as a literal term; the answer-point is treated as
unverified (``status="미확인"``) so no external/unconfirmed knowledge silently
passes.

Chapter-scope is the CALLER's responsibility: pass the index built from the
slot's chapter file, not a multi-chapter aggregate.  Mirrors
``examen.verify.groundedness``.
"""

from __future__ import annotations

from paideia_shared.schemas import (
    FormativeItemCandidate,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)

from maieutica.generate.quiz_gen import MISSING_EVIDENCE_PLACEHOLDER
from maieutica.silver.evidence_index import EvidenceIndex


def verify_groundedness(
    item: QuizItemCandidate,
    evidence_index: EvidenceIndex,
    *,
    subsection_chunk_id: str | None = None,
) -> QuizItemCandidate:
    """Anchor ``item``'s answer-point against the chapter-scoped index.

    Behavior is switched by ``subsection_chunk_id``:

    - **Legacy path** (``subsection_chunk_id is None``): anchor by
      ``item.key_concept`` over the WHOLE index.  If ``key_concept`` is missing
      or equals the
      :data:`~maieutica.generate.quiz_gen.MISSING_EVIDENCE_PLACEHOLDER` sentinel
      it is unverifiable → ``status="미확인"`` (the sentinel is never searched as
      a literal term); otherwise a whole-index substring lookup yields
      ``확인``/``미확인``.  This path is unchanged from v0.1.0.
    - **Answer-anchored path** (``subsection_chunk_id`` given, US1): anchor the
      CORRECT answer option's evidence — ``option_evidence[answer_no - 1]`` —
      SCOPED to that subsection (G1/G2).  The term is the correct option's
      evidence string; an empty term or the sentinel → ``status="미확인"`` (G3,
      sentinel never searched).  Otherwise a SCOPED two-direction substring
      lookup (see :meth:`EvidenceIndex.lookup`) restricted to lines owned by
      ``subsection_chunk_id`` yields ``확인`` (with ``chunk_id ==
      subsection_chunk_id`` and the matched line) or ``미확인`` (G3).

    The leap is grounded by copying the resulting item evidence onto
    ``item.leap`` via a NESTED ``model_copy`` (T038 / FR-012); the leap's
    ``text`` (and therefore the V4 ``answer_explanation_combined`` fold) is never
    altered.  This function never mutates ``item`` (frozen Pydantic model).

    Args:
        item: The generated quiz candidate (``textbook_evidence`` is ``None``).
        evidence_index: **Chapter-scoped** index over original textbook lines;
            must be built from the SAME chapter as ``item.chapter_no``.
        subsection_chunk_id: When set, switch to the answer-anchored path and
            restrict the lookup to that subsection's chunk.

    Returns:
        A NEW ``QuizItemCandidate`` whose ``textbook_evidence`` and
        ``leap.textbook_evidence`` are each set to a ``확인``/``미확인``
        :class:`MaieuticaTextbookEvidence`.
    """
    if subsection_chunk_id is None:
        term = item.key_concept
    else:
        idx = item.answer_no - 1
        term = (
            item.option_evidence[idx]
            if 0 <= idx < len(item.option_evidence)
            else None
        )
    sentinel = not term or term == MISSING_EVIDENCE_PLACEHOLDER

    if sentinel:
        # No real answer-point term → cannot anchor; do not search the sentinel.
        evidence = MaieuticaTextbookEvidence(
            source_file=evidence_index.source_file,
            search_term=None,
            status="미확인",
        )
    elif subsection_chunk_id is None:
        evidence = evidence_index.lookup(term)
    else:
        evidence = evidence_index.lookup(term, chunk_id=subsection_chunk_id)

    # The leap shares the answer-point, so it is grounded by the same evidence
    # lookup (a NEW MaieuticaTextbookEvidence — never the same frozen instance).
    #
    # Approximation (v0.1.0): leap grounding reuses the SAME key_concept lookup as
    # the item answer-point — it does NOT scan leap.text for external facts. A leap
    # whose key_concept is in-range but whose text introduces an external concept
    # still gets status="확인". US5's adversarial review pass (review_agent, R8) is
    # the backstop that scans leap.text for external/uncited content.
    leap_evidence = evidence.model_copy()
    grounded_leap = item.leap.model_copy(
        update={"textbook_evidence": leap_evidence}
    )

    return item.model_copy(
        update={"textbook_evidence": evidence, "leap": grounded_leap}
    )


def ground_formative(
    item: FormativeItemCandidate,
    evidence_index: EvidenceIndex,
) -> FormativeItemCandidate:
    """Anchor a formative item's content against the chapter-scoped index.

    ``generate_formative_item`` freezes a complete
    :class:`~paideia_shared.schemas.FormativeItemCandidate` with
    ``textbook_evidence=None``.  This stage FINALIZES that field (US3 acceptance
    "내용이 해당 챕터 교재 근거 범위 안" / FR-002): it searches the candidate's
    ``topic`` key term against the CHAPTER-SCOPED
    :class:`~maieutica.silver.evidence_index.EvidenceIndex`, producing a
    :class:`~paideia_shared.schemas.MaieuticaTextbookEvidence` with the owning
    chunk_id and ORIGINAL char range when found (``status="확인"``), or
    ``status="미확인"`` otherwise, and sets it via ``model_copy`` (the model is
    frozen; in-place mutation raises).

    This is the formative analogue of :func:`verify_groundedness`'s
    ``key_concept`` approach — the same v0.1.0 approximation (a single key-term
    substring lookup, not a full-content scan) applies.  Chapter-scope is the
    CALLER's responsibility: pass the index built from the slot's chapter file.

    Args:
        item: The generated formative candidate (``textbook_evidence`` is
            ``None``).
        evidence_index: **Chapter-scoped** index over original textbook lines;
            must be built from the SAME chapter as ``item.chapter_no``.

    Returns:
        A NEW ``FormativeItemCandidate`` whose ``textbook_evidence`` is set to a
        ``확인``/``미확인`` :class:`MaieuticaTextbookEvidence`.
    """
    topic = item.topic

    if not topic:
        # No anchor term → cannot anchor; record an explicit 미확인.
        evidence = MaieuticaTextbookEvidence(
            source_file=evidence_index.source_file,
            search_term=None,
            status="미확인",
        )
    else:
        evidence = evidence_index.lookup(topic)

    return item.model_copy(update={"textbook_evidence": evidence})


__all__ = ["ground_formative", "verify_groundedness"]
