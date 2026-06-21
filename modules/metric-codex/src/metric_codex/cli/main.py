"""metric-codex CLI entry point — T020.

Entry point: ``metric-codex = "metric_codex.cli.main:app"``.

Subcommands:
- ``ingest``    — Bronze→Silver: 성적·출석·immersio Silver·needs-map Silver 수집
- ``query``     — 지도교수 질의 응답 (retrieval, pseudonym space)
- ``dry-run``   — 결정론 단계만 실행, LLM 미호출 (헌장 I 검증), staging 번들 산출
- ``generate``  — CodexEntry 생성 (LLM: subscription | api | none(template))
- ``distribute``— 지도교수별 번들 배분 및 Gold 산출
- ``verify``    — CodexEntry 완결성·근거·PII 경계 검증
- ``build``     — 전체 파이프라인 (ingest→generate→distribute→verify→Gold)

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
import json
import re
import shutil
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from paideia_shared.schemas import AdvisorBundleSummary, PseudonymMapEntry
from paideia_shared.schemas.metric_codex import CodexEntry

from metric_codex.errors import LocatedInputError
from metric_codex.generate.backend import BackendUnreachableError
from metric_codex.ingest.bronze_copies import (
    load_blueprint,
    load_curriculum_map,
    load_school_excel_map,
)
from metric_codex.ingest.paideia_sources import read_paideia_sources
from metric_codex.ingest.result import SourceReadResult
from metric_codex.ingest.school_excel import read_school_excel
from metric_codex.output.manifest import build_manifest, read_manifest, write_manifest
from metric_codex.output.paths import bronze_dir, silver_dir
from metric_codex.output.sha256 import compute_sha256
from metric_codex.store.codex import accumulate, read_existing_store, write_store
from metric_codex.store.pseudonym import (
    build_pseudonym_map,
    read_pseudonym_map,
    write_pseudonym_map,
)

# When the combined immersio source (진단×시험결합) is present, these three
# individual source_ids are superseded and evicted from the store to avoid
# double-counting (MC-U26).
_SUPERSEDED_BY_COMBINED: frozenset[str] = frozenset(
    {
        "immersio:학생지표",
        "needs-map:factor_scores",
        "needs-map:cluster_assignment",
    }
)

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


def _add_now_arg(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--now`` timestamp injection flag.

    ``--now`` is the only non-deterministic injection point used by ingest,
    generate, and distribute; ``build`` shares one ``--now`` across all stages.
    Factored out so the three stage helpers can each declare it without the
    duplicate ``add_argument`` colliding when several helpers run on one parser.

    Args:
        parser: The subcommand parser to add ``--now`` to.
    """
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        metavar="ISO8601",
        help=(
            "타임스탬프로 주입할 ISO-8601 UTC. "
            "미지정 시 datetime.now(UTC) — 비결정적이므로 재현 테스트에는 명시 권장."
        ),
    )


