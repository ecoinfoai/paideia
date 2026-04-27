"""Cross-module data contracts (Pydantic v2). Bronze/Silver/Gold layer schema."""

from ._common import (
    CanonicalStudentId,
    CourseSlug,
    OutputKey,
    SectionLabel,
    SemesterCode,
    StandardAxisKey,
)
from .cluster_assignment import (
    ClusterAssignmentRow,
    ClusterCandidate,
    ClusterReport,
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
from .factor_scores import FactorScoreRow
from .free_text_categorization import FreeTextRow
from .manifest import IngestInput, IngestManifest, IngestRowCount
from .needs_map_manifest import (
    LLMCallStat,
    NeedsMapInput,
    NeedsMapManifest,
    NeedsMapPhaseRowCount,
)
from .scale_reliability import ScaleReliabilityReport, ScaleReliabilityRow
from .student_master import StudentMaster

__all__ = [
    "CanonicalStudentId",
    "SemesterCode",
    "CourseSlug",
    "OutputKey",
    "SectionLabel",
    "StandardAxisKey",
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
    "NeedsMapInput",
    "LLMCallStat",
    "NeedsMapPhaseRowCount",
    "NeedsMapManifest",
    "ScaleReliabilityRow",
    "ScaleReliabilityReport",
    "FactorScoreRow",
    "ClusterAssignmentRow",
    "ClusterCandidate",
    "ClusterReport",
    "FreeTextRow",
]
