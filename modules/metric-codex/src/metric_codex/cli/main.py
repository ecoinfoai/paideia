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
from datetime import UTC, datetime
from pathlib import Path

from paideia_shared.schemas import AdvisorBundleSummary

from metric_codex.ingest.bronze_copies import (
    load_blueprint,
    load_curriculum_map,
    load_school_excel_map,
)
from metric_codex.ingest.paideia_sources import read_paideia_sources
from metric_codex.ingest.school_excel import read_school_excel
from metric_codex.output.manifest import build_manifest, write_manifest
from metric_codex.output.paths import bronze_dir, silver_dir
from metric_codex.output.sha256 import compute_sha256
from metric_codex.store.codex import accumulate, read_existing_store, write_store
from metric_codex.store.pseudonym import build_pseudonym_map, write_pseudonym_map

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
    ingest_p.add_argument(
        "--school-excel",
        type=Path,
        default=None,
        metavar="PATH",
        help="학교 성적·출석 xlsx 경로 (기본: Bronze '성적출석.xlsx')",
    )
    ingest_p.add_argument(
        "--school-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="성적출석_map.yaml 경로 (기본: Bronze '성적출석_map.yaml')",
    )
    ingest_p.add_argument(
        "--blueprint",
        type=Path,
        default=None,
        metavar="PATH",
        help="(선택) examen blueprint.yaml — provenance 기록 전용",
    )
    ingest_p.add_argument(
        "--curriculum-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="(선택) curriculum_map.yaml — provenance 기록 전용",
    )
    ingest_p.add_argument(
        "--now",
        type=str,
        default=None,
        metavar="ISO8601",
        help=(
            "ingested_at/generated_at 으로 주입할 ISO-8601 UTC 타임스탬프. "
            "미지정 시 datetime.now(UTC) — 비결정적이므로 재현 테스트에는 명시 권장."
        ),
    )

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

    # 1) School Excel (minimal layer) — fail-fast on a missing/malformed file.
    excel_map = load_school_excel_map(school_map)
    school_result = read_school_excel(
        school_excel,
        excel_map,
        ingested_at=now,
        source_path=str(school_excel.relative_to(data_root)),
    )

    # 2) Upstream paideia Silver (rich layer) — missing dirs degrade silently.
    paideia_results = read_paideia_sources(
        immersio_silver_dir=immersio_silver if immersio_silver.is_dir() else None,
        needsmap_silver_dir=needsmap_silver if needsmap_silver.is_dir() else None,
        semester=semester,
        data_root=data_root,
        ingested_at=now,
    )

    results = [school_result, *paideia_results]

    # 3) Optional provenance: validate blueprint/curriculum (fail-fast) and
    #    record their digests only — they are not used for entry construction.
    config_ids: dict[str, str] = {school_map.name: compute_sha256(school_map)}
    if args.blueprint is not None:
        load_blueprint(args.blueprint)
        config_ids[args.blueprint.name] = compute_sha256(args.blueprint)
    if args.curriculum_map is not None:
        load_curriculum_map(args.curriculum_map)
        config_ids[args.curriculum_map.name] = compute_sha256(args.curriculum_map)

    # 4) Accumulate into the (possibly pre-existing) Silver store.
    existing_entries, existing_records = read_existing_store(own_silver)
    entries, records = accumulate(results, existing_entries, existing_records)
    write_store(own_silver, entries, records)

    # 5) Local-only pseudonym map over the union of all observed identities.
    identities: dict[str, str | None] = {}
    for result in results:
        for student_id, name_kr in result.identities.items():
            # Keep a non-None name if any source supplies one.
            if name_kr is not None or student_id not in identities:
                identities[student_id] = name_kr
    write_pseudonym_map(own_silver / "pseudonym_map.parquet", build_pseudonym_map(identities))

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
