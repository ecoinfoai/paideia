"""needs-map pipeline orchestration.

Skeleton T031 → Phase A+B wire T056. Phase C wired by T074, Phase D-E-F by T105.

Determinism axes (Phase 2 §5):
  1. KMeans seed=42 (Phase C, deferred)
  2. Sort all per-student outputs by canonical student_id ascending (here)
  3. matplotlib dpi=150 + bbox_inches='tight' (Phase E/F, deferred)
  4. reportlab Producer/Creator/CreationDate fixed (Phase E/F, deferred)

Cross-cutting:
  - PII redaction validation flag piped into NeedsMapManifest.pii_redaction_validated
    via LLMCallTracker (T026). Phases without LLM calls leave the flag True.
  - archive_previous_run runs BEFORE any output is written (FR-002 atomicity).
    Return value drops directly into NeedsMapManifest.previous_run_archive_path
    (qa Stage-2 candidate S-5 closure).
  - Per-axis missing_policy provenance fed into NeedsMapInput.missing_policy_source
    (Phase 2 §3.5; adversary H-1 mitigation).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import pandas as pd

# FreeTextRow imported lazily where needed
from paideia_shared.schemas import (
    ClusterAssignmentRow,
    ClusterReport,
    CourseSlug,
    DiagnosticMappingConfig,
    FactorScoreRow,
    FactorScoresLongRow,
    FontResolutionInfo,
    FreetextAuditRow,
    FreeTextRow,  # noqa: E402
    NeedsMapInput,
    NeedsMapManifest,
    NeedsMapPhaseRowCount,
    NewOutputsInfo,
    ScaleReliabilityRow,
    SemesterCode,
    SentimentRunInfo,
)
from pydantic import BaseModel, ConfigDict, Field

from .archive.mover import archive_previous_run
from .cards.batch import generate_all_cards
from .clustering.kmeans import cluster_students
from .clustering.naming import name_clusters
from .clustering.silhouette import recommend_k
from .factor_scores.aggregate import aggregate_axis
from .factor_scores.missing import apply_missing_policy
from .factor_scores.zscore import zscore
from .fonts import resolve_korean_font_paths
from .free_text.audit import write_freetext_audit
from .free_text.dictionary import classify_dictionary
from .free_text.llm_fallback import classify_with_llm_fallback
from .free_text.redaction import redact_pii
from .free_text.roberta_fallback import analyze_with_fallback
from .free_text.sentiment import negative_label_subset_sha256
from .io.keywords import compute_match_rate, load_keywords
from .io.mapping import load_mapping
from .io.silver import load_diagnostic_response, load_student_master
from .llm.client import make_client
from .llm.fallback import LLMCallTracker
from .reliability.cronbach import compute_reliability
from .report.aggregation import build_axis_summary_rows
from .report.cluster_summary import write_cluster_summary_xlsx
from .report.distribution import compute_axis_distributions
from .report.exports import write_axis_summary, write_factor_scores_long
from .report.partitions import compute_partition_for_axis
from .report.pdf_writer import render_group_distribution_pdf

PhaseSet = frozenset[Literal["A", "B", "C", "D", "E", "F"]]
_MODULE_VERSION = "needs-map/0.1.0"
_DEFAULT_MISSING_POLICY: Literal["drop", "mean_impute"] = "drop"
_STANDARD_AXES: tuple[str, ...] = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)
_AXIS_LABELS_KR: dict[str, str] = {
    "digital_efficacy": "도구 적응성",
    "motivation": "학습동기",
    "time_availability": "학습시간",
    "material_preference": "학습자료",
    "study_strategy": "학습전략",
    "study_environment": "학습환경",
    "social_learning": "협업",
    "feedback_seeking": "피드백",
}
_WEAK_STRUCTURE_THRESHOLD = 0.2
_SAMPLE_RATIO_THRESHOLD = 10  # sample/k must be ≥ this for k to be a valid candidate
_CANDIDATE_K_RANGE = range(2, 7)


def _now_utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class NeedsMapArgs(BaseModel):
    """Authoritative bundle of CLI arguments + resolved environment + run-time constants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    phases: PhaseSet
    input_root: Path
    output_root: Path
    seed: int
    created_at_utc: Annotated[
        str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    ] = Field(default_factory=_now_utc_iso)
    k_override: Annotated[int, Field(ge=2, le=6)] | None = None
    llm_enabled: bool
    llm_provider: Literal["anthropic", "openai"]
    llm_model: Annotated[str, Field(min_length=1)]
    llm_timeout_seconds: Annotated[float, Field(gt=0)] = 30.0
    llm_retries: Annotated[int, Field(ge=0)] = 1
    keyword_language: Annotated[str, Field(pattern=r"^[a-z]{2}$")] = "ko"
    dry_run: bool = False
    verbose: bool = False
    roberta_enabled: bool = True

    @property
    def output_key(self) -> str:
        return f"{self.semester}-{self.course_slug}"


