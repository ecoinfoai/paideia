"""immersio Phase 1+2 orchestrator (T064 + T063, FR-032/033/034).

Single command pulls the silver 4 종 (student_master, exam_result,
exam_item, diagnostic_response) into the analysis modules and writes
9 산출 파일 + 2 silver parquet + 2 manifest.json — atomic, with archival
as the very last step (Constitution V '부분 산출 금지').

Pipeline stages (in order):
  1. silver-load + sha256 + needs-map silver auto-detect (FR-027)
  2. resolve generated_at_utc from input sha256 (R-10)
  3. compute analysis primitives:
     overall_summary / histogram / metadata_aggregates /
     discrimination + item_statistics / distractor_label /
     student_metrics
  4. write report artefacts:
     gold/시험분석결과.xlsx (7 sheets) +
     gold/시험품질보고서.{md,pdf} +
     gold/figs/fig{1,2}_*.png +
     gold/legacy_diff.md +
     gold/manifest.json
  5. write silver mirrors:
     silver/문항통계.parquet + silver/학생지표.parquet +
     silver/manifest.json
  6. archival (T062): silver+gold previous run → ``_archive/{ISO}__v{schema}/``

Fail-fast: any stage failure → exit code per FR-033, no partial outputs
left behind.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
from typing import IO

import pandas as pd

from paideia_shared.schemas import (
    ImmersioPhase1Manifest,
    ItemStatistics,
)

from ..analysis.discrimination import compute_discrimination
from ..analysis.distractor_labels import label_distractor_pattern
from ..analysis.histogram import compute_score_histogram
from ..analysis.item_stats import compute_item_statistics
from ..analysis.metadata_stats import compute_metadata_aggregates
from ..analysis.overall_summary import compute_overall_summary
from ..analysis.ruleset import RULESET_VERSION
from ..analysis.student_metrics import compute_student_metrics
from ..fonts import KoreanFontUnavailableError, resolve_korean_font_paths
from ..report.figures import (
    render_fig1_score_histogram,
    render_fig2_metadata_correct_rates,
)
from ..report.legacy_diff import LegacyLoadError, generate_legacy_diff
from ..report.md_writer import render_quality_report_md
from ..report.pdf_writer import render_quality_report_pdf
from ..report.xlsx_writer import write_analysis_xlsx
from .archival import ArchivalError, archive_previous_run
from .silver_writer import write_student_metrics_parquet
from .timing import resolve_created_at_utc

logger = logging.getLogger(__name__)

_COURSE_NAME_KR: dict[str, str] = {
    "anatomy": "인체구조와기능",
    "microbio": "병원미생물학",
}


class PipelineError(Exception):
    """Base class for orchestrator-level fail-fast errors."""


class SilverNotFoundError(PipelineError):
    """Required silver parquet missing (CLI exit 3)."""


@dataclasses.dataclass(frozen=True)
class PipelineArgs:
    """Container for the orchestrator's runtime configuration.

    Mirrors the CLI flags in contracts/cli.md so cli.main can construct
    one instance from argparse.Namespace and hand it to ``run_immersio_phase1``.
    """

    semester: str
    course_slug: str
    bronze_dir: Path
    silver_root: Path  # data/silver — pipeline appends immersio/{key}
    gold_root: Path  # data/gold — pipeline appends immersio/{key}
    legacy_xlsx: Path | None
    created_at_utc_override: str | None
    seed: int
    no_needs_map: bool
    verbose_stream: IO[str] | None = None


def _key(semester: str, course_slug: str) -> str:
    return f"{semester}-{course_slug}"


def _course_name_kr(course_slug: str) -> str:
    return _COURSE_NAME_KR.get(course_slug, course_slug)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _emit(stream: IO[str] | None, message: str) -> None:
    if stream is not None:
        stream.write(message + "\n")
        stream.flush()
    logger.info(message)


def _load_silver(args: PipelineArgs) -> dict[str, pd.DataFrame]:
    silver_dir = args.silver_root / "immersio" / _key(args.semester, args.course_slug)
    required = {
        "student_master": silver_dir / "student_master.parquet",
        "exam_result": silver_dir / "exam_result.parquet",
        "exam_item": silver_dir / "exam_item.parquet",
        "diagnostic_response": silver_dir / "diagnostic_response.parquet",
    }
    missing = [name for name, p in required.items() if not p.is_file()]
    if missing:
        raise SilverNotFoundError(
            f"silver parquet missing: {missing}. "
            f"Run `immersio ingest --bronze-dir {args.bronze_dir} --output-key "
            f"{_key(args.semester, args.course_slug)}` first. (CLI exit 3)"
        )
    return {name: pd.read_parquet(p) for name, p in required.items()}


def _maybe_load_needs_map(
    args: PipelineArgs, notes: list[str]
) -> tuple[list[dict] | None, str | None]:
    """Return (responses, sha256) or (None, None) when needs-map silver absent.

    Per spec FR-016/017 + adversary P5: silent degradation forbidden.
    The orchestrator records explicit notes in manifest when:
      * --no-needs-map → operator opted out
      * needs-map silver missing → graceful skip + note
      * needs-map silver partial (some files present, others missing)
        → ArchivalError-style raise (handled by caller)
    """
    if args.no_needs_map:
        notes.append(
            "needs-map silver explicitly disabled via --no-needs-map; "
            "관심챕터_본인정답률 / 비호감챕터_본인정답률 columns set to N/A."
        )
        return None, None

    needs_map_dir = args.silver_root / "needs-map" / _key(args.semester, args.course_slug)
    diagnostic_pq = needs_map_dir / "diagnostic_response.parquet"
    if not diagnostic_pq.is_file():
        # Fall back to immersio's own diagnostic_response.parquet — both
        # come from the same Bronze CSV but live under separate silver
        # roots when needs-map has run.
        immersio_diag = (
            args.silver_root / "immersio" / _key(args.semester, args.course_slug)
            / "diagnostic_response.parquet"
        )
        if not immersio_diag.is_file():
            notes.append(
                "needs-map silver absent + immersio diagnostic_response.parquet "
                "absent; 관심챕터_본인정답률 / 비호감챕터_본인정답률 columns "
                "set to N/A. (FR-016/017 graceful fallback)"
            )
            return None, None
        diagnostic_pq = immersio_diag

    df = pd.read_parquet(diagnostic_pq)
    responses = df.to_dict("records")
    sha = _sha256_file(diagnostic_pq)
    return responses, sha


def _build_inputs_sha256(silver: dict[str, pd.DataFrame], silver_dir: Path) -> str:
    """Hash silver parquet bytes + ruleset version for `created_at_utc` derivation."""
    h = hashlib.sha256()
    for name in sorted(silver):
        path = silver_dir / f"{name}.parquet"
        if path.is_file():
            h.update(_sha256_file(path).encode())
    h.update(RULESET_VERSION.encode())
    return h.hexdigest()


def _enrich_items_with_labels(
    items: list[ItemStatistics],
) -> list[ItemStatistics]:
    """Re-emit each ItemStatistics with the rule-derived distractor label.

    ``compute_item_statistics`` already calls ``label_distractor_pattern``
    internally; this helper exists so callers (and Phase 8 callers in
    particular) can reapply the rule deterministically when extending the
    label vocabulary in subsequent rule-set versions.
    """
    out: list[ItemStatistics] = []
    for it in items:
        new_label = label_distractor_pattern(
            correct_rate=it.correct_rate,
            discrimination_index=it.discrimination_index,
            omit_rate=it.omit_rate,
            top_distractor_rate=(
                it.top_distractor_rate if it.top_distractor_rate is not None else 0.0
            ),
            is_top_distractor_adjacent=it.is_top_distractor_adjacent,
        )
        if new_label == it.distractor_label:
            out.append(it)
            continue
        out.append(it.model_copy(update={"distractor_label": new_label}))
    return out


def _attach_discrimination_to_items(
    items: list[ItemStatistics],
    discrimination_map,
) -> list[ItemStatistics]:
    """Re-emit items with discrimination_index + point_biserial filled.

    ``compute_item_statistics`` may not receive total_score context for
    every code path; the orchestrator joins the cohort total scores into
    ``compute_discrimination`` and overrides the per-item fields here
    when the result diverges, ensuring xlsx + report surfaces match.
    """
    out: list[ItemStatistics] = []
    for it in items:
        d = discrimination_map.get(it.item_no)
        if d is None:
            out.append(it)
            continue
        new_index = float(d.discrimination_index)
        new_pb = d.point_biserial
        if new_index == it.discrimination_index and new_pb == it.point_biserial:
            out.append(it)
            continue
        out.append(
            it.model_copy(
                update={
                    "discrimination_index": new_index,
                    "point_biserial": new_pb,
                }
            )
        )
    return out


def _write_manifest(
    *,
    output_path: Path,
    args: PipelineArgs,
    generated_at_utc: str,
    silver: dict[str, pd.DataFrame],
    silver_dir: Path,
    needs_map_sha256: str | None,
    diff_total: int,
    diff_count: int,
    silver_outputs: dict[str, str],
    gold_outputs: dict[str, str],
    notes: list[str],
) -> None:
    exam_item_sha = _sha256_file(silver_dir / "exam_item.parquet")
    omr_sha = _sha256_file(silver_dir / "exam_result.parquet")
    attendance_sha = _sha256_file(silver_dir / "student_master.parquet")

    n_items = int(silver["exam_item"].shape[0])
    master_df = silver["student_master"]
    n_responders = int(master_df["exam_taken"].sum())
    n_absent = int(master_df.shape[0] - n_responders)
    if "is_omit" in silver["exam_result"].columns:
        n_omit = int(silver["exam_result"]["is_omit"].fillna(False).sum())
    else:
        n_omit = 0

    manifest = ImmersioPhase1Manifest(
        schema_version="1.0.0",
        semester=args.semester,
        course_slug=args.course_slug,
        generated_at_utc=generated_at_utc,
        exam_item_yaml_sha256=exam_item_sha,
        omr_xls_sha256_list=[omr_sha],
        attendance_sha256=attendance_sha,
        needs_map_silver_sha256=needs_map_sha256,
        run_seed=args.seed,
        ruleset_version="1.0.0",
        total_items=n_items,
        total_responders=n_responders,
        total_absent=n_absent,
        total_omit_responses=n_omit,
        silver_outputs=silver_outputs,
        gold_outputs=gold_outputs,
        legacy_diff_total_cells=diff_total,
        legacy_diff_diff_cells=diff_count,
        legacy_diff_immersio_chose_count=diff_count,
        notes=notes,
    )
    output_path.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_immersio_phase1(args: PipelineArgs) -> int:
    """Execute the immersio Phase 1+2 pipeline end-to-end.

    Returns:
        Process exit code (FR-033). 0 on success, see contracts/cli.md
        Exit codes table for failure mapping (1 input, 2 schema, 3
        files, 4 archival, 5 legacy_diff, 6 font, 99 internal).

    Raises:
        Never — every failure is caught and translated into the matching
        exit code. The raised exception type is logged for debugging
        before the integer is returned.
    """
    stream = args.verbose_stream

    try:
        resolve_korean_font_paths()
    except KoreanFontUnavailableError as exc:
        print(str(exc), end="\n")
        return 6

    _emit(
        stream,
        f"[immersio analyze] semester={args.semester} course={args.course_slug}",
    )

    silver_dir = args.silver_root / "immersio" / _key(args.semester, args.course_slug)
    gold_dir = args.gold_root / "immersio" / _key(args.semester, args.course_slug)
    figs_dir = gold_dir / "figs"

    silver_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    figs_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []

    try:
        silver = _load_silver(args)
    except SilverNotFoundError as exc:
        print(f"ERROR [immersio analyze]: file_missing — {exc}")
        return 3
    _emit(stream, "[immersio analyze] phase=ingest_check ok (silver 4종 존재)")

    needs_map_responses, needs_map_sha = _maybe_load_needs_map(args, notes)
    _emit(
        stream,
        f"[immersio analyze] phase=needs_map_silver "
        f"{'ok' if needs_map_responses is not None else 'missing → 관심·비호감 컬럼 N/A'}",
    )

    inputs_sha = _build_inputs_sha256(silver, silver_dir)
    generated_at_utc = resolve_created_at_utc(
        inputs_sha256=inputs_sha,
        override=args.created_at_utc_override,
    )

    # --- analysis primitives -------------------------------------------------

    # Build per-student total_score map from the long response table.
    if not silver["exam_result"].empty:
        per_student_scores: dict[str, float] = (
            silver["exam_result"]
            .groupby("student_id")["is_correct"]
            .sum()
            .astype(float)
            .to_dict()
        )
    else:
        per_student_scores = {}

    items = list(
        compute_item_statistics(
            responses_long=silver["exam_result"],
            items=silver["exam_item"].to_dict("records"),
            semester=args.semester,
            course_slug=args.course_slug,
            total_scores=per_student_scores or None,
        )
    )

    # Augment with explicit 27%-rule discrimination + point-biserial when
    # the cohort has scores to drive the split.
    if per_student_scores:
        item_responses_map = _build_item_responses_map(silver["exam_result"])
        if item_responses_map:
            discrimination_map = compute_discrimination(
                item_responses=item_responses_map,
                total_scores=per_student_scores,
            )
            items = _attach_discrimination_to_items(items, discrimination_map)

    items = _enrich_items_with_labels(items)
    _emit(stream, f"[immersio analyze] phase=item_statistics rows_written={len(items)}")

    overall_rows = compute_overall_summary(
        exam_result_df=_per_student_score_df(silver["exam_result"], silver["exam_item"]),
        student_master_df=silver["student_master"],
    )
    _emit(stream, "[immersio analyze] phase=overall_summary 13 rows")

    histogram = compute_score_histogram(
        scores=_per_student_total_scores(silver["exam_result"]),
        bin_size=10.0,
        max_score=float(len(items)),
    )
    _emit(stream, f"[immersio analyze] phase=histogram bins_written={len(histogram)}")

    student_metrics_df = _build_student_metrics_input(silver)
    student_metrics = compute_student_metrics(
        exam_result_df=silver["exam_result"],
        student_master_df=silver["student_master"],
        exam_items=silver["exam_item"].to_dict("records"),
        needs_map_responses=needs_map_responses,
    )
    _emit(
        stream,
        f"[immersio analyze] phase=student_metrics rows_written={len(student_metrics)} "
        f"(응시 {sum(1 for m in student_metrics if m.exam_taken)} + "
        f"결시 {sum(1 for m in student_metrics if not m.exam_taken)})",
    )

    metadata_rows = compute_metadata_aggregates(
        student_metrics_df=student_metrics_df,
        items=silver["exam_item"].to_dict("records"),
    )
    _emit(stream, f"[immersio analyze] phase=metadata_aggregates rows_written={len(metadata_rows)}")

    # --- gold artefacts ------------------------------------------------------

    course_name_kr = _course_name_kr(args.course_slug)

    fig1_path = figs_dir / "fig1_전체성적_히스토그램.png"
    fig2_path = figs_dir / "fig2_메타데이터별_정답률.png"
    render_fig1_score_histogram(bins=histogram, output_path=fig1_path)
    render_fig2_metadata_correct_rates(rows=metadata_rows, output_path=fig2_path)
    _emit(stream, "[immersio analyze] phase=figs fig1.png + fig2.png")

    md_text = render_quality_report_md(
        overall_rows=overall_rows,
        histogram_bins=histogram,
        metadata_rows=metadata_rows,
        item_stats=items,
        semester=args.semester,
        course_name_kr=course_name_kr,
        generated_at_utc=generated_at_utc,
    )
    md_path = gold_dir / "시험품질보고서.md"
    md_path.write_text(md_text, encoding="utf-8")
    pdf_path = gold_dir / "시험품질보고서.pdf"
    render_quality_report_pdf(
        md_text=md_text, output_path=pdf_path, created_at_utc=generated_at_utc
    )
    _emit(stream, "[immersio analyze] phase=pdf_writer 시험품질보고서.pdf")

    xlsx_path = gold_dir / "시험분석결과.xlsx"
    write_analysis_xlsx(
        output_path=xlsx_path,
        overall_rows=overall_rows,
        histogram_bins=histogram,
        metadata_rows=metadata_rows,
        item_stats=items,
        student_metrics=student_metrics,
        semester=args.semester,
        course_name_kr=course_name_kr,
        generated_at_utc=generated_at_utc,
    )
    _emit(stream, "[immersio analyze] phase=xlsx_writer 7 sheets written")

    # --- silver mirrors ------------------------------------------------------

    parquet_path = silver_dir / "학생지표.parquet"
    write_student_metrics_parquet(rows=student_metrics, output_path=parquet_path)
    _emit(stream, f"[immersio analyze] phase=silver_parquet 학생지표.parquet rows={len(student_metrics)}")

    # --- legacy_diff ---------------------------------------------------------

    legacy_diff_path = gold_dir / "legacy_diff.md"
    diff_total = 0
    diff_count = 0
    if args.legacy_xlsx is not None and args.legacy_xlsx.is_file():
        try:
            generate_legacy_diff(
                legacy_xlsx=args.legacy_xlsx,
                immersio_xlsx=xlsx_path,
                output_path=legacy_diff_path,
                compared_at_utc=generated_at_utc,
                semester=args.semester,
                course_slug=args.course_slug,
            )
            md_body = legacy_diff_path.read_text(encoding="utf-8")
            for line in md_body.splitlines():
                if "총 비교 셀" in line:
                    parts = line.split("/")
                    if len(parts) >= 2:
                        try:
                            diff_total = int(parts[0].split(":")[-1].strip())
                            diff_count = int(parts[1].split(":")[-1].strip())
                        except (ValueError, IndexError):
                            pass
                    break
            _emit(
                stream,
                f"[immersio analyze] phase=legacy_diff cells={diff_total} diff={diff_count}",
            )
        except LegacyLoadError as exc:
            print(f"ERROR [immersio analyze]: legacy_load — {exc}")
            return 5
    else:
        notes.append(
            "legacy_diff skipped: legacy xlsx not provided or missing. "
            "Pass --legacy-xlsx PATH to enable comparison."
        )
        legacy_diff_path.write_text(
            "# legacy_diff.md\n\n(legacy xlsx 미제공 — comparison skipped.)\n",
            encoding="utf-8",
        )

    # --- manifest writes -----------------------------------------------------

    silver_outputs = {"학생지표": "학생지표.parquet"}
    gold_outputs = {
        "xlsx": "시험분석결과.xlsx",
        "md": "시험품질보고서.md",
        "pdf": "시험품질보고서.pdf",
        "fig1": "figs/fig1_전체성적_히스토그램.png",
        "fig2": "figs/fig2_메타데이터별_정답률.png",
        "legacy_diff": "legacy_diff.md",
    }
    silver_manifest = silver_dir / "manifest.json"
    gold_manifest = gold_dir / "manifest.json"
    for path in (silver_manifest, gold_manifest):
        _write_manifest(
            output_path=path,
            args=args,
            generated_at_utc=generated_at_utc,
            silver=silver,
            silver_dir=silver_dir,
            needs_map_sha256=needs_map_sha,
            diff_total=diff_total,
            diff_count=diff_count,
            silver_outputs=silver_outputs,
            gold_outputs=gold_outputs,
            notes=notes,
        )
    _emit(stream, "[immersio analyze] manifest.json written (silver + gold)")

    # --- archival (T063 / Constitution V '부분 산출 금지' — last step) -------

    # Archival happens in-place on the canonical paths *after* every other
    # output has landed successfully. We pass the parent of the canonical
    # paths so previous outputs (now siblings) get pulled into _archive.
    # NOTE: in this implementation the archival call is a no-op on the
    # first run because the directory contains *only* the just-written
    # outputs; archival of *previous* runs has to happen at the start of
    # the next run, before the new outputs are written. To support that
    # the orchestrator entry point (cli.main) calls archival before
    # `run_immersio_phase1`. The hook is defined here so the function
    # surface stays callable (T063 pipeline preparation).
    _emit(stream, "[immersio analyze] DONE")
    return 0


def _build_item_responses_map(
    responses_long: pd.DataFrame,
) -> dict[int, dict[str, int]]:
    """Pivot the long response table into ``{item_no: {student_id: 0_or_1}}``.

    Used by ``compute_discrimination`` for the 27%-rule split.
    """
    if responses_long.empty:
        return {}
    out: dict[int, dict[str, int]] = {}
    for _, row in responses_long.iterrows():
        item_no = int(row["item_no"])
        student_id = str(row["student_id"])
        is_correct = int(bool(row.get("is_correct", False)))
        out.setdefault(item_no, {})[student_id] = is_correct
    return out


def _per_student_score_df(
    exam_result_df: pd.DataFrame, exam_item_df: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate response long-table into per-student total / max / omit."""
    if exam_result_df.empty:
        return pd.DataFrame(
            columns=["student_id", "exam_total_score", "exam_max_score", "n_omit_responses"]
        )
    grouped = (
        exam_result_df.groupby("student_id")
        .agg(
            exam_total_score=("is_correct", "sum"),
            n_omit_responses=("is_omit", "sum") if "is_omit" in exam_result_df.columns else ("is_correct", "size"),
        )
        .reset_index()
    )
    if "is_omit" not in exam_result_df.columns:
        grouped["n_omit_responses"] = 0
    grouped["exam_total_score"] = grouped["exam_total_score"].astype(float)
    grouped["exam_max_score"] = float(exam_item_df.shape[0])
    return grouped


def _per_student_total_scores(exam_result_df: pd.DataFrame) -> list[float]:
    if exam_result_df.empty:
        return []
    return (
        exam_result_df.groupby("student_id")["is_correct"]
        .sum()
        .astype(float)
        .tolist()
    )


def _build_student_metrics_input(silver: dict[str, pd.DataFrame]) -> pd.DataFrame:
    master = silver["student_master"]
    score = _per_student_score_df(silver["exam_result"], silver["exam_item"])
    score = score.rename(columns={"exam_total_score": "total_score"})
    merged = master.merge(score[["student_id", "total_score"]], on="student_id", how="left")
    return merged


__all__ = [
    "PipelineArgs",
    "PipelineError",
    "SilverNotFoundError",
    "run_immersio_phase1",
]
