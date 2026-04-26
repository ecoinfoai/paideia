"""Deterministic input normalization helpers.

Each helper covers a single concern (student ID, Likert text, multiselect,
encoding, file hashing) so the ingest pipeline can compose them without
hidden coupling.
"""

from .encoding import read_text_with_fallback
from .hashing import sha256_file
from .likert import LIKERT_TEXT_TO_INT, normalize_likert
from .multiselect import expand_multiselect
from .student_id import normalize_student_id

__all__ = [
    "normalize_student_id",
    "normalize_likert",
    "LIKERT_TEXT_TO_INT",
    "expand_multiselect",
    "read_text_with_fallback",
    "sha256_file",
]
