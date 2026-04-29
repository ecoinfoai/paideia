"""CLI entry for ``paideia immersio combine`` (T047, US5).

INTEGRATION (RULE 4): cli wire-in adds first non-pipeline orchestrator
that calls ``run_us1_pipeline``. Wraps it with FR-024 exit-code mapping
+ FR-026 stderr format. Subcommand registration in ``cli/main.py`` is
T048.

Exit codes (FR-024):
- 0  Success
- 1  Input validation failure (semester/course regex / required argv)
- 2  Pydantic ValidationError on silver inputs
- 3  Required input file missing
- 4  Archival failure
- 5  Schema version mismatch (needs-map / Phase 2)
- 6  NanumGothic font missing
- 99 Internal error (unexpected exception)

stderr format (FR-026): ``ERROR [combine.<phase>]: <category> — <message>``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from immersio.fonts import KoreanFontUnavailableError, resolve_korean_font_paths

from .manifest import SchemaVersionMismatch
from .pipeline import run_us1_pipeline

EXIT_OK = 0
EXIT_INPUT_VALIDATION = 1
EXIT_PYDANTIC_VALIDATION = 2
EXIT_INPUT_FILE_MISSING = 3
EXIT_ARCHIVAL_FAILURE = 4
EXIT_SCHEMA_MISMATCH = 5
EXIT_FONT_MISSING = 6
EXIT_INTERNAL = 99

_SEMESTER_RE = re.compile(r"^\d{4}-[12SW]$")
_COURSE_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")


def _stderr(phase: str, category: str, message: str) -> None:
    print(f"ERROR [combine.{phase}]: {category} — {message}", file=sys.stderr)


def _required_silver_inputs(
    *, silver_dir: Path, semester: str, course_slug: str
) -> list[Path]:
    """Return the 8 silver inputs the pipeline needs (cli_combine.md
    Resolved input paths)."""
    nm = silver_dir / "needs-map" / f"{semester}-{course_slug}"
    im = silver_dir / "immersio" / f"{semester}-{course_slug}"
    return [
        nm / "factor_scores.parquet",
        nm / "cluster_assignment.parquet",
        nm / "cluster_names.json",
        nm / "manifest.json",
        im / "student_master.parquet",
        im / "diagnostic_response.parquet",
        im / "학생지표.parquet",
        im / "manifest.json",
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paideia immersio combine",
        description="needs-map × exam combined-analysis Phase 3 pipeline.",
    )
    parser.add_argument(
        "--semester",
        required=True,
        help="Academic semester code (e.g. '2026-1').",
    )
    parser.add_argument(
        "--course",
        required=True,
        help="Course slug (e.g. 'anatomy').",
    )
    parser.add_argument(
        "--silver-dir",
        required=True,
        type=Path,
        help="Silver root directory (no default — silent skip 차단).",
    )
    parser.add_argument(
        "--gold-dir",
        required=True,
        type=Path,
        help="Gold root directory (no default — silent skip 차단).",
    )
    parser.add_argument(
        "--include-cluster",
        action="store_true",
        help="Enable US2 wiring (cluster_compare → fig5 → §4 → sheet 3).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit per-phase progress to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the combine CLI; return FR-024 exit code.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``). Tests pass
            an explicit list.

    Returns:
        Exit code (0 on success, 1-6/99 per FR-024).
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on missing required args; map to our exit 1
        # (input validation). Tests catch SystemExit so we re-raise with
        # the mapped code.
        return EXIT_INPUT_VALIDATION if exc.code != 0 else EXIT_OK

    # Argument regex validation.
    if not _SEMESTER_RE.match(args.semester):
        _stderr(
            "input",
            "invalid-semester",
            f"--semester {args.semester!r} does not match {_SEMESTER_RE.pattern}",
        )
        return EXIT_INPUT_VALIDATION
    if not _COURSE_RE.match(args.course):
        _stderr(
            "input",
            "invalid-course",
            f"--course {args.course!r} does not match {_COURSE_RE.pattern}",
        )
        return EXIT_INPUT_VALIDATION

    # Font check (FR-023, exit 6 trigger).
    try:
        resolve_korean_font_paths()
    except KoreanFontUnavailableError as exc:
        _stderr(
            "font",
            "korean-font-unavailable",
            f"NanumGothic not resolvable. {exc}",
        )
        return EXIT_FONT_MISSING

    # Required input file existence (FR-024 exit 3).
    missing: list[Path] = [
        p
        for p in _required_silver_inputs(
            silver_dir=args.silver_dir,
            semester=args.semester,
            course_slug=args.course,
        )
        if not p.exists()
    ]
    if missing:
        first = missing[0]
        _stderr(
            "input",
            "missing-file",
            f"required input not found: {first}. "
            f"Run upstream pipelines (needs-map / immersio Phase 2) first.",
        )
        return EXIT_INPUT_FILE_MISSING

    # Pipeline dispatch.
    try:
        return run_us1_pipeline(
            semester=args.semester,
            course_slug=args.course,
            silver_dir=args.silver_dir,
            gold_dir=args.gold_dir,
            include_cluster=args.include_cluster,
        )
    except SchemaVersionMismatch as exc:
        _stderr("schema", "version-mismatch", str(exc))
        return EXIT_SCHEMA_MISMATCH
    except ValidationError as exc:
        _stderr("schema", "pydantic-validation", str(exc))
        return EXIT_PYDANTIC_VALIDATION
    except FileNotFoundError as exc:
        _stderr("input", "missing-file", str(exc))
        return EXIT_INPUT_FILE_MISSING
    except KoreanFontUnavailableError as exc:
        _stderr("font", "korean-font-unavailable", str(exc))
        return EXIT_FONT_MISSING
    except OSError as exc:
        _stderr("archival", "io-error", str(exc))
        return EXIT_ARCHIVAL_FAILURE
    except Exception as exc:  # noqa: BLE001
        _stderr("internal", type(exc).__name__, str(exc))
        return EXIT_INTERNAL


__all__ = [
    "main",
    "EXIT_OK",
    "EXIT_INPUT_VALIDATION",
    "EXIT_PYDANTIC_VALIDATION",
    "EXIT_INPUT_FILE_MISSING",
    "EXIT_ARCHIVAL_FAILURE",
    "EXIT_SCHEMA_MISMATCH",
    "EXIT_FONT_MISSING",
    "EXIT_INTERNAL",
]
