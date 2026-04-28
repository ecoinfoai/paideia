"""FreetextAuditRow + write_freetext_audit unit tests [T051].

The roberta-marked positive path (real model load + tokenization) needs
the kote cache and runs only when the operator has it. The non-marked
tests below exercise the deterministic invariants on hand-built rows
so the schema + writer scaffolding is covered without torch.

Spec: 003-needs-map-v0-1-1/tasks.md T051; FR-031.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from paideia_shared.schemas import FreetextAuditRow


def _row(
    *,
    student_id: str = "2026194567",
    freetext_source: str = "q61_anxiety",
    token_index: int = 0,
    token_text: str = "수업",  # noqa: S107
    token_id: int = 12345,
    char_start: int = 0,
    char_end: int = 2,
    redacted_text_length: int = 12,
) -> FreetextAuditRow:
    return FreetextAuditRow(
        student_id=student_id,
        semester="2026-1",
        course_slug="anatomy",
        freetext_source=freetext_source,  # type: ignore[arg-type]
        redacted_text_sha256="a" * 64,
        redacted_text_length=redacted_text_length,
        token_index=token_index,
        token_text=token_text,
        token_id=token_id,
        char_start=char_start,
        char_end=char_end,
        model_id="searle-j/kote_for_easygoing_people",
        model_sha256="b" * 64,
        tokenizer_vocab_sha256="c" * 64,
    )


def test_write_freetext_audit_writes_parquet_sorted(tmp_path: Path) -> None:
    """Output is sorted by (student_id, freetext_source, token_index)."""
    from needs_map.free_text.audit import write_freetext_audit

    rows = [
        _row(student_id="2026194002", token_index=1),
        _row(student_id="2026194001", token_index=0),
        _row(student_id="2026194001", token_index=1),
    ]
    parquet_path = write_freetext_audit(rows, tmp_path)
    assert parquet_path.is_file()
    df = pd.read_parquet(parquet_path)
    assert df["student_id"].tolist() == [
        "2026194001",
        "2026194001",
        "2026194002",
    ]
    assert df["token_index"].tolist() == [0, 1, 1]


def test_write_freetext_audit_empty_input_writes_empty_parquet(
    tmp_path: Path,
) -> None:
    """An empty cohort still writes a parquet with the canonical schema."""
    from needs_map.free_text.audit import write_freetext_audit

    parquet_path = write_freetext_audit([], tmp_path)
    assert parquet_path.is_file()
    df = pd.read_parquet(parquet_path)
    assert df.empty
    canonical = list(FreetextAuditRow.model_fields.keys())
    assert list(df.columns) == canonical


def test_freetext_audit_row_char_offsets_invariant(tmp_path: Path) -> None:
    """char_start ≤ char_end ≤ redacted_text_length — schema enforced."""
    with pytest.raises(ValueError):
        _row(char_start=5, char_end=2)
    with pytest.raises(ValueError):
        _row(char_start=0, char_end=20, redacted_text_length=10)
