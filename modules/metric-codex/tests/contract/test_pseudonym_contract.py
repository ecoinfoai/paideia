"""Contract tests for PseudonymMapEntry (spec 013 T007).

Pattern: ^S\\d{3,}$
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas.metric_codex import PseudonymMapEntry
from pydantic import ValidationError


class TestPseudonymPattern:
    def test_s001_accepted(self):
        entry = PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S001")
        assert entry.pseudonym == "S001"

    def test_s012_accepted(self):
        PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S012")

    def test_s999_accepted(self):
        PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S999")

    def test_s1000_accepted(self):
        """4-digit suffix (>=3 required) should be fine."""
        PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S1000")

    def test_s1_rejected(self):
        """Only one digit — must fail."""
        with pytest.raises(ValidationError):
            PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S1")

    def test_s12_rejected(self):
        """Only two digits — must fail."""
        with pytest.raises(ValidationError):
            PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S12")

    def test_x001_rejected(self):
        """Wrong prefix."""
        with pytest.raises(ValidationError):
            PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="X001")

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="")

    def test_lowercase_s_rejected(self):
        with pytest.raises(ValidationError):
            PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="s001")

    def test_name_kr_optional(self):
        entry = PseudonymMapEntry(student_id="2026194999", name_kr="홍길동", pseudonym="S001")
        assert entry.name_kr == "홍길동"

    def test_student_id_pattern_enforced(self):
        """CanonicalStudentId must be 10 digits."""
        with pytest.raises(ValidationError):
            PseudonymMapEntry(student_id="123", name_kr=None, pseudonym="S001")

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            PseudonymMapEntry(
                student_id="2026194999",
                name_kr=None,
                pseudonym="S001",
                extra_field="oops",
            )

    def test_immutable(self):
        entry = PseudonymMapEntry(student_id="2026194999", name_kr=None, pseudonym="S001")
        with pytest.raises((ValidationError, TypeError)):
            entry.pseudonym = "S002"  # type: ignore[misc]
