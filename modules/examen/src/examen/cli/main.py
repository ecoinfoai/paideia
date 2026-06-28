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
from typing import TYPE_CHECKING

from paideia_shared.schemas._common import CourseSlug, SemesterCode
from pydantic import TypeAdapter

from examen.generate.backend import BackendUnreachableError

if TYPE_CHECKING:
    from paideia_shared.schemas import (
        CurriculumMap,
        ExamenBlueprint,
        SourceInventoryEntry,
    )

    from examen.generate.backend import LLMBackend

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
    build_p.add_argument(
        "--stt",
        type=Path,
        default=None,
        metavar="PATH",
        help=("강의 녹취(STT) 디렉터리 — 미지정 시 bronze 규약 경로 자동 탐색"),
    )

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


def _select_backend(args: argparse.Namespace, semester: str, course: str) -> LLMBackend:
    """Construct the real LLM backend for ``build`` from ``args.backend``.

    Factored out of ``_run_build`` so tests can inject a network-free
    ``FakeBackend`` via the ``_run_build(..., backend=...)`` seam without
    instantiating the real ``SubscriptionBackend`` / ``ApiBackend``.

    Args:
        args: Parsed CLI namespace (uses ``args.backend``).
        semester: Semester code (for the subscription staging/responses dirs).
        course: Course slug (for the subscription staging/responses dirs).

    Returns:
        A concrete ``LLMBackend`` instance (``ApiBackend`` or
        ``SubscriptionBackend``).
    """
    from examen.generate.backend import ApiBackend, SubscriptionBackend

    if args.backend == "api":
        return ApiBackend()
    # subscription: staging + responses dirs under silver
    from examen.output.paths import silver_dir as _silver_dir

    silver_dir_path = _silver_dir(semester, course)
    staging_dir = silver_dir_path / "staging"
    responses_dir = silver_dir_path / "responses"
    return SubscriptionBackend(staging_dir=staging_dir, responses_dir=responses_dir)


def _load_build_inventories(
    blueprint: ExamenBlueprint,
    curriculum_map: CurriculumMap,
    bronze_dir_path: Path,
) -> tuple[list[SourceInventoryEntry] | None, list[SourceInventoryEntry] | None]:
    """Resolve formative & quiz source inventories from the Bronze convention.

    Loads inventories ONLY when the blueprint actually declares them
    (``source_mix['formative'] > 0`` / ``source_mix['quiz'] > 0``).  When a
    source is declared but its Bronze data is missing, fails fast with a
    located ``FileNotFoundError`` (caller maps to exit 2 — no silent skip,
    constitution: 조용한 누락 금지).  When a source is NOT declared
    (count == 0) the corresponding inventory is ``None`` so ``build_exam``'s
    existing ``source_mix == 0`` guard (validate_formative_count) is honoured.

    Bronze layout (quickstart §1)::

        {bronze}/formative/Ch*_FormativeTest.yaml
        {bronze}/formative/형성평가_실제_출제문제들.txt
        {bronze}/quiz/QuestionUploadExcel_{week}주차.xls

    Args:
        blueprint: Validated ExamenBlueprint (reads ``source_mix``).
        curriculum_map: Validated CurriculumMap (week→chapter resolution).
        bronze_dir_path: Path to the Bronze directory.

    Returns:
        ``(formative_inventory, quiz_inventory)`` — each a
        ``list[SourceInventoryEntry]`` when declared+present, else ``None``.

    Raises:
        FileNotFoundError: If a source is declared (>0) but its Bronze data
            (subdir / required file) is absent.
        ValueError: Propagated from the loaders (malformed input, unmatched
            administered item, week missing from curriculum_map, etc.).
    """
    from examen.ingest.source_inventory import (
        load_formative_inventory,
        load_quiz_inventory,
    )

    source_mix = blueprint.source_mix
    semester = blueprint.semester
    course_slug = blueprint.course_slug

    # ---- formative ----
    formative_inventory = None
    if source_mix.get("formative", 0) > 0:
        formative_dir = bronze_dir_path / "formative"
        actual_txt = formative_dir / "형성평가_실제_출제문제들.txt"
        chapter_yamls = sorted(formative_dir.glob("Ch*_FormativeTest.yaml"))
        if not formative_dir.is_dir() or not actual_txt.exists() or not chapter_yamls:
            raise FileNotFoundError(
                f"_run_build: blueprint.source_mix.formative="
                f"{source_mix['formative']} (>0) 이지만 형성평가 입력을 찾을 수 "
                f"없습니다. 기대 경로: {actual_txt} 와 "
                f"{formative_dir}/Ch*_FormativeTest.yaml. "
                "형성 출처를 배치하거나 source_mix.formative 를 0 으로 설정하세요."
            )
        formative_inventory = load_formative_inventory(
            actual_txt=actual_txt,
            chapter_yamls=chapter_yamls,
            curriculum_map=curriculum_map,
            semester=semester,
            course_slug=course_slug,
        )

    # ---- quiz ----
    quiz_inventory = None
    if source_mix.get("quiz", 0) > 0:
        quiz_dir = bronze_dir_path / "quiz"
        xls_paths = sorted(quiz_dir.glob("*.xls"))
        if not quiz_dir.is_dir() or not xls_paths:
            raise FileNotFoundError(
                f"_run_build: blueprint.source_mix.quiz={source_mix['quiz']} "
                f"(>0) 이지만 퀴즈 입력(.xls)을 찾을 수 없습니다. 기대 경로: "
                f"{quiz_dir}/QuestionUploadExcel_*주차.xls. "
                "퀴즈 출처를 배치하거나 source_mix.quiz 를 0 으로 설정하세요."
            )
        quiz_inventory = load_quiz_inventory(
            xls_paths=xls_paths,
            curriculum_map=curriculum_map,
            semester=semester,
            course_slug=course_slug,
        )

    return formative_inventory, quiz_inventory