def _silver_dir(args: NeedsMapArgs) -> Path:
    return args.output_root / "silver" / "needs-map" / args.output_key


def _gold_dir(args: NeedsMapArgs) -> Path:
    return args.output_root / "gold" / "needs-map" / args.output_key


def _resolve_mapping_path(args: NeedsMapArgs) -> Path:
    """Default mapping YAML location per contracts/cli.md "Input Discovery"."""
    return args.input_root / "bronze" / "매핑" / f"{args.course_slug}.diagnostic.yaml"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _likert_columns_for_axis(
    mapping: DiagnosticMappingConfig, axis_key: str
) -> list[str]:
    return [c.source for c in mapping.columns if c.kind == "likert" and c.axis == axis_key]


def _multiselect_columns_for_axis(
    mapping: DiagnosticMappingConfig, axis_key: str
) -> list[str]:
    return [
        c.source for c in mapping.columns if c.kind == "multiselect" and c.axis == axis_key
    ]


def _aggregate_for_axis(
    diag_df: pd.DataFrame, mapping: DiagnosticMappingConfig, axis_key: str
) -> pd.Series | None:
    likert = _likert_columns_for_axis(mapping, axis_key)
    if likert:
        return aggregate_axis(diag_df, axis_columns=likert, kind="mean")
    multiselect = _multiselect_columns_for_axis(mapping, axis_key)
    if multiselect:
        return aggregate_axis(diag_df, axis_columns=multiselect, kind="sum")
    return None


def _resolve_missing_policy_for_axis(
    mapping: DiagnosticMappingConfig, axis_key: str
) -> tuple[Literal["drop", "mean_impute"], Literal["yaml", "default"]]:
    """Per-axis missing policy + provenance flag.

    The mapping YAML schema does not yet carry a per-axis ``missing_policy``
    field (deferred to a later spec); for v0.1.0 every axis defaults to
    ``"drop"`` and provenance is recorded as ``"default"`` so manifest readers
    can tell a downstream consumer applied the code-side fallback rather than
    an explicit operator choice (Phase 2 §3.5).
    """
    _ = mapping, axis_key
    return _DEFAULT_MISSING_POLICY, "default"


def _build_factor_score_rows(
    diag_df: pd.DataFrame,
    student_master_df: pd.DataFrame,
    mapping: DiagnosticMappingConfig,
    standard_axes_used: list[str],
) -> list[dict]:
    """Assemble FactorScoreRow-shaped dicts for every responder.

    Returns a list of dicts (NOT a DataFrame) so Pydantic validation runs over
    the authoritative None/float values *before* pandas coerces None → NaN
    inside an ``object``-dtype column. ``_factor_score_rows_to_df`` produces
    the parquet-bound DataFrame after validation.

    Phase B output is responder-scoped (spec FR Edge Case "응답자 + 명단 합집합"
    is reserved for Phase F card generation). Skipped axes come out as
    ``None / None / True`` for ``score / z / missing`` so the M4 invariants
    (V1 nullness pair, V2 missing⇒None) hold.
    """
    responder_ids = sorted(diag_df["student_id"].unique().tolist())
    master_lookup = student_master_df.set_index("student_id").to_dict(orient="index")

    per_axis_score: dict[str, pd.Series] = {}
    per_axis_missing: dict[str, pd.Series] = {}
    per_axis_z: dict[str, pd.Series] = {}
    for axis in standard_axes_used:
        agg = _aggregate_for_axis(diag_df, mapping, axis)
        if agg is None:
            continue
        policy, _provenance = _resolve_missing_policy_for_axis(mapping, axis)
        agg = agg.reindex(responder_ids)
        resolved, missing = apply_missing_policy(agg, policy=policy)
        per_axis_score[axis] = resolved
        per_axis_missing[axis] = missing
        per_axis_z[axis] = zscore(resolved)

    rows: list[dict] = []
    for sid in responder_ids:
        master = master_lookup.get(sid)
        section = master["section"] if master else None
        if isinstance(section, float) and pd.isna(section):
            section = None
        row: dict = {
            "student_id": sid,
            "on_roster": bool(master["on_roster"]) if master else False,
            "responded": True,
            "section": section,
        }
        for axis in _STANDARD_AXES:
            if axis in per_axis_score:
                score = per_axis_score[axis].get(sid)
                missing = bool(per_axis_missing[axis].get(sid))
                z = per_axis_z[axis].get(sid)
                row[axis] = None if pd.isna(score) else float(score)
                row[f"{axis}_z"] = None if pd.isna(z) else float(z)
                row[f"{axis}_missing"] = missing
            else:
                row[axis] = None
                row[f"{axis}_z"] = None
                row[f"{axis}_missing"] = True
        rows.append(row)
    return rows


def _validate_factor_score_rows(rows: list[dict]) -> None:
    for row in rows:
        FactorScoreRow.model_validate(row)


