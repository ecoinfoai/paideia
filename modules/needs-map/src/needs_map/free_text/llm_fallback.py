"""LLM fallback for uncategorized free-text rows (T096, FR-015).

Walks the rows produced by :func:`classify_dictionary`, picks out the ones
whose ``match_source == 'uncategorized'``, and asks the LLM to assign a
category from the dictionary's known list. Each call goes through the PII
redactor BEFORE leaving the process (FR-PII-002 / adversary PAT-W1):

  1. Build a per-row payload using the original text + redact() against the
     ``StudentMaster.name`` list provided by the caller.
  2. If ``redact(...).validation_flag`` is False → block the call,
     ``LLMCallTracker.record_pii_validation(False)`` flips the manifest field
     permanently to False (adversary H-8), and the row stays as
     ``match_source='llm_fallback'`` with empty matched_categories.
  3. Otherwise call ``call_with_response_model`` → on success the row gets
     the LLM-suggested categories with ``match_source='llm'``. Any failure
     records ``llm_fallback`` and tracker.record(failure_kind=…).

Rows whose ``match_source`` is anything other than ``"uncategorized"`` are
returned untouched (dictionary matches, no_response, etc.).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from paideia_shared.schemas import FreeTextRow
from pydantic import BaseModel, ConfigDict, Field

from ..llm.client import call_with_response_model
from ..llm.fallback import LLMCallTracker
from ..llm.pii import redact

if TYPE_CHECKING:
    import instructor


class FreeTextCategoryOut(BaseModel):
    """instructor response_model for the LLM free-text categorization hook."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    categories: list[str] = Field(default_factory=list)


def _row_with_categories(
    row: FreeTextRow, categories: list[str], source: str
) -> FreeTextRow:
    """Return a clone of ``row`` with new matched_categories + match_source."""
    return FreeTextRow(
        student_id=row.student_id,
        item_id=row.item_id,
        matched_categories=categories,
        match_source=source,  # type: ignore[arg-type]
        raw_length=row.raw_length,
    )


def classify_with_llm_fallback(
    classified_rows: list[FreeTextRow],
    raw_texts: dict[tuple[str, str], str],
    *,
    allowed_categories: list[str],
    student_names: Iterable[str],
    llm_client: instructor.Instructor,
    llm_tracker: LLMCallTracker,
    llm_model: str,
    llm_retries: int,
) -> list[FreeTextRow]:
    """Re-classify uncategorized rows via LLM with PII redaction.

    Args:
        classified_rows: Output of :func:`classify_dictionary`.
        raw_texts: Lookup ``{(student_id, item_id): raw_text}`` so the LLM
            payload can be built without leaking the raw text into the row.
        allowed_categories: Whitelist of categories the LLM may suggest
            (typically every dictionary category name).
        student_names: Iterable of names from ``StudentMaster.name_kr``.
            Each non-empty name is stripped from the LLM payload (FR-PII-002).
        llm_client: instructor client materialized via make_client.
        llm_tracker: per-run accountancy.
        llm_model: model id.
        llm_retries: per-call retry count.

    Returns:
        New list of FreeTextRow with LLM-classified rows promoted.
    """
    name_list = [n for n in student_names if isinstance(n, str) and n]
    out: list[FreeTextRow] = []
    for row in classified_rows:
        if row.match_source != "uncategorized":
            out.append(row)
            continue

        raw = raw_texts.get((row.student_id, row.item_id), "")
        redacted, validation_ok = redact(raw, names=name_list)
        llm_tracker.record_pii_validation(validation_ok)
        if not validation_ok:
            # Block the call; downgrade row to llm_fallback empty list.
            from ..llm.client import LLMCallOutcome

            llm_tracker.record(
                "free_text",
                LLMCallOutcome(succeeded=False, failure_kind="pii_block"),
                student_id=row.student_id,
            )
            out.append(_row_with_categories(row, [], "llm_fallback"))
            continue

        prompt = (
            "다음 학생 자유서술을 아래 카테고리 중에서 0개 이상 선택하세요. "
            "신뢰할 수 없으면 빈 리스트를 반환하세요.\n\n"
            f"카테고리: {', '.join(allowed_categories)}\n"
            f"자유서술: {redacted}"
        )
        result, outcome = call_with_response_model(
            llm_client,
            FreeTextCategoryOut,
            [{"role": "user", "content": prompt}],
            retries=llm_retries,
            model=llm_model,
        )
        llm_tracker.record("free_text", outcome, student_id=row.student_id)

        if outcome.succeeded and isinstance(result, FreeTextCategoryOut):
            categories = [c for c in result.categories if c in allowed_categories]
            out.append(_row_with_categories(row, categories, "llm"))
        else:
            out.append(_row_with_categories(row, [], "llm_fallback"))
    return out
