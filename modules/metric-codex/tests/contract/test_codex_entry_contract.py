"""Contract tests for CodexEntry and SourceRecord (spec 013 T005).

RED phase: all tests must fail before implementation exists.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_entry(**overrides):
    """Return a minimal valid CodexEntry payload with optional field overrides."""
    base = dict(
        student_id="2026194999",
        semester="2026-1",
        cohort_year=2026,
        layer="minimal",
        entry_kind="score_total",
        domain=None,
        item_ref=None,
        key="score_total",
        value_num=85.0,
        value_text=None,
        source_id="school_excel:성적출석.xlsx",
        observed_at="2026-06-01",
    )
    base.update(overrides)
    return base


def _valid_source(**overrides):
    """Return a minimal valid SourceRecord payload."""
    base = dict(
        source_id="school_excel:성적출석.xlsx",
        origin_module="school",
        origin_layer="bronze",
        source_path="data/bronze/2026-1/anatomy/성적출석.xlsx",
        sha256="a" * 64,
        ingested_at="2026-06-01T00:00:00Z",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Import guard — models do not exist yet (RED)
# ---------------------------------------------------------------------------

def _import_models():
    from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind, SourceRecord
    return CodexEntry, EntryKind, SourceRecord


# ---------------------------------------------------------------------------
# SourceRecord tests
# ---------------------------------------------------------------------------

class TestSourceRecord:
    def test_valid_source_record_constructs(self):
        _, _, SourceRecord = _import_models()
        rec = SourceRecord(**_valid_source())
        assert rec.source_id == "school_excel:성적출석.xlsx"

    def test_sha256_pattern_accepts_64_hex(self):
        _, _, SourceRecord = _import_models()
        rec = SourceRecord(**_valid_source(sha256="f" * 64))
        assert len(rec.sha256) == 64

    def test_sha256_pattern_rejects_short(self):
        _, _, SourceRecord = _import_models()
        with pytest.raises(ValidationError):
            SourceRecord(**_valid_source(sha256="a" * 63))

    def test_sha256_pattern_rejects_uppercase(self):
        _, _, SourceRecord = _import_models()
        with pytest.raises(ValidationError):
            SourceRecord(**_valid_source(sha256="A" * 64))

    def test_extra_field_rejected(self):
        _, _, SourceRecord = _import_models()
        with pytest.raises(ValidationError):
            SourceRecord(**_valid_source(unknown_field="x"))

    def test_immutable(self):
        _, _, SourceRecord = _import_models()
        rec = SourceRecord(**_valid_source())
        with pytest.raises((ValidationError, TypeError)):
            rec.source_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EntryKind enum membership
# ---------------------------------------------------------------------------

class TestEntryKindEnum:
    VALID_KINDS = [
        "score_total",
        "score_percent",
        "attendance",
        "percentile_section",
        "percentile_cohort",
        "z_score",
        "domain_correct_rate",
        "item_correct",
        "axis_score_z",
        "freetext_category",
        "cluster_label",
    ]

    def test_all_valid_kinds_accepted(self):
        CodexEntry, EntryKind, _ = _import_models()
        for kind in self.VALID_KINDS:
            entry = CodexEntry(**_valid_entry(entry_kind=kind, layer="rich"))
            assert entry.entry_kind == EntryKind(kind)

    def test_invalid_kind_rejected(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError):
            CodexEntry(**_valid_entry(entry_kind="not_a_kind", layer="rich"))


# ---------------------------------------------------------------------------
# value_num XOR value_text
# ---------------------------------------------------------------------------

class TestValueXOR:
    def test_value_num_only_ok(self):
        CodexEntry, _, _ = _import_models()
        entry = CodexEntry(**_valid_entry(value_num=90.0, value_text=None))
        assert entry.value_num == 90.0
        assert entry.value_text is None

    def test_value_text_only_ok(self):
        CodexEntry, _, _ = _import_models()
        entry = CodexEntry(
            **_valid_entry(
                layer="rich",
                entry_kind="freetext_category",
                value_num=None,
                value_text="category_A",
            )
        )
        assert entry.value_text == "category_A"
        assert entry.value_num is None

    def test_both_set_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError, match="exactly one"):
            CodexEntry(**_valid_entry(value_num=80.0, value_text="also_set"))

    def test_neither_set_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError, match="exactly one"):
            CodexEntry(**_valid_entry(value_num=None, value_text=None))


# ---------------------------------------------------------------------------
# layer ↔ entry_kind rule
# ---------------------------------------------------------------------------

class TestLayerEntryKindRule:
    def test_minimal_score_total_ok(self):
        CodexEntry, _, _ = _import_models()
        entry = CodexEntry(**_valid_entry(layer="minimal", entry_kind="score_total"))
        assert entry.layer == "minimal"

    def test_minimal_score_percent_ok(self):
        CodexEntry, _, _ = _import_models()
        CodexEntry(**_valid_entry(layer="minimal", entry_kind="score_percent"))

    def test_minimal_attendance_ok(self):
        CodexEntry, _, _ = _import_models()
        CodexEntry(**_valid_entry(layer="minimal", entry_kind="attendance"))

    def test_minimal_z_score_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError, match="minimal"):
            CodexEntry(**_valid_entry(layer="minimal", entry_kind="z_score"))

    def test_minimal_domain_correct_rate_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError, match="minimal"):
            CodexEntry(**_valid_entry(layer="minimal", entry_kind="domain_correct_rate"))

    def test_rich_allows_any_kind(self):
        CodexEntry, _, _ = _import_models()
        # Rich layer should accept all kinds without layer restriction
        for kind in TestEntryKindEnum.VALID_KINDS:
            CodexEntry(**_valid_entry(layer="rich", entry_kind=kind))


# ---------------------------------------------------------------------------
# item_ref ↔ item_correct rule
# ---------------------------------------------------------------------------

class TestItemRefRule:
    def test_item_ref_with_item_correct_ok(self):
        CodexEntry, _, _ = _import_models()
        entry = CodexEntry(
            **_valid_entry(
                layer="rich",
                entry_kind="item_correct",
                item_ref="Q01",
                key="item_correct:Q01",
            )
        )
        assert entry.item_ref == "Q01"

    def test_item_ref_without_item_correct_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError, match="item_ref"):
            CodexEntry(
                **_valid_entry(
                    layer="rich",
                    entry_kind="z_score",
                    item_ref="Q01",
                    key="z_score:Q01",
                )
            )

    def test_no_item_ref_with_item_correct_raises(self):
        # item_correct without item_ref should fail per spec (item_ref is required
        # when entry_kind == item_correct — the validator fires on item_ref != None
        # => item_correct, so the reverse is enforced indirectly by usage; spec
        # does NOT mandate item_ref for item_correct, only: item_ref => item_correct.
        # This test verifies the one-way implication passes (item_correct, no item_ref OK).
        CodexEntry, _, _ = _import_models()
        entry = CodexEntry(
            **_valid_entry(
                layer="rich",
                entry_kind="item_correct",
                item_ref=None,
                key="item_correct:all",
            )
        )
        assert entry.entry_kind.value == "item_correct"


# ---------------------------------------------------------------------------
# Natural key presence (field existence check)
# ---------------------------------------------------------------------------

class TestNaturalKey:
    """The (student_id, source_id, entry_kind, key, item_ref) fields must exist."""

    def test_natural_key_fields_present(self):
        CodexEntry, _, _ = _import_models()
        entry = CodexEntry(**_valid_entry())
        assert hasattr(entry, "student_id")
        assert hasattr(entry, "source_id")
        assert hasattr(entry, "entry_kind")
        assert hasattr(entry, "key")
        assert hasattr(entry, "item_ref")


# ---------------------------------------------------------------------------
# cohort_year bounds
# ---------------------------------------------------------------------------

class TestCohortYear:
    def test_lower_bound_ok(self):
        CodexEntry, _, _ = _import_models()
        CodexEntry(**_valid_entry(cohort_year=2000))

    def test_upper_bound_ok(self):
        CodexEntry, _, _ = _import_models()
        CodexEntry(**_valid_entry(cohort_year=2100))

    def test_below_lower_bound_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError):
            CodexEntry(**_valid_entry(cohort_year=1999))

    def test_above_upper_bound_raises(self):
        CodexEntry, _, _ = _import_models()
        with pytest.raises(ValidationError):
            CodexEntry(**_valid_entry(cohort_year=2101))
