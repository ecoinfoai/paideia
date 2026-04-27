"""needs-map CLI entry point (T032 skeleton; phase dispatchers wired in T057/T075/T106).

Exit codes per ``specs/002-needs-map-v0-1-0/contracts/cli.md``:
    0 — Success (all requested phases produced + manifest written)
    1 — Argument error (bad CLI flag values)
    2 — Input contract violation (Silver loader / mapping V1-V6)
    3 — Output contract violation (Pydantic refusal at write time)
    4 — Archival or data-integrity failure (no partial outputs)
    5 — LLM forced+missing (v0.2+; not used in v0.1.0)
   99 — Internal bug (uncaught exception)

LLM auto-disable from ``--no-llm`` or absent ``ANTHROPIC_API_KEY`` env follows
the success path (exit 0). Phase 2 design alignment §3.2 priority:
``--no-llm`` > env presence > active.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from .. import fonts as _fonts_module
from ..archive.mover import ArchivalError
from ..fonts import KoreanFontUnavailableError
from ..io.mapping import MappingKindError, MappingVersionError
from ..pipeline import NeedsMapArgs, run_needs_map

_ALLOWED_PHASE_RANGES = {
    "A-B": frozenset({"A", "B"}),
    "A-C": frozenset({"A", "B", "C"}),
    "A-D": frozenset({"A", "B", "C", "D"}),
    "A-E": frozenset({"A", "B", "C", "D", "E"}),
    "A-F": frozenset({"A", "B", "C", "D", "E", "F"}),
    "all": frozenset({"A", "B", "C", "D", "E", "F"}),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paideia-needs-map",
        description=(
            "사전진단 분석 모듈 — paideia v0.1.0. "
            "ingest Silver 3종(DiagnosticResponse + StudentMaster + DiagnosticMappingConfig)을 "
            "입력으로 받아 Phase A-F를 결정론적으로 실행."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)
    run = sub.add_parser("run", help="Execute one needs-map run.")
    run.add_argument(
        "--semester",
        required=True,
        help="학기 코드 (예: 2026-1). SemesterCode 패턴 검증.",
    )
    run.add_argument(
        "--course",
        required=True,
        help="교과목 kebab-case slug (예: anatomy). CourseSlug 패턴 검증.",
    )
    run.add_argument(
        "--phases",
        choices=sorted(_ALLOWED_PHASE_RANGES.keys()),
        default="all",
        help="실행 Phase 범위. default 'all' (= A-F).",
    )
    run.add_argument(
        "--k",
        type=int,
        default=None,
        help=(
            "군집 수 강제. 허용 [2, 6]. k=1은 표본부족 자동 폴백 전용 "
            "(인자로 1을 주면 exit 1)."
        ),
    )
    run.add_argument(
        "--no-llm",
        action="store_true",
        help="LLM 옵션 일체 비활성. 모든 LLM 호출 부위는 룰/사전/템플릿 폴백.",
    )
    run.add_argument(
        "--llm-provider",
        choices=("anthropic", "openai"),
        default=os.environ.get("PAIDEIA_LLM_PROVIDER", "anthropic"),
        help="LLM 제공자. v0.1.0 구현은 anthropic만. env PAIDEIA_LLM_PROVIDER override.",
    )
    run.add_argument(
        "--llm-model",
        default=os.environ.get("PAIDEIA_LLM_MODEL", "claude-sonnet-4-6"),
        help="모델 ID. env PAIDEIA_LLM_MODEL override.",
    )
    run.add_argument(
        "--input-root",
        type=Path,
        default=Path("./data"),
        help="Bronze/Silver 입력 루트.",
    )
    run.add_argument(
        "--output-root",
        type=Path,
        default=Path("./data"),
        help="Silver/Gold 출력 루트.",
    )
    run.add_argument(
        "--keyword-language",
        default="ko",
        help="키워드 사전 언어 (ISO 639-1).",
    )
    run.add_argument(
        "--seed",
        type=int,
        default=int(os.environ.get("PAIDEIA_RANDOM_SEED", "42")),
        help="난수 seed. env PAIDEIA_RANDOM_SEED override.",
    )
    run.add_argument("--dry-run", action="store_true", help="입력 검증·계획만 출력.")
    run.add_argument("--verbose", action="store_true", help="DEBUG 로그.")
    return parser


def _resolve_llm_enabled(no_llm: bool) -> bool:
    """``--no-llm`` > env presence (Phase 2 design alignment §3.2).

    Returns True iff LLM is *enabled* for this run. ``--no-llm`` always wins;
    otherwise we require ``ANTHROPIC_API_KEY`` to be set (non-empty).
    """
    if no_llm:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _resolve_phases(phase_range: str) -> frozenset[str]:
    return _ALLOWED_PHASE_RANGES[phase_range]


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Returns exit code (cli.md table)."""
    parser = _build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse calls sys.exit on bad args; map to CLI exit 1.
        return int(exc.code) if isinstance(exc.code, int) else 1

    # T057/T075/T106 will dispatch by ns.phases. T032 only validates argument
    # shape and constructs NeedsMapArgs so cli_smoke (T034) reaches the
    # NotImplementedError stub — the deliberate RED signal for Phase 3 entry.

    if ns.k is not None and ns.k == 1:
        sys.stderr.write(
            "ERROR [needs-map] --k=1 is reserved for the sample-too-small auto-fallback "
            "path (FR-010); operators cannot force k=1 via the CLI.\n"
        )
        return 1
    if ns.k is not None and not (2 <= ns.k <= 6):
        sys.stderr.write(
            f"ERROR [needs-map] --k={ns.k} out of allowed range [2, 6].\n"
        )
        return 1

    # v0.1.1 US1 (T023) — pre-flight Korean font check. MUST run before any
    # output directory or file is touched so a font-missing failure is
    # atomic (FR-005). Resolved via the module attribute so test fixtures
    # can monkeypatch ``needs_map.fonts.resolve_korean_font_paths``.
    try:
        _fonts_module.resolve_korean_font_paths()
    except KoreanFontUnavailableError as exc:
        sys.stderr.write(f"{exc}\n")
        return 6

    try:
        args = NeedsMapArgs(
            semester=ns.semester,
            course_slug=ns.course,
            phases=_resolve_phases(ns.phases),
            input_root=ns.input_root,
            output_root=ns.output_root,
            seed=ns.seed,
            k_override=ns.k,
            llm_enabled=_resolve_llm_enabled(ns.no_llm),
            llm_provider=ns.llm_provider,
            llm_model=ns.llm_model,
            keyword_language=ns.keyword_language,
            dry_run=ns.dry_run,
            verbose=ns.verbose,
        )
    except ValidationError as exc:
        sys.stderr.write(
            f"ERROR [needs-map] argument validation failed:\n{exc}\n"
        )
        return 1

    sys.stdout.write(
        f"[needs-map 0.1.0] semester={args.semester} course={args.course_slug} "
        f"phases={sorted(args.phases)}\n"
    )

    try:
        manifest = run_needs_map(args)
    except NotImplementedError as exc:
        # All 6 phases are wired (T056 A+B, T074 C, T105 D-F). This branch
        # only triggers if a future phase is added without a corresponding
        # implementation — kept defensive.
        sys.stderr.write(f"ERROR [needs-map] not yet implemented: {exc}\n")
        return 99
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR [needs-map] input missing: {exc}\n")
        return 2
    except ArchivalError as exc:
        sys.stderr.write(f"ERROR [needs-map] archival failed: {exc}\n")
        return 4
    except (MappingVersionError, MappingKindError) as exc:
        # v0.1.1 mapping loader (T018) raises these as ValueError subclasses
        # carrying an operator-actionable multi-line block in ``args[0]``
        # (per contracts/cli.md "매핑 YAML kind 검증 실패 메시지 형식" and
        # the v2 upgrade hint). Route to exit 1 (input validation failed)
        # so the CLI does not hide them behind the generic exit-99 path.
        sys.stderr.write(f"{exc}\n")
        return 1
    except ValidationError as exc:
        sys.stderr.write(f"ERROR [needs-map] contract violation: {exc}\n")
        # T056-validated input contract failures hit this path; the wiring
        # tasks T074/T105 will refine output-validation routing to exit 3.
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"ERROR [needs-map] internal error: {exc}\n")
        return 99

    for entry in manifest.rows_per_phase:
        sys.stdout.write(
            f"[needs-map] phase={entry.phase} rows_written={entry.rows_written}\n"
        )
    if manifest.cluster_k_used is not None:
        sil = (
            f"{manifest.cluster_silhouette_used:.3f}"
            if manifest.cluster_silhouette_used is not None
            else "n/a"
        )
        sys.stdout.write(
            f"[needs-map] cluster k_used={manifest.cluster_k_used} silhouette={sil}\n"
        )
        if manifest.weak_structure_warning:
            sys.stdout.write(
                "[needs-map] WARNING: cluster structure weak (silhouette < 0.2)\n"
            )
    if manifest.free_text_dictionary_match_rate is not None:
        sys.stdout.write(
            f"[needs-map] free_text dictionary_match_rate="
            f"{manifest.free_text_dictionary_match_rate:.3f}\n"
        )
        if manifest.dictionary_language_mismatch_warning:
            sys.stdout.write(
                "[needs-map] WARNING: dictionary language mismatch suspected (rate < 0.3)\n"
            )
    for stat in manifest.llm_calls:
        sys.stdout.write(
            f"[needs-map] llm site={stat.site} attempted={stat.attempted} "
            f"succeeded={stat.succeeded} fallback={stat.fallback}\n"
        )
    if manifest.previous_run_archive_path:
        sys.stdout.write(
            f"[needs-map] previous_run_archive: {manifest.previous_run_archive_path}\n"
        )
    sys.stdout.write("[needs-map] DONE\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
