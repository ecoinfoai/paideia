"""Cross-module data contracts (Pydantic v2). Bronze/Silver/Gold layer schema."""

from ._common import (
    STANDARD_AXIS_KEYS,
    AuxiliaryGroupKey,
    CanonicalStudentId,
    CourseSlug,
    FreetextAreaKey,
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
from .axis_summary import AxisSummaryRow
from .diagnostic_response import DiagnosticResponse
from .exam_item import ExamItem
from .exam_result import ExamResult
from .factor_scores import FactorScoreRow
from .factor_scores_long import FactorScoresLongRow
from .free_text_categorization import FreeTextRow
from .freetext_audit import FreetextAuditRow
from .manifest import IngestInput, IngestManifest, IngestRowCount
from .needs_map_manifest import (
    FontResolutionInfo,
    LLMCallStat,
    NeedsMapInput,
    NeedsMapManifest,
    NeedsMapPhaseRowCount,
    NewOutputsInfo,
    SentimentRunInfo,
    VocabularyInfo,
)
from .scale_reliability import ReliabilityLabel, ScaleReliabilityReport, ScaleReliabilityRow
from .student_master import StudentMaster

__all__ = [
    "CanonicalStudentId",
    "SemesterCode",
    "CourseSlug",
    "OutputKey",
    "SectionLabel",
    "StandardAxisKey",
    "STANDARD_AXIS_KEYS",
    "AuxiliaryGroupKey",
    "FreetextAreaKey",
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
    "ReliabilityLabel",
    "FactorScoreRow",
    "FactorScoresLongRow",
    "AxisSummaryRow",
    "FreetextAuditRow",
    "FontResolutionInfo",
    "SentimentRunInfo",
    "NewOutputsInfo",
    "VocabularyInfo",
    "ClusterAssignmentRow",
    "ClusterCandidate",
    "ClusterReport",
    "FreeTextRow",
]
