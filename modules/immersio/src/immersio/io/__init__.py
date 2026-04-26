"""Bronze input parsers for the four ingest source formats."""

from .attendance import parse_attendance_xlsx
from .diagnostic import parse_diagnostic_csv
from .exam_omr import parse_exam_omr_xls
from .exam_yaml import parse_exam_yaml

__all__ = [
    "parse_diagnostic_csv",
    "parse_exam_omr_xls",
    "parse_attendance_xlsx",
    "parse_exam_yaml",
]
