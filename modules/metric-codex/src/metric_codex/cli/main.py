"""metric-codex CLI entry point — T020.

Entry point: ``metric-codex = "metric_codex.cli.main:app"``.

Subcommands (stubs — real logic wired in later units):
- ``ingest``    — Bronze→Silver: 성적·출석·immersio Silver·needs-map Silver 수집
- ``query``     — 지도교수 질의 응답 (retrieval + LLM 다듬기)
- ``dry-run``   — 결정론 단계만 실행, LLM 미호출 (헌장 I 검증)
- ``generate``  — CodexEntry 생성 (LLM: subscription | api | none(template))
- ``distribute``— 지도교수별 번들 배분 및 Gold 산출
- ``verify``    — CodexEntry 완결성·근거·PII 경계 검증
- ``build``     — 전체 파이프라인 (ingest→generate→verify→distribute→Gold)

Common options (all subcommands):
    --semester SEMESTER  (required) SemesterCode (e.g. "2026-1")
    --course COURSE      (required) CourseSlug (e.g. "anatomy")
    --data-root PATH     Data root directory (default: data/)

Exit codes:
    0 — Success
    2 — Input/configuration validation failure
    3 — Pipeline step failure
    4 — LLM backend unreachable (api mode only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Argument parser builder
# ---------------------------------------------------------------------------


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add shared options to a subcommand parser.

    All subcommands share --semester, --course, and --data-root.

    Args:
        parser: The subcommand parser to add arguments to.
    """
    parser.add_argument(
        "--semester",
        required=True,
        type=str,
        metavar="SEMESTER",
        help="학기 코드 (예: '2026-1')",
    )
    parser.add_argument(
        "--course",
        required=True,
        type=str,
        metavar="COURSE",
        help="과목 슬러그 (예: 'anatomy')",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        metavar="PATH",
        help="데이터 루트 디렉터리 (기본: data/)",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with all 7 subcommands.

    Returns:
        Configured ArgumentParser ready for parse_args().
    """
    parser = argparse.ArgumentParser(
        prog="metric-codex",
        description=(
            "metric-codex — 학생별 학습역량 누적 기록 + 지도교수 근거 기반 질의 (paideia 모듈)\n"
            "\n"
            "종료 코드: 0 성공 · 2 입력/설정 검증 실패 · "
            "3 파이프라인 단계 실패 · 4 LLM 백엔드 도달 실패(api 모드)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------
    # ingest
    # ------------------------------------------------------------------
    ingest_p = sub.add_parser(
        "ingest",
        help="Bronze→Silver: 성적·출석·immersio Silver·needs-map Silver 수집",
        description=(
            "Bronze 입력(성적·출석 xlsx, immersio/needs-map Silver)을 파싱해\n"
            "Silver 정규화 파일(CodexEntry parquet)을 산출한다. LLM 호출 없음."
        ),
    )
    _add_common_args(ingest_p)

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------
    query_p = sub.add_parser(
        "query",
        help="지도교수 질의 응답 (Silver 검색 + LLM 다듬기)",
        description=(
            "지도교수의 자연어 질의를 Silver CodexEntry에 대해 검색하고\n"
            "LLM 이 근거 기반 답변을 생성한다."
        ),
    )
    _add_common_args(query_p)

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------
    dry_run_p = sub.add_parser(
        "dry-run",
        help="결정론 단계만 실행 (LLM 미호출 — 헌장 I 완주 검증)",
        description=(
            "ingest 단계의 결정론 파이프라인만 실행하고 LLM 없이 Gold 산출물\n"
            "구조를 검증한다. 실제 LLM 호출 없음."
        ),
    )
    _add_common_args(dry_run_p)

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------
    gen_p = sub.add_parser(
        "generate",
        help="CodexEntry 생성 (LLM: subscription | api | none(template))",
        description=(
            "Silver CodexEntry 를 바탕으로 지도교수용 학습역량 요약을 생성한다.\n"
            "입력해시 캐시 적중 시 LLM 미호출 → 재실행 byte-identical."
        ),
    )
    _add_common_args(gen_p)

    # ------------------------------------------------------------------
    # distribute
    # ------------------------------------------------------------------
    dist_p = sub.add_parser(
        "distribute",
        help="지도교수별 번들 배분 및 Gold 산출",
        description=(
            "성적출석_map.yaml + 지도교수배정.yaml 에 따라 학생을 지도교수에\n"
            "배분하고 지도교수별 Gold markdown/yaml 번들을 산출한다."
        ),
    )
    _add_common_args(dist_p)

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------
    verify_p = sub.add_parser(
        "verify",
        help="CodexEntry 완결성·근거·PII 경계 검증",
        description=(
            "Silver CodexEntry 의 완결성(필수 필드), 근거 추적 가능성,\n"
            "PII 경계(가명화 준수) 를 검증한다."
        ),
    )
    _add_common_args(verify_p)

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    build_p = sub.add_parser(
        "build",
        help="전체 파이프라인 (ingest→generate→verify→distribute→Gold 산출)",
        description=(
            "ingest→generate→verify→distribute→output 를 순서대로 실행해 Gold\n"
            "산출물(지도교수별 md/yaml, manifest_metric-codex.json)을 생성한다.\n"
            "검증 통과 전 Gold 미작성 (헌장 V 원자성)."
        ),
    )
    _add_common_args(build_p)

    return parser


# ---------------------------------------------------------------------------
# Subcommand handlers (stubs — real logic filled by later tasks)
# ---------------------------------------------------------------------------


def _run_ingest(args: argparse.Namespace) -> int:
    """Stub handler for ``ingest``. Real Bronze→Silver pipeline TBD."""
    raise NotImplementedError("ingest pipeline not yet implemented")


def _run_query(args: argparse.Namespace) -> int:
    """Stub handler for ``query``. Retrieval + LLM polish TBD."""
    raise NotImplementedError("query pipeline not yet implemented")


def _run_dry_run(args: argparse.Namespace) -> int:
    """Stub handler for ``dry-run``. Determinism-only pass TBD."""
    raise NotImplementedError("dry-run pipeline not yet implemented")


def _run_generate(args: argparse.Namespace) -> int:
    """Stub handler for ``generate``. CodexEntry generation TBD."""
    raise NotImplementedError("generate pipeline not yet implemented")


def _run_distribute(args: argparse.Namespace) -> int:
    """Stub handler for ``distribute``. Advisor bundle distribution TBD."""
    raise NotImplementedError("distribute pipeline not yet implemented")


def _run_verify(args: argparse.Namespace) -> int:
    """Stub handler for ``verify``. Completeness/PII verification TBD."""
    raise NotImplementedError("verify pipeline not yet implemented")


def _run_build(args: argparse.Namespace) -> int:
    """Stub handler for ``build``. Full pipeline TBD."""
    raise NotImplementedError("build pipeline not yet implemented")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS = {
    "ingest": _run_ingest,
    "query": _run_query,
    "dry-run": _run_dry_run,
    "generate": _run_generate,
    "distribute": _run_distribute,
    "verify": _run_verify,
    "build": _run_build,
}


def app(argv: list[str] | None = None) -> int:
    """Entry point for the ``metric-codex`` console script.

    Args:
        argv: Optional override for ``sys.argv[1:]``.  Useful for testing.

    Returns:
        Integer exit code: 0 (success) / 2 (input/config error) /
        3 (pipeline step failure) / 4 (LLM backend unreachable).
    """
    parser = _build_parser()
    # argparse raises SystemExit for --help and unknown arguments.
    # Capture the exit code so callers (tests) get an integer.
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:  # pragma: no cover
        parser.error(f"unknown command: {args.command}")

    try:
        return handler(args)
    except NotImplementedError:
        # Stub handlers — pipeline not yet wired. Treat as a pipeline step
        # failure (exit 3) rather than letting the traceback escape.
        print(
            f"metric-codex: '{args.command}' is not yet implemented",
            file=sys.stderr,
        )
        return 3
    except ValueError as exc:
        print(f"ERROR [metric-codex]: input/config validation error — {exc}", file=sys.stderr)
        return 2
    # TODO(U2b/generate): add `except BackendUnreachableError: return 4` when the
    # api backend is wired (BackendUnreachableError subclasses RuntimeError, so it
    # must be caught BEFORE the RuntimeError branch below — order matters).
    except RuntimeError as exc:
        print(f"ERROR [metric-codex]: pipeline step failed — {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