def _factor_score_rows_to_df(rows: list[dict]) -> pd.DataFrame:
    """Convert validated dicts into a parquet-friendly DataFrame.

    Pandas would otherwise turn None (in nullable string columns like
    ``section``) into NaN-as-float on read-back; using ``object`` dtype keeps
    None visible to downstream consumers that re-validate.
    """
    return pd.DataFrame(rows)


def _make_llm_client_or_none(args: NeedsMapArgs) -> object | None:
    """Materialize an instructor client if and only if llm_enabled (FR-LLM-001).

    ``llm_enabled`` already incorporates the ``--no-llm`` > env priority decided
    at CLI dispatch time (Phase 2 §3.2).
    """
    if not args.llm_enabled:
        return None
    return make_client(
        provider=args.llm_provider,
        model=args.llm_model,
        timeout=args.llm_timeout_seconds,
    )


def _run_phase_c(
    *,
    fs_df: pd.DataFrame,
    args: NeedsMapArgs,
    tracker: LLMCallTracker,
) -> ClusterReport:
    """Phase C orchestration: recommend k → cluster → name → assemble report.

    FR-010: ``--k`` override forces a specific k unless the per-candidate sample
    threshold (sample/k < 10) auto-degrades to k=1. ``--k=1`` is rejected at the
    CLI layer and never reaches this function.

    FR-013: rule-based naming by default; LLM client (when llm_enabled) attempts
    polish; any failure routes to "llm_fallback" with manifest accounting via
    LLMCallTracker.

    Adversary H-3 mitigation: weak_structure_warning + sample_too_small_warning
    are explicit booleans on the report — never silent.
    """
    n_substantive = int(fs_df.dropna(how="all", subset=list(_STANDARD_AXES)).shape[0])

    candidates_in_range = [
        k for k in _CANDIDATE_K_RANGE if n_substantive // k >= _SAMPLE_RATIO_THRESHOLD
    ]
    sample_too_small = len(candidates_in_range) == 0

    k_override_reason: str | None = None
    if args.k_override is not None:
        k_used = args.k_override
        if not sample_too_small and k_used in candidates_in_range:
            chosen, candidate_table = recommend_k(
                fs_df, candidate_k=candidates_in_range, seed=args.seed
            )
            k_override_reason = (
                f"user --k {k_used} explicit override; auto-recommend would have been {chosen}"
            )
        else:
            # ClusterReport V1 still requires k_used to appear in candidates when
            # k_used > 1, so compute silhouette specifically for the override k.
            try:
                _, candidate_table = recommend_k(
                    fs_df, candidate_k=[k_used], seed=args.seed
                )
            except ValueError:
                candidate_table = []
            k_override_reason = (
                f"user --k {k_used} explicit override; sample_too_small={sample_too_small}"
            )
    elif sample_too_small:
        k_used = 1
        candidate_table = []
    else:
        k_used, candidate_table = recommend_k(
            fs_df, candidate_k=candidates_in_range, seed=args.seed
        )

    labels, info = cluster_students(fs_df, k=k_used, seed=args.seed)
    substantive_ids = info["substantive_student_ids"]

    # Distance to centroid for each labelled student.
    centroids = info["centroids"]
    matrix_imputed = info.get("_imputed_matrix")
    distances: list[float | None] = []
    if matrix_imputed is not None and len(centroids) > 0:
        for i, label in enumerate(labels):
            d = float(np.linalg.norm(matrix_imputed[i] - centroids[label]))
            distances.append(d)
    else:
        # k=1 path or empty axis set — no distance to report
        distances = [None] * len(labels)

    rows = [
        ClusterAssignmentRow(
            student_id=sid,
            cluster_id=int(label),
            distance_to_centroid=dist,
        )
        for sid, label, dist in zip(substantive_ids, labels, distances, strict=True)
    ]

    silhouette_used = next(
        (cand.silhouette_score for cand in candidate_table if cand.k == k_used),
        None,
    )
    weak_structure = (
        silhouette_used is not None and silhouette_used < _WEAK_STRUCTURE_THRESHOLD
    )

    centroid_df = pd.DataFrame(centroids, columns=info["axes_used"])

    llm_client = _make_llm_client_or_none(args)
    if not centroid_df.empty:
        cluster_names, naming_source = name_clusters(
            centroid_df,
            axis_labels_kr=_AXIS_LABELS_KR,
            llm_client=llm_client,
            llm_tracker=tracker,
            llm_model=args.llm_model,
            llm_retries=args.llm_retries,
        )
    else:
        cluster_names = {0: "단일 군집 (산출 불가)"}
        naming_source = "rule"

    # Restrict to actually used cluster_ids — V2 requires exact equality.
    used_cluster_ids = sorted({row.cluster_id for row in rows})
    cluster_names = {cid: cluster_names.get(cid, f"cluster_{cid}") for cid in used_cluster_ids}

    return ClusterReport(
        rows=rows,
        k_used=k_used,
        silhouette_used=silhouette_used,
        candidates=candidate_table,
        cluster_names=cluster_names,
        naming_source=naming_source,
        weak_structure_warning=weak_structure,
        sample_too_small_warning=sample_too_small,
        k_override_reason=k_override_reason,
        semester=args.semester,
        course_slug=args.course_slug,
        module_version=_MODULE_VERSION,
    )


