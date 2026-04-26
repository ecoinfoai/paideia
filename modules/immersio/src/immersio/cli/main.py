"""immersio CLI entry point.

Usage:
    immersio ingest --bronze-dir PATH --mapping PATH [--exam-yaml PATH]
                    [--output-key STRING] [--output-dir PATH]
                    [--no-git-commit] [--quiet | --verbose]

Exit codes (per contracts/cli.md):
    0 — Success
    1 — Input validation failure (Silver outputs not written)
    2 — Missing inputs / argument error
    3 — Output directory permission or system error
    4 — Data integrity violation (e.g. duplicate student_id)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import IO

from pydantic import ValidationError

from ..ingest import DataIntegrityError, IngestValidationError, run_ingest


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
    verbosity = ingest.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", action="store_true")
    verbosity.add_argument("--verbose", action="store_true")

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
            run_ingest(
                bronze_dir=args.bronze_dir,
                mapping_path=args.mapping,
                exam_yaml=args.exam_yaml,
                output_key=args.output_key,
                output_dir=args.output_dir,
                no_git_commit=args.no_git_commit,
                verbose_stream=_resolve_stream(args),
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

    parser.error(f"unknown command: {args.command}")
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
