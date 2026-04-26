"""Cross-module data contracts (Pydantic v2). Bronze/Silver/Gold layer schema."""

from ._common import (
    CanonicalStudentId,
    CourseSlug,
    OutputKey,
    SectionLabel,
    SemesterCode,
)
from .diagnostic_mapping import (
    DiagnosticMappingConfig,
    MappingAxes,
    MappingColumn,
    MappingMetadata,
)
from .diagnostic_response import DiagnosticResponse
from .exam_item import ExamItem
from .exam_result import ExamResult
from .manifest import IngestInput, IngestManifest, IngestRowCount
from .student_master import StudentMaster

__all__ = [
    "CanonicalStudentId",
    "SemesterCode",
    "CourseSlug",
    "OutputKey",
    "SectionLabel",
    "StudentMaster",
    "DiagnosticResponse",
    "ExamResult",
    "ExamItem",
    "IngestInput",
    "IngestRowCount",
    "IngestManifest",
    "MappingMetadata",
    "MappingColumn",
    "MappingAxes",
    "DiagnosticMappingConfig",
]
