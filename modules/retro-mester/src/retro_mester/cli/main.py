"""retro_mester CLI entry point.

Entry point: ``retro-mester = "retro_mester.cli.main:app"``

Subcommands
-----------
- ``run``   — execute the full retrospective analytics pipeline

Exit codes
----------
- 0 — success
- 2 — input / config error (missing files, bad config, invalid args)
- 3 — integrity error (data validation failure, pipeline integrity check)
- 5 — LLM required but unavailable (--require-llm set and LLM unreachable)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit-code constants
# ---------------------------------------------------------------------------

EXIT_SUCCESS: int = 0
EXIT_INPUT_ERROR: int = 2
EXIT_INTEGRITY_ERROR: int = 3
EXIT_LLM_REQUIRED_FAIL: int = 5


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with the ``run`` subcommand.

    Returns:
        Configured ``ArgumentParser`` ready to parse ``sys.argv[1:]``.
    """
    parser = argparse.ArgumentParser(
        prog="retro-mester",
        description=(
            "retro-mester — 학기 회고(retrospective) 분석 파이프라인 (paideia 모듈)\n"
            "\n"
            "Exit codes: 0 success · 2 input/config error · "
            "3 integrity error · 5 LLM-required fail"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------
    run_p = sub.add_parser(
        "run",
        help="Execute the retrospective analytics pipeline for a semester/course",
        description=(
            "Load source data, compute item statistics, identify gaps, analyse\n"
            "root causes, validate, align with prior year, prioritise actions,\n"
            "and emit forward recommendations."
        ),
    )
    run_p.add_argument(
        "--semester",
        required=True,
        type=str,
        metavar="SEMESTER",
        help="학기 코드 (예: '2026-1')",
    )
    run_p.add_argument(
        "--course",
        required=True,
        type=str,
        metavar="COURSE",
        help="과목 슬러그 (예: 'anatomy')",
    )
    run_p.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        metavar="DIR",
        help="Data root directory (default: data/)",
    )
    run_p.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Pipeline config YAML (default: <data-root>/bronze/retro-mester/<semester>-<course>/config.yaml)",
    )
    run_p.add_argument(
        "--prior-year",
        type=str,
        default=None,
        metavar="SEMESTER",
        help="Prior-year semester code for year-on-year alignment (e.g. '2025-1')",
    )
    run_p.add_argument(
        "--prior-yaml-path",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to a prior 차년도방향.yaml for forward-contract audit. "
            "When omitted, cold-start (no audit section emitted)."
        ),
    )
    run_p.add_argument(
        "--llm-mode",
        type=str,
        choices=("off", "subscription", "api"),
        default="off",
        metavar="{off,subscription,api}",
        help="LLM backend mode (default: off — no LLM calls)",
    )
    run_p.add_argument(
        "--require-llm",
        action="store_true",
        help=(
            "Fail with exit 5 if LLM is not reachable instead of degrading "
            "gracefully to non-LLM outputs"
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _run_handler(args: argparse.Namespace) -> int:
    """Handler for the ``run`` subcommand — delegates to ``run_retro``.

    Validates non-empty semester/course at the boundary, then calls the
    full retro-mester pipeline.

    Args:
        args: Parsed CLI namespace from argparse.

    Returns:
        Integer exit code (0 / 2 / 3 / 5).
    """
    # Validate semester/course non-empty (argparse ensures required, but guard
    # against whitespace-only values at the boundary).
    if not args.semester.strip():
        print(
            "ERROR [retro-mester]: --semester must be a non-empty string",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR
    if not args.course.strip():
        print(
            "ERROR [retro-mester]: --course must be a non-empty string",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    from retro_mester.pipeline import run_retro

    return run_retro(
        semester=args.semester,
        course=args.course,
        data_root=str(args.data_root),
        config_path=str(args.config) if args.config is not None else None,
        prior_year=args.prior_year,
        prior_yaml_path=str(args.prior_yaml_path) if args.prior_yaml_path is not None else None,
        llm_mode=args.llm_mode,
        require_llm=args.require_llm,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS = {
    "run": _run_handler,
}


def app(argv: list[str] | None = None) -> int:
    """Entry point for the ``retro-mester`` console script.

    Args:
        argv: Optional override for ``sys.argv[1:]``.  Useful for testing.

    Returns:
        Integer exit code (0 / 2 / 3 / 5).
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else EXIT_INPUT_ERROR

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:  # pragma: no cover
        parser.error(f"unknown command: {args.command}")
        return EXIT_INPUT_ERROR

    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