def _run_build(args: argparse.Namespace, backend: LLMBackend | None = None) -> int:
    """Handler for ``build``: ingest→plan→generate→verify→Gold output pipeline.

    Loads blueprint + curriculum_map, verifies chapter files, loads the
    formative/quiz source inventories from the Bronze convention, runs the full
    build_exam() pipeline with the selected backend, and writes Gold artefacts
    to a run-isolated directory.

    Args:
        args: Parsed CLI namespace.
        backend: Optional injected ``LLMBackend`` (test seam).  When ``None``
            the real backend is selected from ``args.backend`` via
            ``_select_backend``.  Tests pass a network-free ``FakeBackend``.

    Exit codes:
        0 — success
        2 — missing/invalid input (blueprint, curriculum_map, chapter files,
            or a declared formative/quiz source with no Bronze data)
        3 — generation/verify step failure
        4 — LLM backend unreachable (api mode)
    """
    from pathlib import Path

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

    bronze_dir_path = _bronze_dir(semester, course)

    # Load formative/quiz inventories from the Bronze convention.  Only loaded
    # when blueprint.source_mix declares them; a declared-but-absent source is a
    # located fail-fast (exit 2).  Absent+undeclared → None (build_exam guard).
    try:
        formative_inventory, quiz_inventory = _load_build_inventories(
            blueprint, curriculum_map, bronze_dir_path
        )
    except FileNotFoundError as exc:
        print(f"ERROR [examen]: missing source inventory — {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR [examen]: source inventory error — {exc}", file=sys.stderr)
        return 2

    # Select backend (real backend unless a test injected one via the seam)
    if backend is None:
        backend = _select_backend(args, semester, course)

    # Resolve effective STT directory for the US7 lecture-emphasis enrichment.
    # Precedence: --no-emphasis forces degrade (None); else explicit --stt;
    # else the convention default data/stt guarded by .exists() (None when absent
    # → graceful degrade, never a failure; FR-026 / SC-013).
    stt_dir: Path | None
    if args.no_emphasis:
        stt_dir = None
    elif args.stt is not None:
        stt_dir = args.stt
    else:
        _default_stt = Path("data") / "stt"
        stt_dir = _default_stt if _default_stt.exists() else None

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
            formative_inventory=formative_inventory,
            quiz_inventory=quiz_inventory,
            stt_dir=stt_dir,
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


_SEMESTER_TA: TypeAdapter[SemesterCode] = TypeAdapter(SemesterCode)
_COURSE_TA: TypeAdapter[CourseSlug] = TypeAdapter(CourseSlug)


def _validate_semester_course(args: argparse.Namespace) -> int | None:
    """Validate ``--semester`` / ``--course`` against their shared patterns.

    Guards with ``getattr`` so subcommands that legitimately omit either flag
    are unaffected. On the first failure prints a located message naming the
    argument, the expected pattern and the offending value (FR-010), and
    signals exit code 2. Returns ``None`` when both values are valid (or absent).

    Args:
        args: Parsed argparse namespace.

    Returns:
        ``2`` if validation failed (caller should return this exit code), else
        ``None``.
    """
    checks: tuple[tuple[str, str | None, TypeAdapter, str, str], ...] = (
        ("--semester", getattr(args, "semester", None), _SEMESTER_TA,
         "SemesterCode", r"^\d{4}-[12SW]$"),
        ("--course", getattr(args, "course", None), _COURSE_TA,
         "CourseSlug", r"^[a-z][a-z0-9-]{1,39}$"),
    )
    examples = {"--semester": "2026-1", "--course": "anatomy"}
    for flag, value, adapter, type_name, pattern in checks:
        if value is None:
            continue
        try:
            adapter.validate_python(value)
        except ValueError:
            print(
                f"ERROR [examen]: input/config validation error — {flag} "
                f"{value!r} does not match {type_name} pattern '{pattern}' "
                f"(e.g. {examples[flag]!r})",
                file=sys.stderr,
            )
            return 2
    return None


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

    # Boundary validation (INJ-01) — reject malformed --semester / --course
    # BEFORE any handler runs, hence before output/paths.py interpolates them
    # into a filesystem path (f"{semester}-{course_slug}"). Without this a
    # traversal payload like "../../etc" reaches mkdir/write_text. app() has no
    # top-level `except ValueError`, so we map the failure to exit 2 locally.
    code = _validate_semester_course(args)
    if code is not None:
        return code

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