def _scale_reliability_rows_to_df(rows: list[ScaleReliabilityRow]) -> pd.DataFrame:
    return pd.DataFrame([r.model_dump() for r in rows])


def _write_silver_atomic(silver_dir: Path, name: str, df: pd.DataFrame) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(silver_dir / name, index=False)


def _write_manifest_atomic(silver_dir: Path, manifest: NeedsMapManifest) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    (silver_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _factor_score_dict_to_long_row(
    fs_dict: dict, semester: str, course_slug: str
) -> FactorScoresLongRow:
    """Bridge a Phase B FactorScoreRow dict into a v0.1.1 long-form row.

    The Phase B dict carries 8 axis × {raw, z, missing} fields plus
    student_id / on_roster / responded / section. Auxiliary group, cluster,
    and freetext fields are not yet wired (Phase 6/8 will hydrate them).
    They are left at their schema defaults (``None`` / ``False``).
    """
    payload: dict = {
        "student_id": fs_dict["student_id"],
        "semester": semester,
        "course_slug": course_slug,
        "on_roster": fs_dict["on_roster"],
        "section": fs_dict.get("section"),
        "responded": fs_dict["responded"],
    }
    for axis in _STANDARD_AXES:
        raw = fs_dict.get(axis)
        z = fs_dict.get(f"{axis}_z")
        missing = fs_dict.get(f"{axis}_missing", raw is None)
        payload[f"{axis}_raw"] = raw
        payload[f"{axis}_z"] = z
        payload[f"{axis}_missing"] = bool(missing)
    return FactorScoresLongRow(**payload)


def _emit_v011_exports(
    *,
    gold_dir: Path,
    fs_rows: list[dict],
    scale_reliability_rows: list[ScaleReliabilityRow],
    free_text_rows: list,  # noqa: ANN401  # FreeTextRow imported lazily
    cluster_report: ClusterReport | None,
    cohort_size: int,
) -> NewOutputsInfo:
    """Run the v0.1.1 long CSV/YAML + axis_summary CSV/YAML writers (T038).

    Returns the populated :class:`NewOutputsInfo` with the four export
    paths set; ``manual_pdf`` and ``freetext_audit_parquet`` carry the
    canonical sibling paths even though Phase 7 / Phase 8 own their
    creation.
    """
    _ = cluster_report, free_text_rows  # not yet hydrated into long rows

    semester_str = next(
        iter({r.get("semester") for r in fs_rows if r.get("semester")}), ""
    )
    course_slug_str = next(
        iter({r.get("course_slug") for r in fs_rows if r.get("course_slug")}),
        "",
    )
    long_rows = [
        _factor_score_dict_to_long_row(
            r, semester_str or _placeholder_semester(), course_slug_str or "anatomy"
        )
        for r in fs_rows
    ]
    long_csv, long_yaml = write_factor_scores_long(long_rows, gold_dir)

    summary_rows = build_axis_summary_rows(
        scale_reliability=[
            r.model_dump() if hasattr(r, "model_dump") else r
            for r in scale_reliability_rows
        ],
        factor_scores_long=[lr.model_dump() for lr in long_rows],
        auxiliary_columns={},
        freetext_summaries={},
        n_cohort=cohort_size,
    )
    summary_csv, summary_yaml = write_axis_summary(summary_rows, gold_dir)

    return NewOutputsInfo(
        factor_scores_long_csv=str(long_csv),
        factor_scores_long_yaml=str(long_yaml),
        axis_summary_csv=str(summary_csv),
        axis_summary_yaml=str(summary_yaml),
        # Phase 7 (T048) writes manual.pdf; Phase 8 (T060) writes
        # freetext_audit.parquet. Path placeholders are recorded now so the
        # manifest is structurally complete; downstream phases will overwrite
        # these paths atomically.
        manual_pdf=str(gold_dir / "needs-map_manual.pdf"),
        freetext_audit_parquet=str(
            gold_dir.parent.parent.parent
            / "silver"
            / "needs-map"
            / gold_dir.name
            / "freetext_audit.parquet"
        ),
    )


def _placeholder_semester() -> str:
    """Fallback semester string for empty-cohort smoke tests (FR-014)."""
    return "1900-1"


def _freetext_source_for_column(source_column: str) -> str | None:
    """Map a diag_response source_column to the v0.1.1 FreetextAreaKey domain.

    The 2026-1 anatomy diagnostic uses Q61 (anxiety) + Q62 (experience).
    Returns ``None`` for sources that should not flow into sentiment
    (defensive — only known freetext columns are analysed).
    """
    if "Q61" in source_column or "anxiety" in source_column.lower():
        return "q61_anxiety"
    if "Q62" in source_column or "experience" in source_column.lower():
        return "q62_experience"
    return None


def _run_sentiment_phase(
    *,
    responses: list[tuple[str, str, str]],
    silver_dir: Path,
    student_names: list[str],
    roberta_enabled: bool,
    dry_run: bool,
) -> tuple[SentimentRunInfo, dict[tuple[str, str], object]]:
    """Run the v0.1.1 sentiment pass: redact → analyze → audit (T060/T061).

    Args:
        responses: ``(student_id, source_column, raw_text)`` triples from
            Phase D dictionary classification.
        silver_dir: Silver tier directory; freetext_audit.parquet lands here.
        student_names: Roster names to redact (in addition to 10-digit IDs).
        roberta_enabled: ``False`` short-circuits to fallback.
        dry_run: When True, the parquet is not written but the manifest
            information still reflects the would-be run.

    Returns:
        ``(SentimentRunInfo, freetext_sentiment_lookup)`` — the lookup
        keys (student_id, source_column) → SentimentResult so Phase E
        can hydrate factor_scores_long.freetext_q61/q62_* fields.
    """
    if not responses:
        return _empty_sentiment_info(roberta_enabled), {}

    redacted_texts: list[str] = []
    redacted_lookup: list[tuple[str, str, str]] = []  # (sid, source, redacted)
    for sid, source, raw in responses:
        redacted = redact_pii(raw, names=student_names)
        redacted_texts.append(redacted)
        redacted_lookup.append((sid, source, redacted))

    sentiment_results, fallback_report = analyze_with_fallback(
        redacted_texts, enabled=roberta_enabled
    )

    audit_rows: list[FreetextAuditRow] = []
    sentiment_lookup: dict[tuple[str, str], object] = {}
    for (sid, source, redacted), result in zip(
        redacted_lookup, sentiment_results, strict=True
    ):
        freetext_source = _freetext_source_for_column(source)
        if freetext_source is None:
            continue
        sentiment_lookup[(sid, freetext_source)] = result
        if (
            fallback_report.enabled
            and result.tokens
            and result.model_id is not None
            and result.model_sha256 is not None
            and result.tokenizer_vocab_sha256 is not None
        ):
            redacted_sha256 = hashlib.sha256(
                redacted.encode("utf-8")
            ).hexdigest()
            for token in result.tokens:
                audit_rows.append(
                    FreetextAuditRow(
                        student_id=sid,
                        semester=_placeholder_semester(),  # caller overrides
                        course_slug="anatomy",  # caller overrides
                        freetext_source=freetext_source,  # type: ignore[arg-type]
                        redacted_text_sha256=redacted_sha256,
                        redacted_text_length=len(redacted),
                        token_index=int(token["token_index"]),
                        token_text=str(token["token_text"]),
                        token_id=int(token["token_id"]),
                        char_start=int(token["char_start"]),
                        char_end=int(token["char_end"]),
                        model_id=result.model_id,
                        model_sha256=result.model_sha256,
                        tokenizer_vocab_sha256=result.tokenizer_vocab_sha256,
                    )
                )

    if not dry_run:
        write_freetext_audit(audit_rows, silver_dir)

    info = SentimentRunInfo(
        enabled=fallback_report.enabled,
        model_id=fallback_report.model_id,
        model_sha256=(
            sentiment_results[0].model_sha256
            if fallback_report.enabled and sentiment_results
            else None
        ),
        tokenizer_vocab_sha256=(
            sentiment_results[0].tokenizer_vocab_sha256
            if fallback_report.enabled and sentiment_results
            else None
        ),
        negative_label_subset_sha256=(
            negative_label_subset_sha256() if fallback_report.enabled else None
        ),
        n_attempted=fallback_report.n_attempted,
        n_succeeded=fallback_report.n_succeeded,
        n_fallback=fallback_report.n_fallback,
        fallback_reason=fallback_report.fallback_reason,
    )
    return info, sentiment_lookup


def _empty_sentiment_info(roberta_enabled: bool) -> SentimentRunInfo:
    """SentimentRunInfo for the empty-responses case (no freetext at all)."""
    return SentimentRunInfo(
        enabled=False,
        model_id=None,
        n_attempted=0,
        n_succeeded=0,
        n_fallback=0,
        fallback_reason="cli-disabled" if not roberta_enabled else "model-unavailable",
    )


def _build_font_resolution_info() -> FontResolutionInfo:
    """Resolve NanumGothic paths + tag the source per-face for the manifest (T026).

    The CLI pre-flight (T023) has already proven the fonts are resolvable;
    this re-resolves to capture the path + source enum for the manifest.
    Source is ``env-var-PAIDEIA_KR_FONT_PATH`` /
    ``env-var-PAIDEIA_KR_FONT_BOLD_PATH`` when the corresponding env-var is
    set, ``fc-match`` otherwise.

    Optional sha256 fingerprints are NOT computed yet — the manifest field
    is left as None pending a follow-up determinism check (FR-035).
    """
    regular_path, bold_path = resolve_korean_font_paths()
    regular_source = (
        "env-var-PAIDEIA_KR_FONT_PATH"
        if os.environ.get("PAIDEIA_KR_FONT_PATH")
        else "fc-match"
    )
    bold_source = (
        "env-var-PAIDEIA_KR_FONT_BOLD_PATH"
        if os.environ.get("PAIDEIA_KR_FONT_BOLD_PATH")
        else "fc-match"
    )
    return FontResolutionInfo(
        regular_path=str(regular_path),
        bold_path=str(bold_path),
        regular_source=regular_source,
        bold_source=bold_source,
    )


def run_needs_map(args: NeedsMapArgs) -> NeedsMapManifest:
    """Orchestrate Phase A-F per ``args.phases``.

    Phase A+B wired (T056); Phase C deferred to T074, Phase D-F to T105.
    """
    if not isinstance(args, NeedsMapArgs):
        raise TypeError(
            f"run_needs_map: expected NeedsMapArgs, got {type(args).__name__}."
        )

    if not args.phases:
        raise ValueError("run_needs_map: args.phases must be non-empty.")

    silver = _silver_dir(args)
    _ = _gold_dir(args)  # Phase E/F path reserved

    diag_df = load_diagnostic_response(args.input_root, args.semester, args.course_slug)
    master_df = load_student_master(args.input_root, args.semester, args.course_slug)
    mapping_path = _resolve_mapping_path(args)
    mapping = load_mapping(mapping_path)

    archive_label = archive_previous_run(silver) if not args.dry_run else None

    declared_axes = list(
        dict.fromkeys(list(mapping.axes.required) + list(mapping.axes.optional))
    )
    standard_axes_used = [a for a in _STANDARD_AXES if a in declared_axes]
    standard_axes_skipped = [a for a in _STANDARD_AXES if a not in standard_axes_used]

    missing_policy_source: dict[str, str] = {}
    for axis in standard_axes_used:
        _, provenance = _resolve_missing_policy_for_axis(mapping, axis)
        missing_policy_source[axis] = provenance

    tracker = LLMCallTracker()  # no LLM calls in Phase A+B; tracker stays empty

    rows_per_phase: list[NeedsMapPhaseRowCount] = []
    phases_executed: list[Literal["A", "B", "C", "D", "E", "F"]] = []
    new_outputs: NewOutputsInfo | None = None

    if "A" in args.phases:
        report = compute_reliability(diag_df, mapping)
        sr_df = _scale_reliability_rows_to_df(report.rows)
        if not args.dry_run:
            _write_silver_atomic(silver, "scale_reliability.parquet", sr_df)
        rows_per_phase.append(
            NeedsMapPhaseRowCount(phase="A", rows_written=len(report.rows))
        )
        phases_executed.append("A")

    if "B" in args.phases:
        fs_rows = _build_factor_score_rows(
            diag_df, master_df, mapping, standard_axes_used
        )
        _validate_factor_score_rows(fs_rows)
        fs_df = _factor_score_rows_to_df(fs_rows)
        if not args.dry_run:
            _write_silver_atomic(silver, "factor_scores.parquet", fs_df)
        rows_per_phase.append(
            NeedsMapPhaseRowCount(phase="B", rows_written=len(fs_df))
        )
        phases_executed.append("B")

    cluster_report: ClusterReport | None = None
    if "C" in args.phases:
        # Phase C requires Phase B output. fs_df is in scope from above when B was
        # requested; if B was skipped (degenerate caller) we synthesize on the fly.
        if "B" not in args.phases:
            fs_rows = _build_factor_score_rows(
                diag_df, master_df, mapping, standard_axes_used
            )
            _validate_factor_score_rows(fs_rows)
            fs_df = _factor_score_rows_to_df(fs_rows)

        cluster_report = _run_phase_c(
            fs_df=fs_df,
            args=args,
            tracker=tracker,
        )
        ca_df = pd.DataFrame([row.model_dump() for row in cluster_report.rows])
        if not args.dry_run:
            _write_silver_atomic(silver, "cluster_assignment.parquet", ca_df)
        rows_per_phase.append(
            NeedsMapPhaseRowCount(phase="C", rows_written=len(cluster_report.rows))
        )
        phases_executed.append("C")

    # ----------------------------------------------------------- Phase D
    free_text_rows: list[FreeTextRow] = []
    free_text_match_rate: float | None = None
    dictionary_language_mismatch = False
    sentiment_info: SentimentRunInfo | None = None
    freetext_sentiment: dict[tuple[str, str], object] = {}
    if "D" in args.phases:
        keyword_dict = load_keywords(args.keyword_language)
        # Build (student_id, item_id, raw_text) triples from diagnostic_response
        ft_subset = diag_df[diag_df["axis_kind"] == "freetext"]
        responses = [
            (str(row["student_id"]), str(row["source_column"]), str(row["value_text"] or ""))
            for _, row in ft_subset.iterrows()
        ]
        free_text_rows = classify_dictionary(responses, dictionary=keyword_dict)
        # LLM fallback for uncategorized rows when llm_enabled
        if args.llm_enabled and any(r.match_source == "uncategorized" for r in free_text_rows):
            client = _make_llm_client_or_none(args)
            if client is not None:
                raw_lookup = {
                    (sid, item_id): raw for sid, item_id, raw in responses
                }
                allowed = [entry.category for entry in keyword_dict.entries]
                names = [
                    n for n in master_df["name_kr"].dropna().tolist() if n
                ]
                free_text_rows = classify_with_llm_fallback(
                    free_text_rows,
                    raw_lookup,
                    allowed_categories=allowed,
                    student_names=names,
                    llm_client=client,
                    llm_tracker=tracker,
                    llm_model=args.llm_model,
                    llm_retries=args.llm_retries,
                )
        # Match-rate + language-mismatch warning (FR-023, adversary P-7)
        sample_texts = [raw for _, _, raw in responses]
        if sample_texts:
            free_text_match_rate = compute_match_rate(keyword_dict, sample_texts)
            dictionary_language_mismatch = (
                free_text_match_rate is not None and free_text_match_rate < 0.3
            )
        ft_df = pd.DataFrame([row.model_dump() for row in free_text_rows])
        if not args.dry_run:
            _write_silver_atomic(silver, "free_text_categorization.parquet", ft_df)

        # T060 — RoBERTa sentiment + per-token audit (US6).
        # Redact PII before inference, run analyze_with_fallback, then
        # write the per-token audit parquet. Fallback (cli-disabled /
        # torch-unavailable / model-unavailable) returns missing
        # SentimentResult instances + a fallback_reason recorded in the
        # manifest. ``sentiment_info`` populates manifest.sentiment.
        sentiment_info, freetext_sentiment = _run_sentiment_phase(
            responses=responses,
            silver_dir=silver,
            student_names=[
                n for n in master_df["name_kr"].dropna().tolist() if n
            ],
            roberta_enabled=args.roberta_enabled,
            dry_run=args.dry_run,
        )

        rows_per_phase.append(
            NeedsMapPhaseRowCount(phase="D", rows_written=len(free_text_rows))
        )
        phases_executed.append("D")

    # Group means in z-space (always 0 by construction; pre-computed for downstream)
    group_means_z: dict[str, float] = dict.fromkeys(_STANDARD_AXES, 0.0)

    # ----------------------------------------------------------- Phase E
    gold = _gold_dir(args)
    if "E" in args.phases:
        if not args.dry_run:
            gold.mkdir(parents=True, exist_ok=True)
        # Build distributions + partition comparisons
        if "B" not in args.phases:
            fs_rows = _build_factor_score_rows(
                diag_df, master_df, mapping, standard_axes_used
            )
            _validate_factor_score_rows(fs_rows)
            fs_df = _factor_score_rows_to_df(fs_rows)
        distributions = compute_axis_distributions(fs_df)
        # Partition comparisons: section + every column with partition_axis=True
        merged_for_partitions = fs_df.merge(
            master_df[["student_id", "section"]], on="student_id", how="left"
        )
        partition_results: list[dict] = []
        for axis in standard_axes_used:
            entry = compute_partition_for_axis(
                merged_for_partitions, partition_col="section", axis=axis
            )
            entry["partition_col"] = "section"
            entry["axis"] = axis
            partition_results.append(entry)
        # Free-text category counts for the bar chart
        free_text_summary: dict[str, int] = {}
        for row in free_text_rows:
            for cat in row.matched_categories:
                free_text_summary[cat] = free_text_summary.get(cat, 0) + 1

        if not args.dry_run:
            render_group_distribution_pdf(
                distributions=distributions,
                cluster_report=cluster_report,
                partition_results=partition_results,
                free_text_summary=free_text_summary,
                output_path=gold / "group_distribution.pdf",
                created_at_utc=args.created_at_utc,
                semester=args.semester,
                course_name_kr=mapping.metadata.course_name_kr or args.course_slug,
            )
            if cluster_report is not None:
                write_cluster_summary_xlsx(
                    cluster_report=cluster_report,
                    factor_scores_df=fs_df,
                    output_path=gold / "cluster_summary.xlsx",
                )
            # v0.1.1 Phase E append (T038): factor_scores_long + axis_summary
            # exports. The two writers are pure (FR-035 byte-equal) so they
            # can run unconditionally — operators always get the new gold
            # files alongside group_distribution.pdf + cluster_summary.xlsx.
            new_outputs = _emit_v011_exports(
                gold_dir=gold,
                fs_rows=fs_rows,
                scale_reliability_rows=(
                    list(report.rows) if "A" in args.phases else []
                ),
                free_text_rows=free_text_rows,
                cluster_report=cluster_report,
                cohort_size=len(fs_rows),
            )
            # T048: render the operator manual PDF after the four exports
            # land. The renderer is purely asset-driven (manual_text.ko.yaml
            # + 3 figure PNGs) so it does not depend on the run inputs;
            # cohort_n is informational only.
            from .report.manual import render_manual_pdf

            manual_path = gold / "needs-map_manual.pdf"
            render_manual_pdf(
                output_path=manual_path,
                semester=args.semester,
                course_name_kr=mapping.metadata.course_name_kr or args.course_slug,
                cohort_n=len(fs_rows),
                created_at_utc=args.created_at_utc,
            )
            new_outputs = NewOutputsInfo(
                factor_scores_long_csv=new_outputs.factor_scores_long_csv,
                factor_scores_long_yaml=new_outputs.factor_scores_long_yaml,
                axis_summary_csv=new_outputs.axis_summary_csv,
                axis_summary_yaml=new_outputs.axis_summary_yaml,
                manual_pdf=str(manual_path),
                freetext_audit_parquet=new_outputs.freetext_audit_parquet,
            )
        rows_per_phase.append(NeedsMapPhaseRowCount(phase="E", rows_written=1))
        phases_executed.append("E")

    # ----------------------------------------------------------- Phase F
    if "F" in args.phases:
        if not args.dry_run:
            gold.mkdir(parents=True, exist_ok=True)
        if "B" not in args.phases:
            fs_rows = _build_factor_score_rows(
                diag_df, master_df, mapping, standard_axes_used
            )
            _validate_factor_score_rows(fs_rows)
            fs_df = _factor_score_rows_to_df(fs_rows)
        client = _make_llm_client_or_none(args) if args.llm_enabled else None
        cards_count = generate_all_cards(
            factor_scores_df=fs_df,
            student_master_df=master_df,
            cluster_report=cluster_report,
            free_text_rows=free_text_rows,
            group_means=group_means_z,
            semester=args.semester,
            course_name_kr=mapping.metadata.course_name_kr or args.course_slug,
            output_dir=gold / "cards",
            created_at_utc=args.created_at_utc,
            llm_client=client,
            llm_tracker=tracker,
            llm_model=args.llm_model,
            llm_retries=args.llm_retries,
        ) if not args.dry_run else 0
        rows_per_phase.append(
            NeedsMapPhaseRowCount(phase="F", rows_written=cards_count)
        )
        phases_executed.append("F")

    # ------------------------------------------- assemble manifest + write
    diag_path = (
        args.input_root / "silver" / "immersio" / args.output_key / "diagnostic_response.parquet"
    )
    master_path = (
        args.input_root / "silver" / "immersio" / args.output_key / "student_master.parquet"
    )
    inputs = NeedsMapInput(
        diagnostic_response_path=str(diag_path.resolve()),
        diagnostic_response_sha256=_sha256(diag_path),
        student_master_path=str(master_path.resolve()),
        student_master_sha256=_sha256(master_path),
        diagnostic_mapping_path=str(mapping_path.resolve()),
        diagnostic_mapping_sha256=_sha256(mapping_path),
        keyword_dictionary_path=None,
        keyword_dictionary_sha256=None,
        missing_policy_source=dict(missing_policy_source),  # type: ignore[arg-type]
    )

    font_resolution = _build_font_resolution_info()

    manifest = NeedsMapManifest(
        semester=args.semester,
        course_slug=args.course_slug,
        output_key=args.output_key,
        module_version=_MODULE_VERSION,
        created_at_utc=args.created_at_utc,
        inputs=inputs,
        standard_axes_used=list(standard_axes_used),  # type: ignore[arg-type]
        standard_axes_skipped=list(standard_axes_skipped),  # type: ignore[arg-type]
        phases_executed=phases_executed,
        rows_per_phase=rows_per_phase,
        cluster_k_used=cluster_report.k_used if cluster_report is not None else None,
        cluster_silhouette_used=(
            cluster_report.silhouette_used if cluster_report is not None else None
        ),
        free_text_dictionary_match_rate=free_text_match_rate,
        dictionary_language_mismatch_warning=dictionary_language_mismatch,
        weak_structure_warning=(
            cluster_report.weak_structure_warning if cluster_report is not None else False
        ),
        llm_provider=args.llm_provider if args.llm_enabled else None,
        llm_model=args.llm_model if args.llm_enabled else None,
        llm_calls=tracker.to_stats(),
        pii_redaction_validated=tracker.pii_redaction_validated,
        previous_run_archive_path=archive_label,
        warnings=[],
        unrecognized_inputs=[],
        font_resolution=font_resolution,
        new_outputs=new_outputs,
        sentiment=sentiment_info,
    )

    if not args.dry_run:
        _write_manifest_atomic(silver, manifest)
        # Mirror the manifest into the Gold directory too (FR-023 sidecar policy:
        # both Silver and Gold trees carry the same manifest.json).
        if "E" in args.phases or "F" in args.phases:
            gold.mkdir(parents=True, exist_ok=True)
            _write_manifest_atomic(gold, manifest)

    return manifest
