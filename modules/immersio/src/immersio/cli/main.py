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
import re
import sys
from pathlib import Path
from typing import IO

from pydantic import ValidationError

from ..ingest import DataIntegrityError, IngestValidationError, run_ingest

_OUTPUT_KEY_PATTERN = re.compile(r"^\d{4}-[12SW]-[a-z][a-z0-9-]{1,39}$")


def _validate_paths(
    *,
    bronze_dir: Path,
    mapping: Path,
    exam_yaml: Path | None,
    output_dir: Path | None,
    output_key: str | None,
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
            _validate_paths(
                bronze_dir=args.bronze_dir,
                mapping=args.mapping,
                exam_yaml=args.exam_yaml,
                output_dir=args.output_dir,
                output_key=args.output_key,
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
