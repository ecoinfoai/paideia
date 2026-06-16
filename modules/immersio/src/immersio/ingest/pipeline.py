"""Phase 0 ingest orchestrator.

Discovers Bronze inputs, parses each source, applies the diagnostic mapping,
combines per-student rows, validates the four Silver outputs, and writes
them atomically with the manifest sidecar.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import IO, Literal

import pandas as pd
from paideia_shared.schemas import (
    CourseSlug,
    DiagnosticMappingConfig,
    IngestInput,
    IngestManifest,
    IngestRowCount,
    OutputKey,
    SemesterCode,
)
from pydantic import ValidationError

from ..io import (
    parse_attendance_xlsx,
    parse_diagnostic_csv,
    parse_exam_omr_xls,
    parse_exam_yaml,
)
from ..io.exam_omr import DEFAULT_RESULT_EXCLUDE_TOKENS
from ..mapping import apply_mapping, load_mapping
from ..normalize import sha256_file
from .combine import combine_sources
from .errors import (
    DataIntegrityError,
    DuplicateStudentIdError,
    IngestValidationError,
    IngestViolation,
)
from .validate import validate_outputs
from .write import write_silver


def _data_integrity_violation(file_repr: str, exc: DuplicateStudentIdError) -> IngestViolation:
    """Wrap a DuplicateStudentIdError into a single IngestViolation."""
    return IngestViolation(
        file_path=file_repr,
        row_or_item_id=None,
        column_or_field="student_id",
        expected="unique student_id after canonical normalization",
        found=str(exc),
    )


_RECOGNIZED_SUBDIRS: tuple[str, ...] = ("진단평가", "시험성적", "출석", "시험문제")


def _safe_version(pkg: str) -> str:
    try:
        return version(pkg)
    except PackageNotFoundError:
        return "0.0.0"


def _git_commit_or_none(repo_root: Path) -> str | None:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    commit = out.stdout.strip()
    return commit or None


def _detect_unique_yaml(dir_path: Path) -> Path:
    yaml_files = sorted(list(dir_path.glob("*.yaml")) + list(dir_path.glob("*.yml")))
    if len(yaml_files) == 0:
        raise FileNotFoundError(
            f"run_ingest: no exam YAML found in {dir_path}; "
            f"either place a single *.yaml or pass --exam-yaml explicitly."
        )
    if len(yaml_files) > 1:
        raise ValueError(
            f"run_ingest: multiple exam YAML files found in {dir_path}; "
            f"specify --exam-yaml explicitly: "
            f"{[p.name for p in yaml_files]}."
        )
    return yaml_files[0]


def _walk_unrecognized(bronze_dir: Path, used_paths: set[Path]) -> list[str]:
    """Enumerate non-input files inside bronze_dir without following symlinks.

    AV-4b hardening: ``Path.rglob('*')`` follows symlinks and silently
    pulls files outside the Bronze tree into the manifest. We use
    ``os.walk(followlinks=False)`` and skip every symlinked entry so
    attacker-planted links cannot poison ``unrecognized_files``.
    """
    import os

    unrecognized: list[str] = []
    for current_dir, subdirs, filenames in os.walk(bronze_dir, followlinks=False):
        subdirs[:] = [d for d in subdirs if not Path(current_dir, d).is_symlink()]
        for filename in filenames:
            entry = Path(current_dir, filename)
            if entry.is_symlink():
                continue
            if entry in used_paths:
                continue
            rel = entry.relative_to(bronze_dir).as_posix()
            unrecognized.append(rel)
    return sorted(unrecognized)


def _print(stream: IO[str] | None, msg: str) -> None:
    if stream is not None:
        stream.write(msg + "\n")
        stream.flush()


def run_ingest(
    bronze_dir: Path,
    mapping_path: Path,
    exam_yaml: Path | None = None,
    output_key: OutputKey | None = None,
    output_dir: Path | None = None,
    *,
    no_git_commit: bool = False,
    verbose_stream: IO[str] | None = None,
    exam_result_pattern: str | None = None,
    exam_absent_pattern: str | None = None,
) -> IngestManifest:
    """Run the Phase 0 Bronze→Silver ingest pipeline end-to-end.

    Args:
        bronze_dir: Directory containing 진단평가/, 시험성적/, 출석/, 시험문제/.
        mapping_path: Diagnostic mapping YAML file path.
        exam_yaml: Explicit exam YAML path; if None, auto-detect when a single
            *.yaml exists under ``bronze_dir/시험문제/``.
        output_key: Override for the silver directory name. When None,
            derived as ``{semester}-{course_slug}`` from the mapping metadata.
        output_dir: Parent directory for silver outputs (default
            ``data/silver/immersio``).
        no_git_commit: If True, leaves manifest.git_commit as None.
        verbose_stream: Optional text stream that receives the seven-stage
            progress messages (typically sys.stdout).
        exam_result_pattern: Optional override glob for the per-section main
            result OMR workbook (FR-029). Forwarded to ``parse_exam_omr_xls``.
            When set, default exclude tokens stop applying.
        exam_absent_pattern: Reserved passthrough for symmetry with
            ``exam_result_pattern``. Currently unused (absent rows live in
            the 결시 sheet of each main result workbook).

    Returns:
        Validated IngestManifest describing the run.

    Raises:
        TypeError, FileNotFoundError, ValueError, pydantic.ValidationError:
            See individual stage parsers for their failure semantics.
    """
    if not isinstance(bronze_dir, Path):
        raise TypeError(f"run_ingest: bronze_dir must be Path, got {type(bronze_dir).__name__}.")
    if not isinstance(mapping_path, Path):
        raise TypeError(
            f"run_ingest: mapping_path must be Path, got {type(mapping_path).__name__}."
        )
    if not bronze_dir.is_dir():
        raise FileNotFoundError(f"run_ingest: bronze_dir missing: {bronze_dir}.")

    diag_dir = bronze_dir / "진단평가"
    exam_dir = bronze_dir / "시험성적"
    attendance_dir = bronze_dir / "출석"
    exam_yaml_dir = bronze_dir / "시험문제"
    for required in (diag_dir, exam_dir, attendance_dir, exam_yaml_dir):
        if not required.is_dir():
            raise FileNotFoundError(
                f"run_ingest: required Bronze subdirectory missing: {required}."
            )

    # === [1/7] Discover ===
    _print(verbose_stream, f"[1/7] Discovering Bronze inputs at {bronze_dir} ...")

    violations: list[IngestViolation] = []

    diag_csvs = sorted(diag_dir.glob("*.csv"))
    if len(diag_csvs) != 1:
        raise ValueError(
            f"run_ingest: expected exactly 1 diagnostic CSV in {diag_dir}, "
            f"found {len(diag_csvs)}: {[p.name for p in diag_csvs]}."
        )
    diag_csv_path = diag_csvs[0]

    attendance_files = sorted(attendance_dir.glob("*.xlsx"))
    if len(attendance_files) != 1:
        raise ValueError(
            f"run_ingest: expected exactly 1 attendance .xlsx in {attendance_dir}, "
            f"found {len(attendance_files)}: {[p.name for p in attendance_files]}."
        )
    attendance_path = attendance_files[0]

    if exam_yaml is None:
        exam_yaml_path = _detect_unique_yaml(exam_yaml_dir)
    else:
        exam_yaml_path = exam_yaml
        if not exam_yaml_path.is_file():
            raise FileNotFoundError(f"run_ingest: --exam-yaml file missing: {exam_yaml_path}.")

    def _track(file_repr: str, stage: str, exc: Exception) -> None:
        if isinstance(exc, ValidationError):
            for error in exc.errors():
                loc = ".".join(str(part) for part in error["loc"])
                violations.append(
                    IngestViolation(
                        file_path=file_repr,
                        row_or_item_id=None,
                        column_or_field=loc,
                        expected=error.get("msg", "valid value"),
                        found=error.get("input"),
                    )
                )
        else:
            violations.append(
                IngestViolation(
                    file_path=file_repr,
                    row_or_item_id=None,
                    column_or_field=stage,
                    expected="successful parse / validation",
                    found=str(exc),
                )
            )

    used_paths = {diag_csv_path, attendance_path, exam_yaml_path}
    used_paths.update(exam_dir.glob("*.xls"))
    used_paths.update(exam_dir.glob("*.xlsx"))
    unrecognized_files = _walk_unrecognized(bronze_dir, used_paths)

    _print(verbose_stream, f"      Diagnostic CSV: {diag_csv_path.relative_to(bronze_dir)}")
    _print(verbose_stream, f"      Attendance:     {attendance_path.relative_to(bronze_dir)}")
    _print(verbose_stream, f"      Exam YAML:      {exam_yaml_path.relative_to(bronze_dir)}")
    if unrecognized_files:
        _print(
            verbose_stream,
            f"      Unrecognized: {len(unrecognized_files)} file(s) recorded in manifest.",
        )

    # === [2/7] Mapping ===
    _print(verbose_stream, f"[2/7] Loading mapping {mapping_path} ...")
    mapping: DiagnosticMappingConfig | None = None
    try:
        mapping = load_mapping(mapping_path)
    except (ValidationError, ValueError) as exc:
        _track(str(mapping_path), "load_mapping", exc)

    semester: SemesterCode = mapping.metadata.semester if mapping is not None else "1900-1"
    course_slug: CourseSlug = mapping.metadata.course_slug if mapping is not None else "unknown"
    course_name_kr = mapping.metadata.course_name_kr if mapping is not None else None
    derived_output_key: OutputKey = (
        output_key if output_key is not None else f"{semester}-{course_slug}"
    )
    if mapping is not None:
        _print(
            verbose_stream,
            f"      mapping_version={mapping.metadata.mapping_version}, "
            f"axes.required={mapping.axes.required}",
        )

    # === [3/7] Diagnostic CSV ===
    _print(verbose_stream, f"[3/7] Parsing diagnostic CSV {diag_csv_path.name} ...")
    diagnostic_df: pd.DataFrame = pd.DataFrame()
    diagnostic_encoding: Literal["utf-8", "cp949"] = "utf-8"
    if mapping is not None:
        try:
            diagnostic_df, diagnostic_encoding = parse_diagnostic_csv(diag_csv_path, mapping)
            _print(
                verbose_stream,
                f"      rows={len(diagnostic_df)}, columns={len(diagnostic_df.columns)}, "
                f"encoding={diagnostic_encoding}",
            )
        except DuplicateStudentIdError as exc:
            raise DataIntegrityError(
                violations=[_data_integrity_violation(str(diag_csv_path), exc)]
            ) from exc
        except (ValueError, ValidationError) as exc:
            _track(str(diag_csv_path), "parse_diagnostic_csv", exc)

    # === [4/7] Exam OMR ===
    _print(verbose_stream, "[4/7] Parsing exam OMR XLS (4 sections × 4 sheets) ...")
    if exam_result_pattern is not None:
        # A7 audit trail: warn the operator that the default exclude-tokens
        # safety net no longer applies. ValueError-on-bad-glob is caught
        # earlier in the CLI; this is the *information* path.
        print(
            f"WARN: --exam-result-pattern override active "
            f"({exam_result_pattern!r}); default exclude tokens "
            f"{sorted(DEFAULT_RESULT_EXCLUDE_TOKENS)} disabled.",
            file=sys.stderr,
        )
    exam_responses_df: pd.DataFrame = pd.DataFrame()
    exam_summary_df: pd.DataFrame = pd.DataFrame()
    try:
        exam_responses_df, exam_summary_df, _items_df = parse_exam_omr_xls(
            exam_dir,
            exam_result_pattern=exam_result_pattern,
            exam_absent_pattern=exam_absent_pattern,
        )
        _print(
            verbose_stream,
            f"      responses={len(exam_responses_df)}, students_in_summary={len(exam_summary_df)}",
        )
    except DuplicateStudentIdError as exc:
        raise DataIntegrityError(
            violations=[_data_integrity_violation(str(exam_dir), exc)]
        ) from exc
    except (ValueError, ValidationError) as exc:
        _track(str(exam_dir), "parse_exam_omr_xls", exc)

    # === [5/7] Attendance ===
    _print(verbose_stream, f"[5/7] Parsing attendance {attendance_path.name} ...")
    attendance_df: pd.DataFrame = pd.DataFrame(
        columns=[
            "student_id",
            "name_kr",
            "attendance_present_count",
            "attendance_absent_count",
            "attendance_late_count",
            "attendance_excused_count",
        ]
    )
    try:
        attendance_df = parse_attendance_xlsx(attendance_path)
        _print(verbose_stream, f"      rows={len(attendance_df)}")
    except DuplicateStudentIdError as exc:
        raise DataIntegrityError(
            violations=[_data_integrity_violation(str(attendance_path), exc)]
        ) from exc
    except (ValueError, ValidationError) as exc:
        _track(str(attendance_path), "parse_attendance_xlsx", exc)

    # Exam YAML
    exam_items: list = []
    try:
        exam_items = parse_exam_yaml(exam_yaml_path, semester, course_slug)
    except (ValueError, ValidationError) as exc:
        _track(str(exam_yaml_path), "parse_exam_yaml", exc)

    # Stop and report if any of the upstream stages collected violations.
    if violations:
        raise IngestValidationError(violations=violations)

    # Cross-reference: OMR item count vs exam YAML item count
    if not exam_responses_df.empty and exam_items:
        omr_items = sorted({int(no) for no in exam_responses_df["item_no"].unique()})
        yaml_items = sorted({item.item_no for item in exam_items})
        if omr_items != yaml_items:
            violations.append(
                IngestViolation(
                    file_path=f"{exam_dir} | {exam_yaml_path}",
                    row_or_item_id=None,
                    column_or_field="item_no coverage",
                    expected=f"OMR item_nos {yaml_items}",
                    found=f"OMR item_nos {omr_items}",
                )
            )
            raise IngestValidationError(violations=violations)

    if mapping is None:
        # Defensive: should already have raised above.
        raise IngestValidationError(violations=violations)

    # === [6/7] Combine + apply mapping + validate ===
    _print(verbose_stream, "[6/7] Combining sources and validating outputs ...")
    try:
        axis_scores, diagnostic_responses, multiselect_new = apply_mapping(
            diagnostic_df, mapping, semester, course_slug
        )
    except (ValueError, ValidationError) as exc:
        _track(str(diag_csv_path), "apply_mapping", exc)
        raise IngestValidationError(violations=violations) from exc

    try:
        student_masters, exam_results = combine_sources(
            diagnostic_df=diagnostic_df,
            exam_responses_df=_attach_section_to_responses(exam_responses_df, exam_summary_df),
            exam_summary_df=exam_summary_df,
            attendance_df=attendance_df,
            axis_scores_by_student=axis_scores,
            items=exam_items,
            semester=semester,
            course_slug=course_slug,
        )
    except (ValueError, ValidationError) as exc:
        _track("<combine>", "combine_sources", exc)
        raise IngestValidationError(violations=violations) from exc

    try:
        validate_outputs(student_masters, diagnostic_responses, exam_results, exam_items)
    except DataIntegrityError:
        # Already an aggregate, exit code 4 — re-raise unchanged.
        raise
    except (ValueError, ValidationError) as exc:
        _track("<cross-validate>", "validate_outputs", exc)
        raise IngestValidationError(violations=violations) from exc

    _print(
        verbose_stream,
        f"      master_rows={len(student_masters)}, "
        f"on_roster={sum(1 for m in student_masters if m.on_roster)}, "
        f"off_roster={sum(1 for m in student_masters if not m.on_roster)}",
    )

    # === [7/7] Write Silver ===
    parent = output_dir if output_dir is not None else (bronze_dir.parent / "silver" / "immersio")
    silver_dir = parent / derived_output_key

    repo_root = _find_repo_root(bronze_dir)
    git_commit = None if no_git_commit else _git_commit_or_none(repo_root)

    inputs: list[IngestInput] = [
        IngestInput(
            role="diagnostic_csv",
            path=str(_relative_or_abs(diag_csv_path, repo_root)),
            sha256=sha256_file(diag_csv_path),
            encoding=diagnostic_encoding,
        ),
        IngestInput(
            role="exam_omr_xls",
            path=str(_relative_or_abs(exam_dir, repo_root)),
            sha256=_sha256_dir_concat(exam_dir),
        ),
        IngestInput(
            role="attendance_xlsx",
            path=str(_relative_or_abs(attendance_path, repo_root)),
            sha256=sha256_file(attendance_path),
        ),
        IngestInput(
            role="exam_yaml",
            path=str(_relative_or_abs(exam_yaml_path, repo_root)),
            sha256=sha256_file(exam_yaml_path),
            encoding="utf-8",
        ),
        IngestInput(
            role="diagnostic_mapping_yaml",
            path=str(_relative_or_abs(mapping_path, repo_root)),
            sha256=sha256_file(mapping_path),
            encoding="utf-8",
        ),
    ]

    if exam_result_pattern is not None:
        exclude_tokens_applied: list[str] = []  # operator override disables defaults
    else:
        exclude_tokens_applied = sorted(DEFAULT_RESULT_EXCLUDE_TOKENS)

    manifest = IngestManifest(
        output_key=derived_output_key,
        semester=semester,
        course_slug=course_slug,
        course_name_kr=course_name_kr,
        paideia_shared_version=_safe_version("paideia-shared"),
        immersio_version=_safe_version("immersio"),
        mapping_version=mapping.metadata.mapping_version,
        inputs=inputs,
        unrecognized_files=unrecognized_files,
        multiselect_new_options=multiselect_new,
        row_counts=IngestRowCount(
            student_master=len(student_masters),
            diagnostic_response=len(diagnostic_responses),
            exam_result=len(exam_results),
            exam_item=len(exam_items),
        ),
        created_at=datetime.now(tz=UTC),
        git_commit=git_commit,
        exam_result_pattern_used=exam_result_pattern,
        exclude_tokens_applied=exclude_tokens_applied,
    )

    _print(verbose_stream, f"[7/7] Writing Silver to {silver_dir} ...")
    write_silver(
        silver_dir,
        student_masters,
        diagnostic_responses,
        exam_results,
        exam_items,
        manifest,
    )
    _print(verbose_stream, "Completed.")
    return manifest


def _attach_section_to_responses(
    exam_responses_df: pd.DataFrame, exam_summary_df: pd.DataFrame
) -> pd.DataFrame:
    """Carry over the per-student section already present in the OMR responses DF.

    The exam_omr parser already injects the section column, so this helper is a
    forward-compatible noop that future refactors can override.
    """
    return exam_responses_df


def _find_repo_root(start: Path) -> Path:
    here = start.resolve()
    while True:
        if (here / ".git").exists():
            return here
        if here.parent == here:
            return start
        here = here.parent


def _relative_or_abs(path: Path, repo_root: Path) -> Path:
    try:
        return path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return path.resolve()


def _sha256_dir_concat(dir_path: Path) -> str:
    """SHA-256 over the concatenation of every regular file under dir (sorted).

    AV-4b hardening: walks without following symlinks and explicitly skips
    every symlinked entry so attacker-planted links cannot smuggle external
    bytes into the manifest's input hash.
    """
    import hashlib
    import os

    digest = hashlib.sha256()
    entries: list[Path] = []
    for current_dir, subdirs, filenames in os.walk(dir_path, followlinks=False):
        subdirs[:] = [d for d in subdirs if not Path(current_dir, d).is_symlink()]
        for filename in filenames:
            entry = Path(current_dir, filename)
            if entry.is_symlink():
                continue
            entries.append(entry)
    for entry in sorted(entries):
        if entry.is_file():
            digest.update(entry.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(entry.read_bytes())
    return digest.hexdigest()
