"""T050 — CanonicalStudentId must reject non-ASCII (Unicode) digit strings.

Audit finding MC-U04: pydantic v2 ``\\d`` matches Unicode digits, so Arabic-Indic
10-digit strings like ``٠١٢٣٤٥٦٧٨٩`` were wrongly accepted.  After T051 the
pattern is ``^[0-9]{10}$``, which is strictly ASCII.

RED state (pre-fix): Arabic-Indic case does NOT raise → test fails.
GREEN state (post-fix): both assertions pass.
"""

import pytest
from paideia_shared.schemas.metric_codex import PseudonymMapEntry
from pydantic import ValidationError


class TestCanonicalStudentIdAsciiOnly:
    """CanonicalStudentId accepts ASCII digits and rejects Unicode digits."""

    def test_ascii_digit_id_accepted(self) -> None:
        """A standard ASCII 10-digit id must be accepted."""
        entry = PseudonymMapEntry(
            student_id="2026000001",
            pseudonym="S001",
        )
        assert entry.student_id == "2026000001"

    def test_arabic_indic_digits_rejected(self) -> None:
        """Arabic-Indic 10-digit string (U+0660..U+0669) must raise ValidationError.

        Pre-fix: pydantic \\d matches these → wrongly accepted (RED).
        Post-fix: [0-9] is ASCII-only → rejected (GREEN).
        """
        with pytest.raises(ValidationError):
            PseudonymMapEntry(
                student_id="٠١٢٣٤٥٦٧٨٩",  # U+0660..U+0669
                pseudonym="S001",
            )
