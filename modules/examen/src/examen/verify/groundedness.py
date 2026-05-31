"""T027 — Groundedness verification: re-check textbook evidence anchor.

``verify_groundedness(item, evidence_index) -> ExamItemDraft``

The item already carries ``textbook_evidence`` anchored at gen-time
(``examen.generate.item_gen``).  This function RE-CHECKS the item's
``key_concept`` against the ORIGINAL textbook lines via the CHAPTER-SCOPED
evidence index, setting ``status="확인"`` only if the term is found, else
``"미확인"``.

Design notes
------------
- Never silently pass an unanchored item: if ``key_concept`` is ``None``
  or absent from the index, status is always ``"미확인"``.
- The function always returns a new ``ExamItemDraft`` via ``model_copy``
  (the schema is frozen; in-place mutation raises ``FrozenInstanceError``).
- Non-textbook items (``source="formative"`` / ``"quiz"``) that carry
  ``textbook_evidence=None`` are returned unchanged — those paths are
  verified by different rules (US2 / US3).
- Chapter-scope is the CALLER's responsibility: pass the index built from
  the slot's chapter file, not a multi-chapter aggregate.
"""

from __future__ import annotations

from paideia_shared.schemas import ExamItemDraft, TextbookEvidence

from examen.silver.evidence_index import EvidenceIndex


def verify_groundedness(
    item: ExamItemDraft,
    evidence_index: EvidenceIndex,
) -> ExamItemDraft:
    """Re-check ``item.key_concept`` against the chapter-scoped evidence index.

    Steps:
    1. If ``item.textbook_evidence is None`` and source is not ``"textbook"``,
       return the item unchanged (non-textbook items have no textbook anchor).
    2. Look up ``item.key_concept`` in ``evidence_index`` (substring search).
    3. Build a new ``TextbookEvidence`` with:
       - ``status="확인"`` if at least one hit is found (first hit used).
       - ``status="미확인"`` if no hits (or ``key_concept`` is ``None``).
    4. Return ``item.model_copy(update={"textbook_evidence": new_evidence})``.

    This function never mutates ``item`` (frozen Pydantic model).

    Args:
        item: The generated exam item to re-verify.
        evidence_index: **Chapter-scoped** searchable index over original
            textbook lines.  Must be built from the SAME chapter as
            ``item.chapter_no`` (caller responsibility).

    Returns:
        A new ``ExamItemDraft`` with ``textbook_evidence.status`` set
        to ``"확인"`` or ``"미확인"`` based on the re-check result.
    """
    # 비-교과서 문항이고 근거가 없으면 그대로 반환 (US2/US3 대상)
    if item.textbook_evidence is None and item.source != "textbook":
        return item

    # key_concept 검색
    key_concept = item.key_concept
    source_file = evidence_index.source_file

    if not key_concept:
        # key_concept 없음 → 앵커 불가 → 미확인
        new_evidence = TextbookEvidence(
            source_file=source_file,
            line=None,
            found_text=None,
            status="미확인",
            search_term=None,
        )
    else:
        hits = evidence_index.search(key_concept)
        if hits:
            first = hits[0]
            new_evidence = TextbookEvidence(
                source_file=source_file,
                line=first.line_no,
                found_text=first.found_text,
                status="확인",
                search_term=key_concept,
            )
        else:
            # 교재에서 찾을 수 없음 → 외부 지식 플래그
            new_evidence = TextbookEvidence(
                source_file=source_file,
                line=None,
                found_text=None,
                status="미확인",
                search_term=key_concept,
            )

    # frozen model → model_copy 로 새 객체 반환
    return item.model_copy(update={"textbook_evidence": new_evidence})


__all__ = ["verify_groundedness"]
