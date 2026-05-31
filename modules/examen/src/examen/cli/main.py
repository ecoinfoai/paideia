"""examen CLI entry point — T016.

Entry point: ``examen = "examen.cli.main:app"`` (immersio 와 동일 패턴).

Subcommands
-----------
- ``ingest``    — Bronze→Silver: 교재 클린·청킹, STT 파싱, 출처 대장 (LLM 0)
- ``plan``      — blueprint solver: 슬롯 목록 산출 (LLM 0)
- ``dry-run``   — 슬롯별 생성요청 번들 산출, LLM 미호출 (헌장 I 검증)
- ``generate``  — 번들→문항 생성 (LLM: subscription | api)
- ``verify``    — groundedness·형식·정답균형·중복 검증
- ``build``     — 전체 파이프라인 (ingest→plan→generate→verify→output)

Common options (all subcommands):
    --semester SEMESTER  (required) SemesterCode (e.g. "2026-1")
    --course COURSE      (required) CourseSlug (e.g. "anatomy")
    --blueprint PATH     출제사양 YAML (defaults to bronze dir convention)
    --curriculum-map PATH 주차→장→절 YAML (defaults to bronze dir convention)
    --backend {subscription,api}  (default: subscription)
    --no-emphasis        강조 자료 무시

Exit codes (immersio 규약 계승 — contracts/cli_examen.md):
    0 — Success
    2 — 입력/설정 검증 실패 (missing required input, bad blueprint, config error)
    3 — 생성/검증 단계 실패 (not-yet-implemented stubs; SubscriptionBackend missing response)
    4 — LLM 백엔드 도달 실패 (api mode only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from examen.generate.backend import BackendUnreachableError

# ---------------------------------------------------------------------------
# Argument parser builder
# ---------------------------------------------------------------------------


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common options to a subcommand parser.

    Common options are: ``--semester``, ``--course``, ``--blueprint``,
    ``--curriculum-map``, ``--backend``, ``--no-emphasis``.
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
        "--blueprint",
        type=Path,
        default=None,
        metavar="PATH",
        help="출제사양 YAML (미지정 시 bronze 디렉터리 규약 경로 사용)",
    )
    parser.add_argument(
        "--curriculum-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="주차→장→절 매핑 YAML (미지정 시 bronze 디렉터리 규약 경로 사용)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=("subscription", "api"),
        default="subscription",
        help="LLM 백엔드 (기본: subscription)",
    )
    parser.add_argument(
        "--no-emphasis",
        action="store_true",
        help="강조 자료 무시 (degrade 강제 테스트)",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with all 6 subcommands."""
    parser = argparse.ArgumentParser(
        prog="examen",
        description=(
            "examen — 시험 문제 초안 결정론적 출제 파이프라인 (paideia 모듈)\n"
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
        help="Bronze→Silver: 교재 클린·청킹, STT 파싱, 출처 대장 산출",
        description=(
            "Bronze 입력(교재 텍스트, STT, 형성평가 yaml, 퀴즈 xls)을 파싱해\n"
            "Silver 정규화 파일(SourceInventory, EmphasisCell)과\n"
            "ingest_report.json 을 산출한다. LLM 호출 없음."
        ),
    )
    _add_common_args(ingest_p)

    # ------------------------------------------------------------------
    # plan
    # ------------------------------------------------------------------
    plan_p = sub.add_parser(
        "plan",
        help="blueprint solver: 총 문항 수→챕터/난이도/출처 배분 → 슬롯 목록",
        description=(
            "blueprint.yaml 의 제약(총 문항 수, 난이도 목표, 출처 믹스)을\n"
            "결정론적 그리디 알고리즘으로 풀어 슬롯 목록을 산출한다. LLM 호출 없음."
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
        help="groundedness·형식·정답번호 균형·중복·문제검증",
        description=(
            "생성된 문항을 원본 교재에 대한 groundedness, 형식 규칙(보기 글자수 등),\n"
            "정답번호 균형(15~25%, 연속 ≤2), 중복 여부로 검증한다."
        ),
    )
    _add_common_args(verify_p)

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    build_p = sub.add_parser(
        "build",
        help="전체 파이프라인 (ingest→plan→generate→verify→Gold 산출)",
        description=(
            "ingest→plan→generate→verify→output 를 순서대로 실행해 Gold 산출물\n"
            "(exam_draft.xlsx·md, manifest_examen.json 등)을 생성한다.\n"
            "검증 통과 전 Gold 미작성 (헌장 V 원자성)."
        ),
    )
    _add_common_args(build_p)

    return parser


# ---------------------------------------------------------------------------
# Blueprint validation helper
# ---------------------------------------------------------------------------


def _validate_blueprint(
    semester: str,
    course: str,
    blueprint_path: Path | None,
) -> int:
    """Validate the blueprint, resolving to the bronze-dir default if not given.

    Args:
        semester: Semester code string.
        course: Course slug string.
        blueprint_path: Explicit ``--blueprint`` argument, or ``None``.

    Returns:
        0 if validation passes, 2 if it fails.
    """
    from examen.ingest.config import bronze_dir, load_blueprint

    # blueprint 경로가 없으면 bronze 디렉터리 규약 경로 사용
    if blueprint_path is None:
        blueprint_path = bronze_dir(semester, course) / "blueprint.yaml"

    try:
        load_blueprint(blueprint_path)
    except FileNotFoundError as exc:
        print(f"ERROR [examen]: blueprint not found — {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR [examen]: blueprint validation failed — {exc}", file=sys.stderr)
        return 2

    return 0


# ---------------------------------------------------------------------------
# Subcommand handlers (stubs — real logic filled by later tasks)
# ---------------------------------------------------------------------------


def _run_ingest(args: argparse.Namespace) -> int:
    """Stub handler for ``ingest``. Validates blueprint; pipeline TBD (later task)."""
    rc = _validate_blueprint(args.semester, args.course, args.blueprint)
    if rc != 0:
        return rc

    # TODO(US1): implement ingest pipeline (Bronze→Silver)
    print(
        f"[examen ingest] semester={args.semester} course={args.course} "
        f"(not yet implemented — pipeline stub)",
        file=sys.stderr,
    )
    return 0


def _run_plan(args: argparse.Namespace) -> int:
    """Stub handler for ``plan``. Validates blueprint; solver TBD (later task)."""
    rc = _validate_blueprint(args.semester, args.course, args.blueprint)
    if rc != 0:
        return rc

    # TODO(US2): implement blueprint solver → slot list
    print(
        f"[examen plan] semester={args.semester} course={args.course} "
        f"(not yet implemented — pipeline stub)",
        file=sys.stderr,
    )
    return 0


def _run_dry_run(args: argparse.Namespace) -> int:
    """Stub handler for ``dry-run``. Validates blueprint; bundle writer TBD."""
    rc = _validate_blueprint(args.semester, args.course, args.blueprint)
    if rc != 0:
        return rc

    # TODO(US2): wire dry_run_bundles after plan produces slot list
    print(
        f"[examen dry-run] semester={args.semester} course={args.course} "
        f"(not yet implemented — pipeline stub)",
        file=sys.stderr,
    )
    return 0


def _run_generate(args: argparse.Namespace) -> int:
    """Stub handler for ``generate``. Validates blueprint; generation TBD."""
    rc = _validate_blueprint(args.semester, args.course, args.blueprint)
    if rc != 0:
        return rc

    # TODO(US3): implement generation pipeline with InputHashCache + chosen backend
    print(
        f"[examen generate] semester={args.semester} course={args.course} "
        f"backend={args.backend} no_emphasis={args.no_emphasis} "
        f"(not yet implemented — pipeline stub)",
        file=sys.stderr,
    )
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    """Stub handler for ``verify``. Validates blueprint; verifier TBD."""
    rc = _validate_blueprint(args.semester, args.course, args.blueprint)
    if rc != 0:
        return rc

    # TODO(US4): implement groundedness + format verification
    print(
        f"[examen verify] semester={args.semester} course={args.course} "
        f"(not yet implemented — pipeline stub)",
        file=sys.stderr,
    )
    return 0


def _run_build(args: argparse.Namespace) -> int:
    """Handler for ``build``: ingest→plan→generate→verify→Gold output pipeline.

    Loads blueprint + curriculum_map, verifies chapter files, runs the full
    build_exam() pipeline with the selected backend, and writes Gold artefacts
    to a run-isolated directory.

    Exit codes:
        0 — success
        2 — missing/invalid input (blueprint, curriculum_map, chapter files)
        3 — generation/verify step failure
        4 — LLM backend unreachable (api mode)
    """
    from pathlib import Path

    from examen.generate.backend import ApiBackend, SubscriptionBackend
    from examen.ingest.config import bronze_dir as _bronze_dir
    from examen.ingest.config import load_blueprint, load_curriculum_map
    from examen.pipeline import build_exam

    semester = args.semester
    course = args.course

    # Resolve blueprint path
    blueprint_path: Path | None = args.blueprint
    if blueprint_path is None:
        blueprint_path = _bronze_dir(semester, course) / "blueprint.yaml"

    # Resolve curriculum_map path
    curriculum_map_path: Path | None = args.curriculum_map
    if curriculum_map_path is None:
        curriculum_map_path = _bronze_dir(semester, course) / "curriculum_map.yaml"

    # Load + validate blueprint
    try:
        blueprint = load_blueprint(blueprint_path)
    except FileNotFoundError as exc:
        print(f"ERROR [examen]: blueprint not found — {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR [examen]: blueprint validation failed — {exc}", file=sys.stderr)
        return 2

    # Load + validate curriculum_map
    try:
        curriculum_map = load_curriculum_map(curriculum_map_path)
    except FileNotFoundError as exc:
        print(f"ERROR [examen]: curriculum_map not found — {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR [examen]: curriculum_map validation failed — {exc}", file=sys.stderr)
        return 2

    # Select backend
    bronze_dir_path = _bronze_dir(semester, course)
    if args.backend == "api":
        backend = ApiBackend()
    else:
        # subscription: staging + responses dirs under silver
        from examen.output.paths import silver_dir as _silver_dir
        silver_dir_path = _silver_dir(semester, course)
        staging_dir = silver_dir_path / "staging"
        responses_dir = silver_dir_path / "responses"
        backend = SubscriptionBackend(staging_dir=staging_dir, responses_dir=responses_dir)

    # Run pipeline
    try:
        items, run_dir = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir_path,
            data_root=Path("data"),
            backend=backend,
            blueprint_path=blueprint_path,
            curriculum_map_path=curriculum_map_path,
        )
    except FileNotFoundError as exc:
        print(f"ERROR [examen]: missing input file — {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        # Pipeline config/coverage errors (e.g. a slot chapter_no with no matching
        # chapter data) are input/config faults → exit 2.  A bare ValueError is NOT
        # a RuntimeError, so the app() trap would otherwise let it escape to exit 1.
        print(f"ERROR [examen]: pipeline config/coverage error — {exc}", file=sys.stderr)
        return 2

    print(
        f"[examen build] done: {len(items)} items → {run_dir}",
        file=sys.stderr,
    )
    return 0


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
    """Entry point for the ``examen`` console script.

    Args:
        argv: Optional override for ``sys.argv[1:]``.  Useful for testing.

    Returns:
        Integer exit code (0 / 2 / 3 / 4).
    """
    parser = _build_parser()
    # argparse가 필수 인자 누락 또는 --help 시 SystemExit을 raise함.
    # SystemExit.code 를 그대로 반환해 테스트에서 정수 비교 가능하게 한다.
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:  # pragma: no cover
        parser.error(f"unknown command: {args.command}")
        return 2

    # Pipeline exception trap (T016 — exit codes 3/4). Placed in app() so all
    # future pipeline wiring inherits the mapping without each handler repeating
    # it. BackendUnreachableError (api 백엔드 도달 실패) → 4; any other
    # RuntimeError (생성/검증 단계 실패, e.g. SubscriptionBackend missing
    # response) → 3. Order matters: BackendUnreachableError subclasses
    # RuntimeError, so it must be caught first.
    try:
        return handler(args)
    except BackendUnreachableError as exc:
        print(f"ERROR [examen]: LLM backend unreachable — {exc}", file=sys.stderr)
        return 4
    except RuntimeError as exc:
        print(f"ERROR [examen]: generate/verify step failed — {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