def _add_question_set_arg(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--question-set`` flag.

    Used by query, dry-run, generate, and verify; ``build`` declares it once for
    the generate stage.  Factored out so helpers that both want it never collide.

    Args:
        parser: The subcommand parser to add ``--question-set`` to.
    """
    parser.add_argument(
        "--question-set",
        type=Path,
        default=None,
        metavar="PATH",
        help="question_set.yaml 경로 (기본: Bronze question_set.yaml)",
    )


def _add_ingest_args(parser: argparse.ArgumentParser, *, with_now: bool = True) -> None:
    """Add the ingest-stage flags (school Excel/map + optional provenance).

    Shared by the ``ingest`` subparser and ``build`` so the two flag sets can
    never drift.

    Args:
        parser: The subcommand parser to add flags to.
        with_now: When True, also add the shared ``--now`` flag.  ``build`` adds
            ``--now`` once itself (set False there) to avoid a duplicate.
    """
    parser.add_argument(
        "--school-excel",
        type=Path,
        default=None,
        metavar="PATH",
        help="학교 성적·출석 xlsx 경로 (기본: Bronze '성적출석.xlsx')",
    )
    parser.add_argument(
        "--school-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="성적출석_map.yaml 경로 (기본: Bronze '성적출석_map.yaml')",
    )
    parser.add_argument(
        "--blueprint",
        type=Path,
        default=None,
        metavar="PATH",
        help="(선택) examen blueprint.yaml — provenance 기록 전용",
    )
    parser.add_argument(
        "--curriculum-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="(선택) curriculum_map.yaml — provenance 기록 전용",
    )
    if with_now:
        _add_now_arg(parser)


def _add_generate_args(
    parser: argparse.ArgumentParser,
    *,
    with_now: bool = True,
    with_question_set: bool = True,
) -> None:
    """Add the generate-stage flags (backend/model/responses + question set).

    Shared by the ``generate`` subparser and ``build`` so the two flag sets can
    never drift.

    Args:
        parser: The subcommand parser to add flags to.
        with_now: When True, also add the shared ``--now`` flag.
        with_question_set: When True, also add the shared ``--question-set`` flag.
            ``build`` declares ``--now``/``--question-set`` once itself to avoid
            duplicates with the ingest/other helpers.
    """
    parser.add_argument(
        "--backend",
        choices=("none", "subscription", "api"),
        default="none",
        help="LLM 백엔드 (기본: none → 결정론 template; 헌장 I 오프라인 완주)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        metavar="ID",
        help="api 백엔드 모델 id (기본: claude-sonnet-4-6)",
    )
    if with_question_set:
        _add_question_set_arg(parser)
    parser.add_argument(
        "--responses-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="subscription 백엔드 응답 디렉터리 (기본: Silver staging_responses/)",
    )
    parser.add_argument(
        "--require-llm",
        action="store_true",
        default=False,
        help="api 백엔드 도달 실패 시 template 폴백 없이 종료 코드 4 (기본: 폴백)",
    )
    if with_now:
        _add_now_arg(parser)


def _add_distribute_args(parser: argparse.ArgumentParser, *, with_now: bool = True) -> None:
    """Add the distribute-stage flags (advisor roster).

    Shared by the ``distribute`` subparser and ``build`` so the two flag sets
    can never drift.

    Args:
        parser: The subcommand parser to add flags to.
        with_now: When True, also add the shared ``--now`` flag.
    """
    parser.add_argument(
        "--roster",
        type=Path,
        default=None,
        metavar="PATH",
        help="지도교수배정.yaml 경로 (기본: Bronze '지도교수배정.yaml')",
    )
    if with_now:
        _add_now_arg(parser)


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
    _add_ingest_args(ingest_p)

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------
    query_p = sub.add_parser(
        "query",
        help="지도교수 질의 응답 (Silver 검색, pseudonym 공간)",
        description=(
            "Silver CodexEntry에서 학생의 근거를 검색한다.\n"
            "학생은 student_id(10자리) 또는 pseudonym(S001)으로 지정.\n"
            "--question-id 또는 --text 중 하나(상호 배타적)."
        ),
    )
    _add_common_args(query_p)
    query_p.add_argument(
        "--student",
        required=True,
        metavar="STUDENT",
        help="학번(10자리 숫자) 또는 가명(S001 형식)",
    )
    query_student_group = query_p.add_mutually_exclusive_group(required=False)
    query_student_group.add_argument(
        "--question-id",
        metavar="ID",
        default=None,
        help="question_set.yaml 에서 질문 id 지정",
    )
    query_student_group.add_argument(
        "--text",
        metavar="TEXT",
        default=None,
        help="자유형식 키워드 검색",
    )
    _add_question_set_arg(query_p)
    query_p.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="PATH",
        dest="json_out",
        help="QueryAnswer JSON 저장 경로 (선택)",
    )
    query_p.add_argument(
        "--reveal",
        action="store_true",
        default=False,
        help="--reveal 시 student_id 와 이름 함께 출력 (기본: pseudonym만)",
    )

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------
    dry_run_p = sub.add_parser(
        "dry-run",
        help="결정론 단계만 실행 (LLM 미호출 — 헌장 I 완주 검증, staging 번들 산출)",
        description=(
            "Silver CodexEntry + pseudonym_map 을 읽어 staging/{pseudonym}.json\n"
            "번들을 산출한다. LLM 호출 없음. PRIV-01: PII 포함 파일 불산출."
        ),
    )
    _add_common_args(dry_run_p)
    _add_question_set_arg(dry_run_p)

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
    _add_generate_args(gen_p)

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
    _add_distribute_args(dist_p)

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------
    verify_p = sub.add_parser(
        "verify",
        help="CodexEntry 완결성·근거·PII 경계 검증",
        description=(
            "Silver CodexEntry 의 완결성(필수 필드), 근거 추적 가능성,\n"
            "PII 경계(가명화 준수) 를 검증한다.\n"
            "종료 코드: 0 모든 불변식 통과 · 2 입력 오류 · 3 불변식 위반"
        ),
    )
    _add_common_args(verify_p)
    _add_question_set_arg(verify_p)
    verify_p.add_argument(
        "--roster",
        type=Path,
        default=None,
        metavar="PATH",
        help="지도교수배정.yaml 경로 (기본: Bronze '지도교수배정.yaml')",
    )

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    build_p = sub.add_parser(
        "build",
        help="전체 파이프라인 (ingest→generate→distribute→verify)",
        description=(
            "ingest→generate→distribute→verify 를 순서대로 실행해 Gold\n"
            "산출물(지도교수별 md/yaml, manifest_metric-codex.json)을 생성한다.\n"
            "첫 번째 비-0 종료 코드에서 중단 (first-non-zero stop)."
        ),
    )
    _add_common_args(build_p)
    # build needs the UNION of ingest + generate + distribute flags, declared via
    # the same helpers the individual subparsers use (so the flag sets cannot
    # drift).  ``--now`` is shared by all three and ``--question-set`` by generate;
    # declare those once and suppress the duplicates in the stage helpers.
    _add_now_arg(build_p)
    _add_question_set_arg(build_p)
    _add_ingest_args(build_p, with_now=False)
    _add_generate_args(build_p, with_now=False, with_question_set=False)
    _add_distribute_args(build_p, with_now=False)

    return parser


# ---------------------------------------------------------------------------
# Subcommand handlers (stubs — real logic filled by later tasks)
# ---------------------------------------------------------------------------


def _relative_source_path(path: Path, data_root: Path) -> str:
    """Return ``path`` relative to ``data_root`` for a deterministic source_path.

    Args:
        path: A real filesystem path under ``data_root``.
        data_root: The ``--data-root`` directory.

    Returns:
        The repo-relative path string (independent of cwd / machine).

    Raises:
        LocatedInputError: If ``path`` is not inside ``data_root`` (would yield a
            non-deterministic, machine-specific source_path).
    """
    try:
        return str(path.relative_to(data_root))
    except ValueError as exc:
        raise LocatedInputError(
            "--school-excel path must be inside --data-root for a deterministic source_path",
            file=str(path),
            expected=f"path under {data_root}",
            actual=str(path),
        ) from exc


def _run_ingest(args: argparse.Namespace) -> int:
    """Consolidate all sources into the per-student Silver store (Scenario A).

    Reads the school Excel (minimal layer) plus any immersio/needs-map Silver
    (rich layer), accumulates them into ``codex_entry.parquet`` /
    ``source_ledger.parquet`` (idempotent across runs), writes the local-only
    pseudonym map, and emits the run manifest.  Missing optional upstream Silver
    degrades gracefully (fewer entries), never errors.

    Args:
        args: Parsed CLI arguments for the ``ingest`` subcommand.

    Returns:
        ``0`` on success.

    Raises:
        LocatedInputError: On any boundary failure (caught by ``app`` → exit 2).
    """
    semester: str = args.semester
    course: str = args.course
    data_root: Path = args.data_root

    # ``--now`` is the ONLY non-deterministic injection point.  When omitted we
    # fall back to wall-clock time; the resulting manifest/ledger timestamps are
    # then non-deterministic (documented in --help).
    now: str = args.now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    own_bronze = bronze_dir(semester, course, data_root=data_root)
    school_excel: Path = args.school_excel or (own_bronze / "성적출석.xlsx")
    school_map: Path = args.school_map or (own_bronze / "성적출석_map.yaml")

    own_silver = silver_dir(semester, course, data_root=data_root)
    immersio_silver = data_root / "silver" / "immersio" / f"{semester}-{course}"
    needsmap_silver = data_root / "silver" / "needs-map" / f"{semester}-{course}"

    # 1) School Excel (minimal layer).  The store accumulates across runs, so a
    #    later (e.g. immersio-only) run may legitimately omit the school Excel:
    #    when neither the workbook nor its map exists, the minimal layer simply
    #    degrades (like the upstream Silver sources).  An explicitly supplied or
    #    half-present source still fails fast.
    results: list[SourceReadResult] = []
    config_ids: dict[str, str] = {}
    school_explicit = args.school_excel is not None or args.school_map is not None
    if school_explicit or school_map.is_file() or school_excel.is_file():
        excel_map = load_school_excel_map(school_map)
        school_source_path = _relative_source_path(school_excel, data_root)
        results.append(
            read_school_excel(
                school_excel,
                excel_map,
                ingested_at=now,
                source_path=school_source_path,
            )
        )
        config_ids[school_map.name] = compute_sha256(school_map)

    # 2) Upstream paideia Silver (rich layer) — missing dirs degrade silently.
    immersio_dir_arg = immersio_silver if immersio_silver.is_dir() else None
    needsmap_dir_arg = needsmap_silver if needsmap_silver.is_dir() else None
    paideia_results = read_paideia_sources(
        immersio_silver_dir=immersio_dir_arg,
        needsmap_silver_dir=needsmap_dir_arg,
        semester=semester,
        data_root=data_root,
        ingested_at=now,
    )
    results.extend(paideia_results)

    # MC-U26: when the combined source (진단×시험결합) is present in this run's
    # results, the three individual sources it supersedes must be evicted from
    # the store so they cannot double-count alongside the combined entries.
    combined_source_id = "immersio:진단×시험결합"
    combined_in_results = any(
        r.source_record.source_id == combined_source_id for r in paideia_results
    )
    superseded_source_ids = _SUPERSEDED_BY_COMBINED if combined_in_results else frozenset()

    # F1/F2 transparency: report which upstream sources were found vs absent so
    # operators can detect silent degrade without inspecting the manifest.
    _school_status = "found" if (
        school_explicit or school_map.is_file() or school_excel.is_file()
    ) else "absent"
    _immersio_status = "found" if immersio_dir_arg is not None else "absent"
    _needsmap_status = "found" if needsmap_dir_arg is not None else "absent"
    print(
        f"ingest: sources — "
        f"school_excel={_school_status} "
        f"immersio={_immersio_status} "
        f"needs-map={_needsmap_status}",
        file=sys.stderr,
    )

    # 3) Optional provenance: validate blueprint/curriculum (fail-fast) and
    #    record their digests only — they are not used for entry construction.
    if args.blueprint is not None:
        load_blueprint(args.blueprint)
        config_ids[args.blueprint.name] = compute_sha256(args.blueprint)
    if args.curriculum_map is not None:
        load_curriculum_map(args.curriculum_map)
        config_ids[args.curriculum_map.name] = compute_sha256(args.curriculum_map)

    # 4) Accumulate into the (possibly pre-existing) Silver store.
    existing_entries, existing_records = read_existing_store(own_silver)
    entries, records = accumulate(
        results,
        existing_entries,
        existing_records,
        superseded_source_ids=superseded_source_ids,
    )
    write_store(own_silver, entries, records)

    # 5) Local-only pseudonym map over the FULL accumulated student set.  The
    #    store accumulates across runs, so the map must cover every student with
    #    a CodexEntry — not just this run's — and must preserve names established
    #    by earlier runs (a run that omits a student must not drop them).
    pseudonym_path = own_silver / "pseudonym_map.parquet"
    identities: dict[str, str | None] = {}
    prior_pseudonyms: dict[str, str] = {}
    # Seed with names and pseudonyms recovered from the prior map (append-only).
    if pseudonym_path.is_file():
        for prior in read_pseudonym_map(pseudonym_path):
            identities[prior.student_id] = prior.name_kr
            prior_pseudonyms[prior.student_id] = prior.pseudonym
    # Overlay this run's identities — a non-None name always wins.
    for result in results:
        for student_id, name_kr in result.identities.items():
            if name_kr is not None or identities.get(student_id) is None:
                identities[student_id] = name_kr
    # Ensure every accumulated student is present (name unknown → None).
    for entry in entries:
        identities.setdefault(entry.student_id, None)
    write_pseudonym_map(
        pseudonym_path,
        build_pseudonym_map(identities, prior=prior_pseudonyms),
    )

    # 6) Manifest — pre-distribution bundle snapshot (distribute overwrites later).
    student_ids = sorted({e.student_id for e in entries})
    student_count = len(student_ids)
    bundle_summary = AdvisorBundleSummary(
        total_students_with_codex=student_count,
        assigned_count=0,
        unassigned_sids=student_ids,
        advisor_count=0,
        per_advisor_counts={},
    )
    manifest = build_manifest(
        semester=semester,
        course_slug=course,
        input_hashes={r.source_record.source_id: r.source_record.sha256 for r in results},
        config_ids=config_ids,
        generated_at=now,
        llm_backend="none(template)",
        llm_model=None,
        cache_hit_rate=None,
        student_count=student_count,
        entry_count=len(entries),
        bundle_summary=bundle_summary,
    )
    write_manifest(own_silver / "manifest_metric-codex.json", manifest)

    return 0


def _load_store_and_map(
    own_silver: Path,
    pseudonym_path: Path,
) -> tuple[list[CodexEntry], list[PseudonymMapEntry]]:
    """Load the Silver codex store and pseudonym map for a semester/course.

    Shared by the ``query``, ``dry-run`` (and later ``generate``) handlers.

    Args:
        own_silver: metric-codex Silver directory for this semester/course.
        pseudonym_path: Path to ``pseudonym_map.parquet`` in that directory.

    Returns:
        ``(entries, pseudonym_map)`` — all CodexEntry rows and the full map.

    Raises:
        LocatedInputError: If a present store/map file fails to read or validate.
    """
    entries, _ = read_existing_store(own_silver)
    pseudonym_map = read_pseudonym_map(pseudonym_path)
    return entries, pseudonym_map


def _resolve_student(
    student_arg: str,
    entries: list[CodexEntry],
    pseudonym_map: list[PseudonymMapEntry],
) -> tuple[str, str, str | None]:
    """Resolve --student to (student_id, pseudonym, name_kr).

    Accepts a 10-digit student_id or an S\\d{3,} pseudonym.

    Args:
        student_arg: The --student CLI value.
        entries: All CodexEntry rows in the store.
        pseudonym_map: Full pseudonym map.

    Returns:
        ``(student_id, pseudonym, name_kr)`` tuple.

    Raises:
        LocatedInputError: If the student is not found in the store or map.
    """
    sid_to_pseudonym: dict[str, tuple[str, str | None]] = {
        e.student_id: (e.pseudonym, e.name_kr) for e in pseudonym_map
    }
    pseudonym_to_sid: dict[str, tuple[str, str | None]] = {
        e.pseudonym: (e.student_id, e.name_kr) for e in pseudonym_map
    }

    if re.fullmatch(r"\d{10}", student_arg):
        # student_id branch
        if student_arg not in sid_to_pseudonym:
            raise LocatedInputError(
                f"student_id {student_arg!r} not found in pseudonym map",
                expected="a known student_id",
                actual=student_arg,
            )
        pseudonym, name_kr = sid_to_pseudonym[student_arg]
        student_id = student_arg
    elif re.fullmatch(r"S\d{3,}", student_arg):
        # pseudonym branch
        if student_arg not in pseudonym_to_sid:
            raise LocatedInputError(
                f"pseudonym {student_arg!r} not found in pseudonym map",
                expected="a known pseudonym (S001 format)",
                actual=student_arg,
            )
        student_id, name_kr = pseudonym_to_sid[student_arg]
        pseudonym = student_arg
    else:
        raise LocatedInputError(
            f"--student must be a 10-digit student_id or S\\d{{3,}} pseudonym; "
            f"got {student_arg!r}",
            expected="10-digit student_id or S001 pseudonym",
            actual=student_arg,
        )

    # Validate: student must have entries in the codex.
    known_sids = {e.student_id for e in entries}
    if student_id not in known_sids:
        raise LocatedInputError(
            f"student_id {student_id!r} has no entries in the Silver store",
            expected="student with codex entries",
            actual=student_id,
        )

    return student_id, pseudonym, name_kr


def _run_query(args: argparse.Namespace) -> int:
    """Handle the ``query`` subcommand: evidence retrieval in pseudonym space.

    Loads the Silver store + pseudonym map, resolves the --student argument
    (10-digit id or S\\d{3,} pseudonym), runs answer_question, and prints each
    citation to stdout.  Optionally writes a QueryAnswer JSON with --json.
    With --reveal, also prints student_id and name_kr.

    Args:
        args: Parsed CLI arguments for the ``query`` subcommand.

    Returns:
        ``0`` on success.

    Raises:
        LocatedInputError: On boundary failures (caught by ``app`` → exit 2).
    """
    from metric_codex.retrieve.query import answer_question, load_question_set

    semester: str = args.semester
    course: str = args.course
    data_root: Path = args.data_root

    own_silver = silver_dir(semester, course, data_root=data_root)
    own_bronze = bronze_dir(semester, course, data_root=data_root)
    pseudonym_path = own_silver / "pseudonym_map.parquet"

    entries, pmap = _load_store_and_map(own_silver, pseudonym_path)

    student_id, pseudonym, name_kr = _resolve_student(args.student, entries, pmap)

    # Filter entries to this student only.
    student_entries = [e for e in entries if e.student_id == student_id]

    # Build the QueryAnswer.
    if args.question_id is not None:
        qs_path: Path = args.question_set or (own_bronze / "question_set.yaml")
        qs = load_question_set(qs_path)
        question = next((q for q in qs.questions if q.id == args.question_id), None)
        if question is None:
            raise LocatedInputError(
                f"question_id {args.question_id!r} not found in question_set",
                file=str(qs_path),
                expected="a valid question id",
                actual=args.question_id,
            )
        qa = answer_question(student_entries, pseudonym=pseudonym, question=question)
    elif args.text is not None:
        qa = answer_question(student_entries, pseudonym=pseudonym, freeform_text=args.text)
    else:
        # Neither --question-id nor --text supplied.  The argparse group is
        # required=False, so this branch IS reachable when the user omits both;
        # fail fast with a located error (→ exit 2).
        raise LocatedInputError(
            "one of --question-id or --text must be provided",
            expected="--question-id ID or --text TEXT",
            actual="(none)",
        )

    # Print: reveal header (optional), citations or no_evidence sentinel.
    if args.reveal:
        print(f"student_id: {student_id}")
        print(f"name_kr: {name_kr or '(unknown)'}")

    print(f"pseudonym: {pseudonym}")
    # F3: available_layers must appear in plain-text output (contracts/cli.md).
    layers_str = ", ".join(sorted(qa.available_layers))
    print(f"가용 층: {layers_str}")

    if qa.no_evidence:
        print("근거 없음")
    else:
        for c in qa.citations:
            obs = f", observed_at={c.observed_at}" if c.observed_at else ""
            print(f"- {c.key}: {c.value} (출처: {c.source_id}, {c.layer}{obs})")

    # Optional JSON output.
    if args.json_out is not None:
        json_path: Path = args.json_out
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(qa.model_dump(), sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    return 0


def _run_dry_run(args: argparse.Namespace) -> int:
    """Handle the ``dry-run`` subcommand: deterministic staging bundle generation.

    Loads the Silver store + pseudonym map, builds pseudonymized StudentBundles
    for every student, and writes staging/{pseudonym}.json files under the Silver
    directory.  No LLM call; no PII in output (PRIV-01/SC-004).

    Args:
        args: Parsed CLI arguments for the ``dry-run`` subcommand.

    Returns:
        ``0`` on success.

    Raises:
        LocatedInputError: On any boundary failure (caught by ``app`` → exit 2).
    """
    from metric_codex.generate.bundle import build_bundles, write_staging
    from metric_codex.retrieve.query import load_question_set

    semester: str = args.semester
    course: str = args.course
    data_root: Path = args.data_root

    own_silver = silver_dir(semester, course, data_root=data_root)
    own_bronze = bronze_dir(semester, course, data_root=data_root)
    pseudonym_path = own_silver / "pseudonym_map.parquet"

    entries, pmap = _load_store_and_map(own_silver, pseudonym_path)

    qs_path: Path = args.question_set or (own_bronze / "question_set.yaml")
    qs = load_question_set(qs_path)

    bundles = build_bundles(
        codex_entries=entries,
        pseudonym_map=pmap,
        question_set=qs,
    )

    # Arm the name scan with every known name from the local pseudonym map so a
    # leaked name fails fast before the staging file is written (PRIV-01).
    known_names = frozenset(e.name_kr for e in pmap if e.name_kr)
    written = write_staging(own_silver, bundles, known_names=known_names)

    print(f"dry-run: {len(written)} staging bundle(s) written")
    for p in written:
        print(f"  {p}")

    return 0


def _run_generate(args: argparse.Namespace) -> int:
    """Handle the ``generate`` subcommand: per-student narrative + re-identification.

    Loads the Silver store + pseudonym map, validates the map for bijection FIRST
    (PRIV-05 — a corrupt/non-bijective map aborts before ANY Gold write), builds
    pseudonymized StudentBundles, and renders one Gold markdown per student.

    With ``--backend none`` the deterministic template path runs offline (헌장 I).
    With ``--backend api``/``subscription`` the pseudonymized evidence is asserted
    PII-free, then polished through an ``InputHashCache``-wrapped backend.  If the
    api backend is unreachable: ``--require-llm`` propagates (exit 4); otherwise
    the run falls back to the template and continues (no hard stop — SC-009).

    Args:
        args: Parsed CLI arguments for the ``generate`` subcommand.

    Returns:
        ``0`` on success (or ``4`` only when api + unreachable + ``--require-llm``).

    Raises:
        LocatedInputError: On boundary failures (caught by ``app`` → exit 2).
        BackendUnreachableError: api + unreachable + ``--require-llm`` (→ exit 4).
    """
    from metric_codex.generate.backend import (
        ApiBackend,
        BackendUnreachableError,
        GenerationRequest,
        InputHashCache,
        SubscriptionBackend,
    )
    from metric_codex.generate.bundle import assert_no_pii, build_bundles
    from metric_codex.generate.narrative import render_template
    from metric_codex.generate.reidentify import (
        reidentify_and_write,
        validate_pseudonym_map,
    )
    from metric_codex.output.paths import gold_dir
    from metric_codex.retrieve.query import load_question_set

    semester: str = args.semester
    course: str = args.course
    data_root: Path = args.data_root
    backend_mode: str = args.backend

    now: str = args.now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    own_silver = silver_dir(semester, course, data_root=data_root)
    own_bronze = bronze_dir(semester, course, data_root=data_root)
    own_gold = gold_dir(semester, course, data_root=data_root)
    pseudonym_path = own_silver / "pseudonym_map.parquet"

    entries, pmap = _load_store_and_map(own_silver, pseudonym_path)

    # PRIV-05: validate the map for bijection BEFORE any Gold byte is written.
    pseudonym_index = validate_pseudonym_map(pmap)

    # MC-U02: clear the 학생별/ tree so stale mds from a prior run
    # (name changes, dropped students) cannot linger and corrupt counts.
    # Done AFTER bijection validation and BEFORE writing new files so a
    # mid-run failure leaves a consistent (partially rebuilt) tree, not a mix
    # of old and new content.
    student_dir = own_gold / "학생별"
    if student_dir.exists():
        shutil.rmtree(student_dir)

    qs_path: Path = args.question_set or (own_bronze / "question_set.yaml")
    qs = load_question_set(qs_path)

    bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)

    # Names armed for the LLM-boundary PII scan (PRIV-01).
    known_names = frozenset(e.name_kr for e in pmap if e.name_kr)

    # Optional LLM polish wiring (api/subscription).  None for --backend none.
    cache: InputHashCache | None = None
    if backend_mode in ("api", "subscription"):
        cache_dir = own_silver / "cache"
        if backend_mode == "api":
            backend = ApiBackend(model=args.model)
        else:
            responses_dir: Path = args.responses_dir or (own_silver / "staging_responses")
            backend = SubscriptionBackend(
                staging_dir=own_silver / "staging",
                responses_dir=responses_dir,
            )
        cache = InputHashCache(backend=backend, cache_dir=cache_dir)

    llm_used = False
    written: list[Path] = []

    for bundle in bundles:
        # The deterministic cited evidence (template) is BOTH the offline output
        # AND the PII-free 'facts' an LLM polishes — never raw codex rows.
        facts = render_template(bundle)

        if cache is None:
            narrative = facts
        else:
            # PRIV-01: defense at the LLM boundary — re-assert no PII on the
            # pseudonymized facts before constructing the request.
            assert_no_pii(facts, known_names=known_names)
            request = GenerationRequest(
                slot_id=bundle.pseudonym,
                prompt=(
                    "다음은 한 학생의 가명화된 학습 근거 요약이다. "
                    "근거에 없는 사실을 추가하지 말고, 지도교수가 읽기 쉽도록 "
                    "한국어로 다듬어라:\n\n" + facts
                ),
                facts=facts,
                model=args.model,
                mode=backend_mode,
            )
            try:
                response = cache.generate(request)
            except BackendUnreachableError:
                if args.require_llm:
                    raise
                # 헌장 I — no hard stop: fall back to the template and continue.
                cache = None
                narrative = facts
            else:
                # PRIV defense-in-depth: scan raw_text for 10-digit ids and emails
                # BEFORE re-identifying or writing Gold.  The model never receives
                # names (prompt carries only pseudonymized facts), so known_names
                # is omitted here.  A hit → LocatedInputError (exit 2), no Gold written.
                assert_no_pii(response.raw_text)
                narrative = response.raw_text
                llm_used = True

        out = reidentify_and_write(
            gold_dir=own_gold,
            pseudonym=bundle.pseudonym,
            narrative=narrative,
            pseudonym_index=pseudonym_index,
        )
        written.append(out)

    # Manifest update — preserve the ingest-stage provenance (input_hashes /
    # config_ids / bundle_summary) unchanged (헌장 V); update ONLY the
    # generate-owned fields.  When no prior manifest exists (generate run before
    # ingest), fall back to empty provenance + a recomputed bundle_summary.
    student_ids = sorted({e.student_id for e in entries})
    student_count = len(student_ids)

    manifest_path = own_silver / "manifest_metric-codex.json"
    if manifest_path.is_file():
        prior = read_manifest(manifest_path)
        input_hashes = prior.input_hashes
        config_ids = prior.config_ids
        bundle_summary = prior.bundle_summary
    else:
        input_hashes = {}
        config_ids = {}
        bundle_summary = AdvisorBundleSummary(
            total_students_with_codex=student_count,
            assigned_count=0,
            unassigned_sids=student_ids,
            advisor_count=0,
            per_advisor_counts={},
        )

    if backend_mode == "none" or not llm_used:
        manifest_backend = "none(template)"
        manifest_model = None
    else:
        manifest_backend = backend_mode
        manifest_model = args.model

    manifest = build_manifest(
        semester=semester,
        course_slug=course,
        input_hashes=input_hashes,
        config_ids=config_ids,
        generated_at=now,
        llm_backend=manifest_backend,
        llm_model=manifest_model,
        cache_hit_rate=cache.cache_hit_rate() if cache is not None else None,
        student_count=student_count,
        entry_count=len(entries),
        bundle_summary=bundle_summary,
    )
    write_manifest(manifest_path, manifest)

    print(f"generate: {len(written)} student narrative(s) written ({manifest_backend})")
    for p in written:
        print(f"  {p}")

    return 0


def _run_distribute(args: argparse.Namespace) -> int:
    """Handle the ``distribute`` subcommand: per-advisor bundle assembly.

    Reads the advisor roster, groups Gold student md files by advisor, copies
    each advisee's md into the advisor's own Gold subdirectory (no cross-leak),
    reports unassigned students explicitly, and updates the manifest preserving
    the prior ingest/generate provenance (constitution V).

    Args:
        args: Parsed CLI arguments for the ``distribute`` subcommand.

    Returns:
        ``0`` on success.

    Raises:
        LocatedInputError: On boundary failures (caught by ``app`` → exit 2).
    """
    from metric_codex.distribute.bundles import group_by_advisor, write_advisor_bundles
    from metric_codex.distribute.roster import load_roster
    from metric_codex.distribute.summary import (
        build_summary,
        write_unassigned_report,
    )
    from metric_codex.distribute.summary import (
        write_missing_gold_report as _write_missing_gold_report,
    )
    from metric_codex.output.paths import gold_dir

    semester: str = args.semester
    course: str = args.course
    data_root: Path = args.data_root
    now: str = args.now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    own_bronze = bronze_dir(semester, course, data_root=data_root)
    own_silver = silver_dir(semester, course, data_root=data_root)
    own_gold = gold_dir(semester, course, data_root=data_root)

    # 1) Load advisor roster.
    roster_path: Path = args.roster or (own_bronze / "지도교수배정.yaml")
    roster = load_roster(roster_path)

    # 2) Load the Silver codex to get the authoritative student set (MC-U23).
    #    The codex is the source of truth for total/assigned/unassigned counts;
    #    the on-disk md count may differ (a student can lack a Gold md if generate
    #    was interrupted or the md was manually removed).
    codex_entries, _ = read_existing_store(own_silver)
    codex_sids = sorted({e.student_id for e in codex_entries})

    # Build a sid → advisor map from the roster and classify each codex student.
    sid_to_advisor: dict[str, str] = {e.student_id: e.advisor_id for e in roster}
    roster_sids: set[str] = set(sid_to_advisor)

    # 3) Group Gold md files by advisor (disk walk) for the copy step.  This
    #    also yields the name map for the unassigned report.  The disk-derived
    #    unassigned list (2nd value) is intentionally discarded — unassigned is
    #    derived from the codex set below, not from on-disk mds (MC-U23).
    per_advisor_paths, _, names = group_by_advisor(gold_dir=own_gold, roster=roster)

    # 4) Build the codex-sourced per_advisor grouping for the summary.
    #    Assigned codex students with no Gold md are still counted as assigned
    #    but cannot be copied — they are surfaced via a separate missing-md report.
    per_advisor_sids: dict[str, list[str]] = {}
    for sid in codex_sids:
        advisor_id = sid_to_advisor.get(sid)
        if advisor_id is not None:
            per_advisor_sids.setdefault(advisor_id, []).append(sid)

    # Detect assigned codex students who have no Gold md (MC-U21).
    md_sids: set[str] = set(names)
    missing_gold: list[str] = sorted(
        sid for sid in codex_sids
        if sid in roster_sids and sid not in md_sids
    )

    # 5) Write per-advisor bundles (atomic, whole-tree clear, no cross-leak).
    write_advisor_bundles(gold_dir=own_gold, per_advisor=per_advisor_paths)

    # 6) Build summary from the codex set; write unassigned + missing-md reports.
    summary = build_summary(
        codex_sids=codex_sids,
        roster_sids=roster_sids,
        per_advisor=per_advisor_sids,
    )
    # Names map may not cover codex students who have no Gold md; extend with
    # empty entries so the unassigned report can still emit a line per sid.
    for sid in codex_sids:
        names.setdefault(sid, None)
    unassigned_sids = list(summary.unassigned_sids)  # already ASC-sorted by schema
    write_unassigned_report(gold_dir=own_gold, unassigned=unassigned_sids, names=names)
    # Written unconditionally (mirrors 미배정.md) so a previously-surfaced student
    # whose md now exists no longer lingers in a stale 미생성.md (MC-U02).
    _write_missing_gold_report(gold_dir=own_gold, missing_sids=missing_gold, names=names)

    # 7) Update manifest — preserve provenance, update bundle_summary.
    manifest_path = own_silver / "manifest_metric-codex.json"
    if manifest_path.is_file():
        prior = read_manifest(manifest_path)
        input_hashes = prior.input_hashes
        config_ids = prior.config_ids
        llm_backend = prior.llm_backend
        llm_model = prior.llm_model
        cache_hit_rate = prior.cache_hit_rate
        student_count = prior.student_count
        entry_count = prior.entry_count
    else:
        input_hashes = {}
        config_ids = {}
        llm_backend = "none(template)"
        llm_model = None
        cache_hit_rate = None
        student_count = len(codex_sids)
        entry_count = 0

    manifest = build_manifest(
        semester=semester,
        course_slug=course,
        input_hashes=input_hashes,
        config_ids=config_ids,
        generated_at=now,
        llm_backend=llm_backend,
        llm_model=llm_model,
        cache_hit_rate=cache_hit_rate,
        student_count=student_count,
        entry_count=entry_count,
        bundle_summary=summary,
    )
    write_manifest(manifest_path, manifest)

    assigned_count = summary.assigned_count
    unassigned_count = len(summary.unassigned_sids)
    advisor_count = summary.advisor_count
    print(
        f"distribute: {assigned_count} assigned, {unassigned_count} unassigned, "
        f"{advisor_count} advisor(s)"
    )

    return 0


def _run_verify(args: argparse.Namespace) -> int:
    """Handle the ``verify`` subcommand: post-hoc invariant enforcement.

    Runs every applicable check from ``metric_codex.verify.checks``.  If any
    violation is found, prints each located violation to stderr and exits 3.
    On a clean pass, prints a confirmation to stdout and exits 0.

    The check is READ-ONLY — it never writes Gold/Silver.

    Args:
        args: Parsed CLI arguments for the ``verify`` subcommand.

    Returns:
        ``0`` all invariants pass; ``3`` one or more violations detected.
    """
    from metric_codex.verify.checks import run_all_checks

    semester: str = args.semester
    course: str = args.course
    data_root: Path = args.data_root
    question_set_path: Path | None = args.question_set
    roster_path: Path | None = args.roster

    violations = run_all_checks(
        data_root=data_root,
        semester=semester,
        course_slug=course,
        question_set_path=question_set_path,
        roster_path=roster_path,
    )

    if violations:
        for v in violations:
            print(str(v), file=sys.stderr)
        return 3

    print("verify: all invariants pass")
    return 0


def _run_build(args: argparse.Namespace) -> int:
    """Run the full pipeline: ingest → generate → distribute → verify.

    Executes each stage in order.  On the first non-zero return code, prints a
    failure note to stderr and returns that code immediately (first-non-zero stop).
    A stage that raises (e.g. ``LocatedInputError`` / ``BackendUnreachableError``)
    propagates naturally to ``app()``, which also stops the sequence.

    Args:
        args: Parsed CLI arguments — the ``build`` subparser exposes the union of
            all stage-specific flags so the shared ``Namespace`` satisfies every
            handler without modification.

    Returns:
        ``0`` if all stages succeed; otherwise the first non-zero exit code from
        any stage.

    Raises:
        LocatedInputError: Propagated from ingest or distribute (→ exit 2 in app).
        BackendUnreachableError: Propagated from generate with ``--require-llm``
            (→ exit 4 in app).
    """
    stages: Sequence[tuple[str, Callable[[argparse.Namespace], int]]] = (
        ("ingest", _run_ingest),
        ("generate", _run_generate),
        ("distribute", _run_distribute),
        ("verify", _run_verify),
    )
    for name, stage in stages:
        rc = stage(args)  # a raise here propagates to app() = first-non-zero stop
        if rc != 0:
            print(f"build: {name} failed (exit {rc})", file=sys.stderr)
            return rc
        print(f"build: {name} ok", file=sys.stderr)
    return 0


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
    except BackendUnreachableError as exc:
        # BackendUnreachableError subclasses RuntimeError, so it MUST be caught
        # before the RuntimeError branch below — order matters (exit 4 only when
        # the api backend is unreachable and --require-llm was set).
        print(f"ERROR [metric-codex]: LLM backend unreachable — {exc}", file=sys.stderr)
        return 4
    except RuntimeError as exc:
        print(f"ERROR [metric-codex]: pipeline step failed — {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
