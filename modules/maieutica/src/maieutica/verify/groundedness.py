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

from paideia_shared.schemas import MaieuticaTextbookEvidence, QuizItemCandidate

from maieutica.generate.quiz_gen import MISSING_EVIDENCE_PLACEHOLDER
from maieutica.silver.evidence_index import EvidenceIndex


def verify_groundedness(
    item: QuizItemCandidate,
    evidence_index: EvidenceIndex,
) -> QuizItemCandidate:
    """Anchor ``item``'s answer-point against the chapter-scoped index.

    Steps:
    1. Derive the search term from ``item.key_concept``.  If it is missing or
       equals the :data:`~maieutica.generate.quiz_gen.MISSING_EVIDENCE_PLACEHOLDER`
       sentinel, the answer-point is unverifiable → ``status="미확인"`` (the
       sentinel is never searched as a literal term).
    2. Otherwise look the term up in ``evidence_index`` (substring search over
       the ORIGINAL textbook lines).  A hit yields ``status="확인"`` with the
       owning chunk_id + char range; no hit yields ``status="미확인"``.
    3. Ground the leap too (T038 / FR-012): the leap is "one step further" on
       the SAME answer-point, so it is anchored against the chapter index by the
       same ``key_concept`` term.  An in-range concept yields ``확인``; an
       external new fact yields ``미확인``.  The leap evidence is attached via a
       NESTED ``model_copy`` — first copy the leap with its new
       ``textbook_evidence``, then copy the candidate with the new leap.  The
       leap's ``text`` (and therefore the V4 ``answer_explanation_combined``
       fold) is never altered.
    4. Return the candidate copy carrying both the item-level evidence and the
       leap-level evidence.

    This function never mutates ``item`` (frozen Pydantic model).

    Args:
        item: The generated quiz candidate (``textbook_evidence`` is ``None``).
        evidence_index: **Chapter-scoped** index over original textbook lines;
            must be built from the SAME chapter as ``item.chapter_no``.

    Returns:
        A NEW ``QuizItemCandidate`` whose ``textbook_evidence`` and
        ``leap.textbook_evidence`` are each set to a ``확인``/``미확인``
        :class:`MaieuticaTextbookEvidence`.
    """
    key_concept = item.key_concept

    if not key_concept or key_concept == MISSING_EVIDENCE_PLACEHOLDER:
        # No real answer-point term → cannot anchor; do not search the sentinel.
        evidence = MaieuticaTextbookEvidence(
            source_file=evidence_index.source_file,
            search_term=None,
            status="미확인",
        )
    else:
        evidence = evidence_index.lookup(key_concept)

    # The leap shares the answer-point, so it is grounded by the same evidence
    # lookup (a NEW MaieuticaTextbookEvidence — never the same frozen instance).
    leap_evidence = evidence.model_copy()
    grounded_leap = item.leap.model_copy(
        update={"textbook_evidence": leap_evidence}
    )

    return item.model_copy(
        update={"textbook_evidence": evidence, "leap": grounded_leap}
    )


__all__ = ["verify_groundedness"]
