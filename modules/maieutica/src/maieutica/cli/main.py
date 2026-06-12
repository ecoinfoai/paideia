"""maieutica CLI entry point — T012.

Entry point: ``maieutica = "maieutica.cli.main:app"`` (examen 동일 패턴).

Subcommands
-----------
- ``ingest``    — Bronze→Silver: 챕터 교재 클린·청킹, 근거 인덱스 (LLM 0)
- ``plan``      — 생성사양 → 슬롯 목록(N 퀴즈 + M 형성, 챕터 1개) (LLM 0)
- ``dry-run``   — 슬롯별 생성요청 번들만 산출 (LLM 미호출 — 헌장 I 결정론 완주)
- ``generate``  — 번들 → 문항 생성 (LLM: subscription | api)
- ``verify``    — groundedness·형식·정답번호 균형·중복·자동 2차 재검토
- ``build``     — 전체 파이프라인 (ingest→plan→generate→verify→assemble→output)

Common options (all subcommands):
    --semester SEMESTER        (required) SemesterCode (e.g. "2026-1")
    --course COURSE            (required) CourseSlug (e.g. "anatomy-physiology")
    --week WEEK                (required) 대상 주차 (int); curriculum_map 으로 챕터 귀속
    --generation-spec PATH     생성사양 YAML (미지정 시 bronze 디렉터리 규약 경로 사용)
    --curriculum-map PATH      주차→장→절 YAML (미지정 시 bronze 디렉터리 규약 경로 사용)
    --quiz-count N             퀴즈 후보 수 재정의 (optional int)
    --formative-count M        형성 후보 수 재정의 (optional int)
    --backend {subscription,api}  (default: subscription)

Exit codes (immersio·examen 규약 계승 — contracts/cli_maieutica.md):
    0 — Success
    2 — 입력/설정 검증 실패 (missing required input, bad spec, curriculum mapping missing)
    3 — 생성/검증 단계 실패 (not-yet-implemented stubs; SubscriptionBackend missing response)
    4 — LLM 백엔드 도달 실패 (api mode only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from maieutica.generate.backend import BackendUnreachableError

# ---------------------------------------------------------------------------
# Argument parser builder
# ---------------------------------------------------------------------------


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common options to a subcommand parser.

    Common options: ``--semester``, ``--course``, ``--week``,
    ``--generation-spec``, ``--curriculum-map``, ``--quiz-count``,
    ``--formative-count``, ``--backend``.
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
        help="과목 슬러그 (예: 'anatomy-physiology')",
    )
    parser.add_argument(
        "--week",
        required=True,
        type=int,
        metavar="WEEK",
        help="대상 주차 정수 — curriculum_map 으로 챕터 귀속",
    )
    parser.add_argument(
        "--generation-spec",
        type=Path,
        default=None,
        metavar="PATH",
        help="생성사양 YAML (미지정 시 bronze 디렉터리 규약 경로 사용)",
    )
    parser.add_argument(
        "--curriculum-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="주차→장→절 매핑 YAML (미지정 시 bronze 디렉터리 규약 경로 사용)",
    )
    parser.add_argument(
        "--quiz-count",
        type=int,
        default=None,
        metavar="N",
        help="퀴즈 후보 수 재정의 (미지정 시 generation_spec 또는 기본값 20 사용)",
    )
    parser.add_argument(
        "--formative-count",
        type=int,
        default=None,
        metavar="M",
        help="형성 후보 수 재정의 (미지정 시 generation_spec 또는 기본값 3 사용)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=("subscription", "api"),
        default="subscription",
        help="LLM 백엔드 (기본: subscription)",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with all 6 subcommands."""
    parser = argparse.ArgumentParser(
        prog="maieutica",
        description=(
            "maieutica — 교재 기반 주차별 퀴즈·형성평가 후보 생성 파이프라인 (paideia 모듈)\n"
            "\n"
            "종료 코드: 0 성공 · 2 입력/설정 검증 실패 · "
            "3 생성/검증 단계 실패 · 4 LLM 백엔드 도달 실패(api 모드)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------
    # ingest
    # ------------------------------------------------------------------
    ingest_p = sub.add_parser(
        "ingest",
        help="Bronze→Silver: 챕터 교재 클린·청킹, 근거 인덱스 산출 (LLM 0)",
        description=(
            "Bronze 입력(챕터 교재 텍스트)을 클리닝·청킹해\n"
            "Silver 정규화 파일(청크 ID + 문자범위 근거 인덱스)과\n"
            "ingest_report.json 을 산출한다. LLM 호출 없음."
        ),
    )
    _add_common_args(ingest_p)

    # ------------------------------------------------------------------
    # plan
    # ------------------------------------------------------------------
    plan_p = sub.add_parser(
        "plan",
        help="생성사양 → 슬롯 목록(N 퀴즈 + M 형성, 챕터 1개) (LLM 0)",
        description=(
            "generation_spec.yaml 의 제약(주차·챕터·퀴즈 수·형성 수)을\n"
            "결정론적으로 풀어 슬롯 목록을 산출한다. LLM 호출 없음."
        ),
    )
    _add_common_args(plan_p)

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------
    dry_run_p = sub.add_parser(
        "dry-run",
        help="슬롯별 생성요청 번들만 산출 (LLM 미호출 — 헌장 I 결정론 완주 검증)",
        description=(
            "plan 단계의 슬롯 목록으로 생성요청 번들 JSON 파일을 staging 디렉터리에\n"
            "쓴다. LLM 호출 없음. subscription 세션이 읽을 번들을 생성할 때 사용."
        ),
    )
    _add_common_args(dry_run_p)

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------
    gen_p = sub.add_parser(
        "generate",
        help="번들 → 문항 생성 (LLM: --backend subscription | api)",
        description=(
            "슬롯별 생성요청 번들을 LLM 백엔드에 전달해 문항 초안을 생성한다.\n"
            "입력해시 캐시 적중 시 LLM 미호출 → 재실행 byte-identical (SC-009)."
        ),
    )
    _add_common_args(gen_p)

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------
    verify_p = sub.add_parser(
        "verify",
        help="groundedness·보기 글자수·해설 길이·정답번호 균형·중복·2차 재검토",
        description=(
            "생성된 문항을 원본 교재에 대한 groundedness, 형식 규칙(보기 글자수·해설 길이),\n"
            "정답번호 균형(15~25%, 연속 ≤2), 중복 여부로 검증한다.\n"
            "자동 2차 재검토 포함."
        ),
    )
    _add_common_args(verify_p)

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    build_p = sub.add_parser(
        "build",
        help="전체 파이프라인 (ingest→plan→generate→verify→assemble→Gold 산출)",
        description=(
            "ingest→plan→generate→verify→assemble→output 를 순서대로 실행해\n"
            "Gold 산출물(기말출제초안.xlsx·yaml, 출제품질리포트.md, manifest_maieutica.json)을\n"
            "생성한다. 검증 통과 전 Gold 미작성 (헌장 V 원자성)."
        ),
    )
    _add_common_args(build_p)

    return parser


# ---------------------------------------------------------------------------
# Subcommand handlers (stubs — real pipeline logic filled by later tasks)
# ---------------------------------------------------------------------------


def _run_ingest(args: argparse.Namespace) -> int:
    """Stub handler for ``ingest``. Pipeline TBD (later task).

    Args:
        args: Parsed CLI namespace.

    Returns:
        3 — stub not yet implemented.
    """
    raise NotImplementedError(
        f"ingest: pipeline not yet implemented "
        f"(semester={args.semester!r}, course={args.course!r}, week={args.week})"
    )


def _run_plan(args: argparse.Namespace) -> int:
    """Stub handler for ``plan``. Solver TBD (later task).

    Args:
        args: Parsed CLI namespace.

    Returns:
        3 — stub not yet implemented.
    """
    raise NotImplementedError(
        f"plan: pipeline not yet implemented "
        f"(semester={args.semester!r}, course={args.course!r}, week={args.week})"
    )


def _run_dry_run(args: argparse.Namespace) -> int:
    """Stub handler for ``dry-run``. Bundle writer TBD (later task).

    Args:
        args: Parsed CLI namespace.

    Returns:
        3 — stub not yet implemented.
    """
    raise NotImplementedError(
        f"dry-run: pipeline not yet implemented "
        f"(semester={args.semester!r}, course={args.course!r}, week={args.week})"
    )


def _run_generate(args: argparse.Namespace) -> int:
    """Stub handler for ``generate``. Generation pipeline TBD (later task).

    Args:
        args: Parsed CLI namespace.

    Returns:
        3 — stub not yet implemented.
    """
    raise NotImplementedError(
        f"generate: pipeline not yet implemented "
        f"(semester={args.semester!r}, course={args.course!r}, week={args.week}, "
        f"backend={args.backend!r})"
    )


def _run_verify(args: argparse.Namespace) -> int:
    """Stub handler for ``verify``. Verifier TBD (later task).

    Args:
        args: Parsed CLI namespace.

    Returns:
        3 — stub not yet implemented.
    """
    raise NotImplementedError(
        f"verify: pipeline not yet implemented "
        f"(semester={args.semester!r}, course={args.course!r}, week={args.week})"
    )


def _run_build(args: argparse.Namespace) -> int:
    """Stub handler for ``build``. Full pipeline TBD (later task).

    Args:
        args: Parsed CLI namespace.

    Returns:
        3 — stub not yet implemented.
    """
    raise NotImplementedError(
        f"build: pipeline not yet implemented "
        f"(semester={args.semester!r}, course={args.course!r}, week={args.week}, "
        f"backend={args.backend!r})"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


_COMMAND_HANDLERS = {
    "ingest": _run_ingest,
    "plan": _run_plan,
    "dry-run": _run_dry_run,
    "generate": _run_generate,
    "verify": _run_verify,
    "build": _run_build,
}


def app(argv: list[str] | None = None) -> int:
    """Entry point for the ``maieutica`` console script.

    Args:
        argv: Optional override for ``sys.argv[1:]``.  Useful for testing.

    Returns:
        Integer exit code (0 / 2 / 3 / 4).
    """
    parser = _build_parser()
    # argparse 가 필수 인자 누락 또는 --help 시 SystemExit 을 raise 함.
    # SystemExit.code 를 그대로 반환해 테스트에서 정수 비교 가능하게 한다.
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:  # pragma: no cover
        parser.error(f"unknown command: {args.command!r}")
        return 2

    # Pipeline exception trap — exit-code mapping:
    #   BackendUnreachableError  → 4  (LLM api backend도달 실패)
    #   NotImplementedError      → 3  (stub — generation/verify stage not yet impl)
    #   RuntimeError             → 3  (generation/verify stage failure)
    # Order matters: BackendUnreachableError subclasses RuntimeError.
    try:
        return handler(args)
    except BackendUnreachableError as exc:
        print(
            f"ERROR [maieutica]: LLM backend unreachable — {exc}",
            file=sys.stderr,
        )
        return 4
    except NotImplementedError as exc:
        print(
            f"ERROR [maieutica]: not yet implemented — {exc}",
            file=sys.stderr,
        )
        return 3
    except RuntimeError as exc:
        print(
            f"ERROR [maieutica]: generate/verify step failed — {exc}",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
