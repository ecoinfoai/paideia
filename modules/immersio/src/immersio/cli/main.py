"""immersio CLI entry point.

Usage:
    immersio ingest --bronze-dir PATH --mapping PATH [--exam-yaml PATH]
                    [--output-key STRING] [--output-dir PATH]
                    [--no-git-commit] [--quiet | --verbose]
                    [--exam-result-pattern GLOB] [--exam-absent-pattern GLOB]

Exit codes (per contracts/cli.md):
    0 — Success
    1 — Input validation failure (Silver outputs not written)
    2 — Missing inputs / argument error
    3 — Output directory permission or system error
    4 — Data integrity violation (e.g. duplicate student_id)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import IO

from pydantic import ValidationError

from ..analyze.archival import ArchivalError, archive_previous_run
from ..analyze.pipeline import (
    PipelineArgs,
    SilverNotFoundError,
    run_immersio_phase1,
)
from ..fonts import KoreanFontUnavailableError
from ..ingest import DataIntegrityError, IngestValidationError, run_ingest

_SEMESTER_PATTERN = re.compile(r"^\d{4}-[12SW]$")
_COURSE_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_ISO8601_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_OUTPUT_KEY_PATTERN = re.compile(r"^\d{4}-[12SW]-[a-z][a-z0-9-]{1,39}$")

_MAX_GLOB_PATTERN_LEN = 1024


def _validate_glob_pattern(label: str, value: str | None) -> None:
    """Reject CLI glob-pattern flags that could escape ``bronze_dir`` or DoS.

    Closure of adversary AV-A1 (``..`` segment escape), AV-A3 (NUL/control
    bytes), AV-A6 (absolute path), AV-A8 (oversized). Called from
    ``_validate_paths`` for ``--exam-result-pattern`` / ``--exam-absent-pattern``.

    Args:
        label: Human-readable flag name (e.g. ``"--exam-result-pattern"``)
            included in every error message so operators know which input
            to fix.
        value: The flag value or ``None``.

    Raises:
        ValueError: For any structural rejection. Caller maps to exit 2.
    """
    if value is None:
        return
    if value == "":
        raise ValueError(f"{label} is empty (provide a glob or omit the flag)")
    if "\x00" in value:
        raise ValueError(f"{label} contains NUL byte")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{label} contains control bytes")
    if len(value) > _MAX_GLOB_PATTERN_LEN:
        raise ValueError(
            f"{label} exceeds max length ({len(value)} > {_MAX_GLOB_PATTERN_LEN})"
        )
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError(
            f"{label} must not be an absolute path "
            f"(use a relative glob anchored under bronze_dir/시험성적)"
        )
    parts = re.split(r"[\\/]", value)
    if any(part == ".." for part in parts):
        raise ValueError(
            f"{label} must not contain '..' parent-segment (escape blocked)"
        )


def _validate_paths(
    *,
    bronze_dir: Path,
    mapping: Path,
    exam_yaml: Path | None,
    output_dir: Path | None,
    output_key: str | None,
    exam_result_pattern: str | None = None,
    exam_absent_pattern: str | None = None,
) -> None:
    """Reject path traversal, symlink escape, NUL/control bytes, and ancestor coupling.

    Closure of adversary AV-3 (path traversal). Called from ``app()`` before
    ``run_ingest`` so structural rejections raise as ValueError → exit code 2.

    Args:
        bronze_dir: --bronze-dir argument.
        mapping: --mapping argument.
        exam_yaml: --exam-yaml argument or None.
        output_dir: --output-dir argument or None.
        output_key: --output-key argument or None.

    Raises:
        ValueError: For any structural rejection (NUL/control bytes, symlinked
            inputs, output coupled to bronze, device files, malformed output_key).
        FileNotFoundError: If bronze_dir / mapping / exam_yaml does not exist.
    """
    if output_key is not None:
        if "\x00" in output_key:
            raise ValueError("output_key contains NUL byte")
        if any(ord(c) < 32 or ord(c) == 127 for c in output_key):
            raise ValueError("output_key contains control bytes")
        if not _OUTPUT_KEY_PATTERN.fullmatch(output_key):
            raise ValueError(
                f"output_key '{output_key}' does not match required pattern "
                f"'{{YYYY}}-[12SW]-{{course-slug}}'"
            )

    _validate_glob_pattern("--exam-result-pattern", exam_result_pattern)
    _validate_glob_pattern("--exam-absent-pattern", exam_absent_pattern)

    bronze_real = bronze_dir.resolve(strict=True)
    if not bronze_real.is_dir():
        raise ValueError(f"bronze_dir ({bronze_real}) is not a directory")
    if bronze_dir.is_symlink():
        raise ValueError(f"bronze_dir ({bronze_dir}) must not be a symlink")

    for label, path in (("mapping", mapping), ("exam_yaml", exam_yaml)):
        if path is None:
            continue
        if path.is_symlink():
            raise ValueError(f"{label} ({path}) must not be a symlink")
        real = path.resolve(strict=True)
        if not real.is_file():
            raise ValueError(f"{label} ({real}) is not a regular file")

    if output_dir is not None:
        output_real = output_dir.resolve()
        try:
            output_real.relative_to(bronze_real)
        except ValueError:
            return
        raise ValueError(
            f"output_dir ({output_real}) cannot be inside bronze_dir ({bronze_real})"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="immersio", description="immersio ingest CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Run Phase 0 Bronze→Silver ingest")
    ingest.add_argument("--bronze-dir", required=True, type=Path)
    ingest.add_argument("--mapping", required=True, type=Path)
    ingest.add_argument("--exam-yaml", type=Path, default=None)
    ingest.add_argument("--output-key", type=str, default=None)
    ingest.add_argument("--output-dir", type=Path, default=None)
    ingest.add_argument("--no-git-commit", action="store_true")
    ingest.add_argument(
        "--exam-result-pattern",
        type=str,
        default=None,
        help=(
            "Override glob for the per-section main result workbook (FR-029). "
            "Passed to parse_exam_omr_xls. When set, the default exclude tokens "
            "((OX), (문항분석), 결시) no longer apply."
        ),
    )
    ingest.add_argument(
        "--exam-absent-pattern",
        type=str,
        default=None,
        help=(
            "Override glob for the per-section absent workbook (FR-029). "
            "Reserved passthrough — currently absent rows are read from the "
            "결시 sheet inside the main result workbook."
        ),
    )
    verbosity = ingest.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", action="store_true")
    verbosity.add_argument("--verbose", action="store_true")

    analyze = sub.add_parser("analyze", help="Run Phase 1+2 analysis pipeline")
    analyze.add_argument("--semester", required=True, type=str)
    analyze.add_argument("--course", required=True, type=str)
    analyze.add_argument("--bronze-dir", type=Path, default=Path("data/bronze"))
    analyze.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    analyze.add_argument("--gold-dir", type=Path, default=Path("data/gold"))
    analyze.add_argument(
        "--legacy-xlsx",
        type=Path,
        default=Path("data/silver/legacy/중간고사_분석결과.xlsx"),
    )
    analyze.add_argument("--exam-result-pattern", type=str, default=None)
    analyze.add_argument("--exam-absent-pattern", type=str, default=None)
    analyze.add_argument("--created-at-utc", type=str, default=None)
    analyze.add_argument("--seed", type=int, default=42)
    analyze.add_argument("--no-needs-map", action="store_true")
    a_verbosity = analyze.add_mutually_exclusive_group()
    a_verbosity.add_argument("--quiet", action="store_true")
    a_verbosity.add_argument("--verbose", action="store_true")

    # T048 — Phase 3 combine subcommand (INTEGRATION RULE 4).
    combine = sub.add_parser(
        "combine",
        help="Run Phase 3 needs-map × exam combined-analysis pipeline",
    )
    combine.add_argument("--semester", required=True, type=str)
    combine.add_argument("--course", required=True, type=str)
    combine.add_argument("--silver-dir", required=True, type=Path)
    combine.add_argument("--gold-dir", required=True, type=Path)
    combine.add_argument("--include-cluster", action="store_true")
    combine.add_argument("--include-subgroup", action="store_true")
    combine.add_argument("--verbose", action="store_true")

    # T030 — spec 006 immersio-email subparser (Foundational stub).
    # Body wiring lands in T049/T057/T073/T080/T083/T100l per phase.
    email_p = sub.add_parser(
        "email",
        help="Send per-student PDF reports (spec 006 immersio-email v0.1.0)",
    )
    email_p.add_argument("--profile", required=True, type=str)
    email_p.add_argument("--semester", required=True, type=str)
    email_p.add_argument("--course", required=True, type=str)
    email_p.add_argument("--exam-name", required=True, type=str)
    email_p.add_argument("--sent-date", type=str, default=None)
    email_p.add_argument("--send", action="store_true")
    email_p.add_argument(
        "--self-test",
        type=int,
        default=None,
        help=(
            "본인 메일함으로만 발송, 학생 메일함 도달 0 — N 명을 본인에게 "
            "test_dummy 로 미리 발송 (FR-C01b · v0.1.1)"
        ),
    )
    retry_group = email_p.add_mutually_exclusive_group()
    retry_group.add_argument("--retry-failed", action="store_true")
    retry_group.add_argument("--retry-skipped", action="store_true")
    email_p.add_argument("--rate-per-min", type=int, default=None)
    email_p.add_argument(
        "--cohort",
        type=str,
        choices=("low_score", "rest", "all"),
        default="all",
    )
    email_p.add_argument("--confirm-sample", type=int, default=None)
    email_p.add_argument("--bronze-csv", type=Path, default=None)
    email_p.add_argument("--gold-pdf-dir", type=Path, default=None)
    email_p.add_argument("--silver-master", type=Path, default=None)
    email_p.add_argument("--silver-student-metrics", type=Path, default=None)
    email_p.add_argument(
        "--created-at-utc",
        type=str,
        default=None,
        help=(
            "UTC timestamp override (YYYY-MM-DDTHH:MM:SSZ) for manifest "
            "started_at/completed_at — pins re-runs to a fixed timestamp "
            "for byte-identical manifest output (M3 advisory)."
        ),
    )
    e_verbosity = email_p.add_mutually_exclusive_group()
    e_verbosity.add_argument("--quiet", action="store_true")
    e_verbosity.add_argument("--verbose", action="store_true")

    # T088 — Polish init-test-fixtures helper (TestProfile dummy PDFs).
    init_p = sub.add_parser(
        "email-init-test-fixtures",
        help="Generate dummy PDFs into TestProfile.dummy_fixture_dir (spec 006 T088)",
    )
    init_p.add_argument("--profile", required=True, type=str)

    return parser


def _resolve_stream(args: argparse.Namespace) -> IO[str] | None:
    if args.verbose:
        return sys.stdout
    return None


def app(argv: list[str] | None = None) -> int:
    """Entry point for the ``immersio`` console script.

    Args:
        argv: Optional override for sys.argv[1:].

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        try:
            _validate_paths(
                bronze_dir=args.bronze_dir,
                mapping=args.mapping,
                exam_yaml=args.exam_yaml,
                output_dir=args.output_dir,
                output_key=args.output_key,
                exam_result_pattern=args.exam_result_pattern,
                exam_absent_pattern=args.exam_absent_pattern,
            )
        except FileNotFoundError as exc:
            print(f"ERROR: missing input — {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"ERROR: invalid argument — {exc}", file=sys.stderr)
            return 2

        try:
            run_ingest(
                bronze_dir=args.bronze_dir,
                mapping_path=args.mapping,
                exam_yaml=args.exam_yaml,
                output_key=args.output_key,
                output_dir=args.output_dir,
                no_git_commit=args.no_git_commit,
                verbose_stream=_resolve_stream(args),
                exam_result_pattern=args.exam_result_pattern,
                exam_absent_pattern=args.exam_absent_pattern,
            )
        except DataIntegrityError as exc:
            # contracts/cli.md exit code 4: post-normalization data integrity.
            print(str(exc), file=sys.stderr)
            return 4
        except IngestValidationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except FileNotFoundError as exc:
            print(f"ERROR: missing input — {exc}", file=sys.stderr)
            return 2
        except ValidationError as exc:
            print("ERROR: schema validation failed.", file=sys.stderr)
            for error in exc.errors():
                loc = ".".join(str(part) for part in error["loc"])
                print(f"  - {loc}: {error['msg']}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except PermissionError as exc:
            print(f"ERROR: output permission — {exc}", file=sys.stderr)
            return 3
        except OSError as exc:
            # Generic system errors (ENOSPC, EROFS, EIO, ...) per qa-engineer note.
            print(f"ERROR: system I/O — {exc}", file=sys.stderr)
            return 3
        return 0

    if args.command == "analyze":
        return _run_analyze(args)

    if args.command == "email":
        # Foundational stub (T030). Actual orchestration wires in via
        # T049 (US1 dry-run), T057 (US2 self-test), T073 (US3 send).
        # FR-F03: validate semester / course / exam-name format at CLI entry
        # (mirror of `analyze` pattern at L430-444). Without this guard,
        # malformed --semester values surface as Phase B "directory not
        # found" with a misleading error message (post-release smoke).
        if not _SEMESTER_PATTERN.match(args.semester):
            print(
                f"ERROR [immersio email]: invalid_semester — "
                f"--semester must match YYYY-N (1/2/S/W), got {args.semester!r}",
                file=sys.stderr,
            )
            return 1
        if not _COURSE_SLUG_PATTERN.match(args.course):
            print(
                f"ERROR [immersio email]: invalid_course — "
                f"--course must match {_COURSE_SLUG_PATTERN.pattern}, "
                f"got {args.course!r}",
                file=sys.stderr,
            )
            return 1
        if not args.exam_name.strip():
            print(
                "ERROR [immersio email]: invalid_exam_name — "
                "--exam-name must be non-empty (FR-B04)",
                file=sys.stderr,
            )
            return 1

        from immersio.email.pipeline import run_email_dispatch

        return run_email_dispatch(args)

    if args.command == "email-init-test-fixtures":
        # T088 — generate dummy PDFs into TestProfile.dummy_fixture_dir.
        from immersio.email.dummy_fixture import generate_dummy_pdfs
        from immersio.email.profile import ProfileError, ProfileLoader
        from paideia_shared.schemas import TestProfile

        try:
            profile = ProfileLoader().load(args.profile)
        except ProfileError as exc:
            print(
                f"ERROR [immersio email-init-test-fixtures]: {exc}",
                file=sys.stderr,
            )
            return 1
        if not isinstance(profile, TestProfile):
            print(
                f"ERROR [immersio email-init-test-fixtures]: profile "
                f"{args.profile!r} is not a TestProfile (got "
                f"{profile.profile_kind}). This subcommand only works "
                f"with profile_kind: test.",
                file=sys.stderr,
            )
            return 1
        students = [(d.student_id, d.name_kr) for d in profile.dummy_students]
        from pathlib import Path as _Path

        written = generate_dummy_pdfs(
            _Path(str(profile.dummy_fixture_dir)), students
        )
        print(
            f"[immersio email-init-test-fixtures] wrote {len(written)} dummy "
            f"PDFs to {profile.dummy_fixture_dir}",
            file=sys.stdout,
        )
        return 0

    if args.command == "combine":
        # T048 — INTEGRATION (RULE 4). Delegate to combine.cli.main with
        # the dispatched argv slice; argparse already validated semester /
        # course / paths, so we re-shape into the combine subparser argv.
        from immersio.combine.cli import main as combine_main

        argv = [
            "--semester",
            args.semester,
            "--course",
            args.course,
            "--silver-dir",
            str(args.silver_dir),
            "--gold-dir",
            str(args.gold_dir),
        ]
        if args.include_cluster:
            argv.append("--include-cluster")
        if args.include_subgroup:
            argv.append("--include-subgroup")
        if args.verbose:
            argv.append("--verbose")
        return combine_main(argv)

    parser.error(f"unknown command: {args.command}")
    return 2  # pragma: no cover


def _run_analyze(args: argparse.Namespace) -> int:
    """Drive the Phase 1+2 analysis orchestrator end-to-end.

    Maps every fail-fast exception to the contracts/cli.md exit code
    table (FR-033). archival of the previous run happens *before*
    ``run_immersio_phase1`` writes new outputs so the canonical paths
    are empty when the pipeline starts (Constitution V '부분 산출 금지').
    """
    if not _SEMESTER_PATTERN.match(args.semester):
        print(
            f"ERROR [immersio analyze]: invalid_semester — "
            f"--semester must match YYYY-N (1/2/S/W), got {args.semester!r}",
            file=sys.stderr,
        )
        return 1
    if not _COURSE_SLUG_PATTERN.match(args.course):
        print(
            f"ERROR [immersio analyze]: invalid_course — "
            f"--course must be kebab-case slug, got {args.course!r}",
            file=sys.stderr,
        )
        return 1
    if args.created_at_utc is not None:
        # Two-tier validation per adversary P7: regex shape + datetime
        # semantic check. The regex catches gross typos (missing seconds,
        # missing 'T', etc.); fromisoformat rejects out-of-range fields
        # (e.g. 2026-13-99T...). Anti-pattern blocked: silent UTC offset
        # rewrite — we accept ONLY the trailing 'Z' form.
        if not _ISO8601_PATTERN.match(args.created_at_utc):
            print(
                f"ERROR [immersio analyze]: invalid_created_at_utc — "
                f"--created-at-utc must be ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ), "
                f"got {args.created_at_utc!r}",
                file=sys.stderr,
            )
            return 1
        try:
            import datetime as _dt
            _dt.datetime.fromisoformat(args.created_at_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            print(
                f"ERROR [immersio analyze]: invalid_created_at_utc — "
                f"calendar fields out of range: {args.created_at_utc!r} "
                f"({exc})",
                file=sys.stderr,
            )
            return 1

    legacy_xlsx = args.legacy_xlsx
    if legacy_xlsx is not None and not legacy_xlsx.is_file():
        # Soft path — the orchestrator will record a manifest note instead
        # of failing. Operator can pass /dev/null to suppress entirely.
        legacy_xlsx = None

    silver_root = args.silver_dir.resolve()
    gold_root = args.gold_dir.resolve()
    silver_dir = silver_root / "immersio" / f"{args.semester}-{args.course}"
    gold_dir = gold_root / "immersio" / f"{args.semester}-{args.course}"

    # Archival of any prior run BEFORE new outputs land. silver_dir holds
    # both Phase 0 ingest inputs (student_master.parquet etc., persistent)
    # and the analyze pipeline's own mirrors (학생지표.parquet,
    # manifest.json, rotating). Whitelist the rotating set so ingest
    # inputs stay in place across re-runs.
    silver_whitelist = frozenset({"학생지표.parquet", "manifest.json"})
    try:
        archive_previous_run(
            silver_dir=silver_dir,
            gold_dir=gold_dir,
            silver_whitelist=silver_whitelist,
        )
    except ArchivalError as exc:
        print(f"ERROR [immersio analyze]: archival — {exc}", file=sys.stderr)
        return 4

    pipeline_args = PipelineArgs(
        semester=args.semester,
        course_slug=args.course,
        bronze_dir=args.bronze_dir,
        silver_root=silver_root,
        gold_root=gold_root,
        legacy_xlsx=legacy_xlsx,
        created_at_utc_override=args.created_at_utc,
        seed=args.seed,
        no_needs_map=args.no_needs_map,
        verbose_stream=_resolve_stream(args),
    )

    try:
        return run_immersio_phase1(pipeline_args)
    except KoreanFontUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 6
    except SilverNotFoundError as exc:
        print(f"ERROR [immersio analyze]: file_missing — {exc}", file=sys.stderr)
        return 3
    except ValidationError as exc:
        print("ERROR [immersio analyze]: schema_validation", file=sys.stderr)
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            print(f"  - {loc}: {error['msg']}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR [immersio analyze]: file_missing — {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"ERROR [immersio analyze]: invalid_input — {exc}", file=sys.stderr)
        return 1
    except (PermissionError, OSError) as exc:
        print(f"ERROR [immersio analyze]: io — {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
