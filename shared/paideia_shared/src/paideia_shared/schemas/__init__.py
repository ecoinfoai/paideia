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
from .axis_summary import AxisSummaryRow
from .cluster_assignment import (
    ClusterAssignmentRow,
    ClusterCandidate,
    ClusterReport,
)
from .cluster_score_comparison import (
    ClusterPairwise,
    ClusterRow,
    ClusterScoreComparison,
)
from .cohort_row import CohortRow
from .combined_analysis_manifest import CombinedAnalysisManifest
from .combined_analysis_row import CombinedAnalysisRow
from .correlation_cell import CorrelationCell
from .curriculum_map import CurriculumEntry, CurriculumMap
from .diagnostic_mapping import (
    DiagnosticMappingConfig,
    MappingAxes,
    MappingColumn,
    MappingMetadata,
)
from .diagnostic_response import DiagnosticResponse
from .email_dispatch_log_row import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)
from .email_dispatch_manifest import (
    EmailManifest,
    EmailManifestCounts,
    EmailManifestInputs,
    EmailManifestOutputs,
)
from .email_dispatch_report import DispatchReportData
from .email_mapping_entry import EmailMappingEntry
from .email_message_draft import EmailMessageDraft
from .emphasis_cell import EmphasisCell
from .exam_item import ExamItem
from .exam_item_draft import ExamItemDraft, TextbookEvidence
from .exam_result import ExamResult
from .examen_blueprint import ExamenBlueprint
from .examen_manifest import ExamenManifest
from .factor_scores import FactorScoreRow
from .factor_scores_long import FactorScoresLongRow
from .free_text_categorization import FreeTextRow
from .freetext_audit import FreetextAuditRow
from .histogram_bin import HistogramBin
from .immersio_phase1_manifest import ImmersioPhase1Manifest
from .item_statistics import DistractorLabel, ItemStatistics
from .legacy_diff_entry import LegacyDiffEntry
from .maieutica import (
    FormativeItemCandidate,
    LeapExplanation,
    MaieuticaGenerationSpec,
    MaieuticaManifest,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)
from .manifest import IngestInput, IngestManifest, IngestRowCount
from .metadata_aggregate import MetadataAggregate, MetadataKind, TestKind
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
from .pre_send_summary import PreSendSummary
from .professor_profile import ProfessorProfile
from .regression_summary import RegressionCoefficient, RegressionFitSummary
from .scale_reliability import ReliabilityLabel, ScaleReliabilityReport, ScaleReliabilityRow
from .source_inventory_entry import SourceInventoryEntry
from .student_exam_metrics import StudentExamMetrics
from .student_master import StudentMaster
from .student_pdf_bundle import StudentPDFBundle
from .subgroup_score_comparison import SubgroupScoreComparison
from .test_profile import DummyStudent, TestProfile
from .textbook_chunk import TextbookChunk

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
    "ItemStatistics",
    "DistractorLabel",
    "StudentExamMetrics",
    "MetadataAggregate",
    "MetadataKind",
    "TestKind",
    "HistogramBin",
    "LegacyDiffEntry",
    "ImmersioPhase1Manifest",
    # Phase 3 combined-analysis (spec 005) — M1-M7
    "CombinedAnalysisRow",
    "CorrelationCell",
    "RegressionCoefficient",
    "RegressionFitSummary",
    "ClusterScoreComparison",
    "ClusterPairwise",
    "ClusterRow",
    "SubgroupScoreComparison",
    "CombinedAnalysisManifest",
    # spec 006 immersio-email v0.1.0 — 8 models + 3 enums
    "DispatchStatus",
    "DispatchMode",
    "CohortLabel",
    "CohortRow",
    "DispatchLogRow",
    "EmailManifest",
    "EmailManifestInputs",
    "EmailManifestOutputs",
    "EmailManifestCounts",
    "DispatchReportData",
    "EmailMappingEntry",
    "EmailMessageDraft",
    "ProfessorProfile",
    "StudentPDFBundle",
    "DummyStudent",
    "TestProfile",
    # spec 007 immersio-email v0.1.1 — 1 new model
    "PreSendSummary",
    # spec 008 examen question-gen — 7 new models (T004-T011)
    "ExamenBlueprint",
    "CurriculumEntry",
    "CurriculumMap",
    "SourceInventoryEntry",
    "TextbookChunk",
    "EmphasisCell",
    "TextbookEvidence",
    "ExamItemDraft",
    "ExamenManifest",
    # spec 009 maieutica question-gen — 6 new models (T005-T011)
    "MaieuticaTextbookEvidence",
    "MaieuticaGenerationSpec",
    "LeapExplanation",
    "QuizItemCandidate",
    "FormativeItemCandidate",
    "MaieuticaManifest",
]
