"""maieutica CLI entry point — stub (T003).

Full subcommands (ingest|plan|dry-run|generate|verify|build) added in T012.
Entry point: ``maieutica = "maieutica.cli.main:app"``
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maieutica",
        description=(
            "maieutica — 교재 기반 주차별 퀴즈·형성평가 후보 생성 파이프라인 (paideia 모듈)\n"
            "\n"
            "Subcommands: ingest | plan | dry-run | generate | verify | build\n"
            "(not yet implemented — run T012 to wire subcommands)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    return parser


def app(argv: list[str] | None = None) -> int:
    """Entry point for the ``maieutica`` console script.

    Args:
        argv: Optional override for ``sys.argv[1:]``.  When ``None`` argparse
            reads ``sys.argv[1:]`` directly; passing ``[]`` triggers help output.

    Returns:
        Integer exit code.
    """
    parser = _build_parser()
    # No subcommands yet — print help and exit 0 for any invocation.
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
