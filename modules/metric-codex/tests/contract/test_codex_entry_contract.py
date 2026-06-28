"""Contract tests for CodexEntry and SourceRecord (spec 013 T005)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind, SourceRecord
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
# SourceRecord tests
# ---------------------------------------------------------------------------


class TestSourceRecord:
    def test_valid_source_record_constructs(self):
        rec = SourceRecord(**_valid_source())
        assert rec.source_id == "school_excel:성적출석.xlsx"

    def test_sha256_pattern_accepts_64_hex(self):
        rec = SourceRecord(**_valid_source(sha256="f" * 64))
        assert len(rec.sha256) == 64

    def test_sha256_pattern_rejects_short(self):
        with pytest.raises(ValidationError):
            SourceRecord(**_valid_source(sha256="a" * 63))

    def test_sha256_pattern_rejects_uppercase(self):
        with pytest.raises(ValidationError):
            SourceRecord(**_valid_source(sha256="A" * 64))

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            SourceRecord(**_valid_source(unknown_field="x"))

    def test_immutable(self):
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
        for kind in self.VALID_KINDS:
            entry = CodexEntry(**_valid_entry(entry_kind=kind, layer="rich"))
            assert entry.entry_kind == EntryKind(kind)

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            CodexEntry(**_valid_entry(entry_kind="not_a_kind", layer="rich"))


# ---------------------------------------------------------------------------
# value_num XOR value_text
# ---------------------------------------------------------------------------


class TestValueXOR:
    def test_value_num_only_ok(self):
        entry = CodexEntry(**_valid_entry(value_num=90.0, value_text=None))
        assert entry.value_num == 90.0
        assert entry.value_text is None

    def test_value_text_only_ok(self):
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
        with pytest.raises(ValidationError, match="exactly one"):
            CodexEntry(**_valid_entry(value_num=80.0, value_text="also_set"))

    def test_neither_set_raises(self):
        with pytest.raises(ValidationError, match="exactly one"):
            CodexEntry(**_valid_entry(value_num=None, value_text=None))


# ---------------------------------------------------------------------------
# layer ↔ entry_kind rule
# ---------------------------------------------------------------------------


class TestLayerEntryKindRule:
    def test_minimal_score_total_ok(self):
        entry = CodexEntry(**_valid_entry(layer="minimal", entry_kind="score_total"))
        assert entry.layer == "minimal"

    def test_minimal_score_percent_ok(self):
        CodexEntry(**_valid_entry(layer="minimal", entry_kind="score_percent"))

    def test_minimal_attendance_ok(self):
        CodexEntry(**_valid_entry(layer="minimal", entry_kind="attendance"))

    def test_minimal_z_score_raises(self):
        with pytest.raises(ValidationError, match="minimal"):
            CodexEntry(**_valid_entry(layer="minimal", entry_kind="z_score"))

    def test_minimal_domain_correct_rate_raises(self):
        with pytest.raises(ValidationError, match="minimal"):
            CodexEntry(**_valid_entry(layer="minimal", entry_kind="domain_correct_rate"))

    def test_rich_allows_any_kind(self):
        # Rich layer should accept all kinds without layer restriction
        for kind in TestEntryKindEnum.VALID_KINDS:
            CodexEntry(**_valid_entry(layer="rich", entry_kind=kind))


# ---------------------------------------------------------------------------
# item_ref ↔ item_correct rule
# ---------------------------------------------------------------------------


class TestItemRefRule:
    def test_item_ref_with_item_correct_ok(self):
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
        with pytest.raises(ValidationError, match="item_ref"):
            CodexEntry(
                **_valid_entry(
                    layer="rich",
                    entry_kind="z_score",
                    item_ref="Q01",
                    key="z_score:Q01",
                )
            )

    def test_item_correct_without_item_ref_ok(self):
        # The implication is one-way: item_correct without item_ref is valid.
        entry = CodexEntry(
            **_valid_entry(
                layer="rich",
                entry_kind="item_correct",
                item_ref=None,
                key="item_correct:all",
            )
        )
        assert entry.entry_kind is EntryKind.item_correct


# ---------------------------------------------------------------------------
# Natural key field values
# ---------------------------------------------------------------------------


class TestNaturalKey:
    """The (student_id, source_id, entry_kind, key, item_ref) tuple round-trips."""

    def test_natural_key_values_round_trip(self):
        entry = CodexEntry(
            **_valid_entry(
                layer="rich",
                entry_kind="item_correct",
                item_ref="Q07",
                key="item_correct:Q07",
            )
        )
        natural_key = (
            entry.student_id,
            entry.source_id,
            entry.entry_kind,
            entry.key,
            entry.item_ref,
        )
        assert natural_key == (
            "2026194999",
            "school_excel:성적출석.xlsx",
            EntryKind.item_correct,
            "item_correct:Q07",
            "Q07",
        )


# ---------------------------------------------------------------------------
# cohort_year bounds
# ---------------------------------------------------------------------------


class TestCohortYear:
    def test_lower_bound_ok(self):
        CodexEntry(**_valid_entry(cohort_year=2000))

    def test_upper_bound_ok(self):
        CodexEntry(**_valid_entry(cohort_year=2100))

    def test_below_lower_bound_raises(self):
        with pytest.raises(ValidationError):
            CodexEntry(**_valid_entry(cohort_year=1999))

    def test_above_upper_bound_raises(self):
        with pytest.raises(ValidationError):
            CodexEntry(**_valid_entry(cohort_year=2101))


# ---------------------------------------------------------------------------
# T053 RED — V4: value_num finite guard (FR-023)
# ---------------------------------------------------------------------------


class TestValueNumFiniteGuard:
    """V4: value_num must be finite (NaN / ±inf rejected).

    T053 RED — these must FAIL until V4 is added to CodexEntry.
    T061 GREEN — after V4, all assertions must pass.
    """

    def test_nan_rejected(self):
        """value_num=NaN passes XOR but renders as 'nan'; V4 must reject it."""
        with pytest.raises(ValidationError, match="finite"):
            CodexEntry(**_valid_entry(value_num=float("nan")))

    def test_positive_inf_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            CodexEntry(**_valid_entry(value_num=float("inf")))

    def test_negative_inf_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            CodexEntry(**_valid_entry(value_num=float("-inf")))

    def test_finite_value_accepted(self):
        """A normal finite value must still be accepted."""
        entry = CodexEntry(**_valid_entry(value_num=42.5))
        assert entry.value_num == 42.5

    def test_zero_accepted(self):
        """Zero is finite and must be accepted."""
        entry = CodexEntry(**_valid_entry(value_num=0.0))
        assert entry.value_num == 0.0

    def test_negative_finite_accepted(self):
        """A negative finite value must be accepted."""
        entry = CodexEntry(**_valid_entry(value_num=-3.14))
        assert entry.value_num == -3.14
