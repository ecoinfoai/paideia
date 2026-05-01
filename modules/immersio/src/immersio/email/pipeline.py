"""immersio-email orchestration pipeline (T048).

Phase A→B→C→D→E orchestrator. Dry-run mode (``--send`` absent) writes
.eml previews + manifest + report and returns exit code 0. Live send
modes (US2 self-test, US3 production) land in subsequent phases.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchReportData,
    DispatchStatus,
    EmailManifest,
    EmailManifestCounts,
    EmailManifestInputs,
    EmailManifestOutputs,
    EmailMappingEntry,
    StudentPDFBundle,
)

from . import __version__ as EMAIL_VERSION
from .archival import archive_previous_run
from .composer import build_email_draft
from .manifest import write_email_manifest
from .master_check import (
    MasterMismatchError,
    MasterMissingError,
    cross_check_with_master,
)
from .pdf_scan import PDFScanError, scan_pdf_directory
from .pdf_verify import verify_pdf_body_contains_student_id
from .preview import write_eml_preview_files
from .profile import ProfileError, ProfileLoader
from .report import write_dispatch_report_md
from .roster import RosterError, load_email_mapping, write_mapping_silver

KST = timezone(timedelta(hours=9))


def _default_paths(args: argparse.Namespace) -> dict[str, Path]:
    """Resolve canonical paths from semester/course unless overridden."""
    semester = args.semester
    course = args.course
    return {
        "bronze_csv": (
            Path(args.bronze_csv)
            if args.bronze_csv is not None
            else Path("data/bronze/진단평가/진단평가_1차_결과.csv")
        ),
        "gold_pdf_dir": (
            Path(args.gold_pdf_dir)
            if args.gold_pdf_dir is not None
            else Path(f"data/gold/immersio/{semester}-{course}/이메일_발송용")
        ),
        "silver_master": (
            Path(args.silver_master)
            if args.silver_master is not None
            else Path("data/silver/immersio/학생마스터.parquet")
        ),
        "silver_email_dir": Path(f"data/silver/immersio/{semester}-{course}"),
        "gold_email_dir": Path(f"data/gold/immersio/{semester}-{course}"),
        "preview_dir": Path(
            f"tmp/immersio_email_preview/{semester}-{course}"
        ),
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_sent_date(arg: str | None) -> date:
    if arg is None:
        return datetime.now(tz=KST).date()
    return date.fromisoformat(arg)


def run_email_dispatch(args: argparse.Namespace) -> int:
    """Drive Phase A→E orchestration end-to-end (T048)."""
    if args.self_test is not None and not args.send:
        print(
            "ERROR [immersio email]: --self-test requires --send "
            "(self-test mode only meaningful when actually sending).",
            file=sys.stderr,
        )
        return 2

    try:
        loader = ProfileLoader()
        profile = loader.load(args.profile)
    except ProfileError as exc:
        print(f"ERROR [immersio email]: profile — {exc}", file=sys.stderr)
        return 1

    paths = _default_paths(args)
    try:
        sent_date = _parse_sent_date(args.sent_date)
    except ValueError as exc:
        print(
            f"ERROR [immersio email]: invalid --sent-date — {exc}",
            file=sys.stderr,
        )
        return 1

    course_name_kr = _resolve_course_name_kr(args)

    mode = (
        DispatchMode.TEST
        if profile.profile_kind == "test"
        else DispatchMode.PRODUCTION
    )
    cohort = (
        CohortLabel(args.cohort) if getattr(args, "cohort", None) else CohortLabel.ALL
    )

    if args.send:
        try:
            archive_previous_run(paths["gold_email_dir"])
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR [immersio email]: archival — {exc}", file=sys.stderr)
            return 4

    # Phase A — roster
    try:
        entries = load_email_mapping(paths["bronze_csv"])
    except RosterError as exc:
        print(
            f"ERROR [immersio email]: phase A roster — {exc}", file=sys.stderr
        )
        return 3 if "not found" in str(exc) else 1

    paths["silver_email_dir"].mkdir(parents=True, exist_ok=True)
    silver_mapping_path = (
        paths["silver_email_dir"] / "학번_이메일_매핑.parquet"
    )
    write_mapping_silver(entries, silver_mapping_path)

    # Phase B — pdf scan
    try:
        bundles = scan_pdf_directory(paths["gold_pdf_dir"])
    except PDFScanError as exc:
        print(
            f"ERROR [immersio email]: phase B pdf-scan — {exc}",
            file=sys.stderr,
        )
        return 4

    # Phase C — master cross-check
    try:
        matched, missing_in_master = cross_check_with_master(
            bundles, paths["silver_master"]
        )
    except MasterMismatchError as exc:
        print(
            f"ERROR [immersio email]: phase C master — {exc}",
            file=sys.stderr,
        )
        return 4
    except MasterMissingError as exc:
        print(
            f"ERROR [immersio email]: phase C master — {exc}",
            file=sys.stderr,
        )
        return 3

    # Phase D — pdf body verify
    attachment_max = profile.operational_defaults.attachment_max_bytes
    verified = [
        verify_pdf_body_contains_student_id(
            b, attachment_max_bytes=attachment_max
        )
        for b in matched
    ]
    verify_by_sid = {v.bundle.student_id: v for v in verified}
    missing_sids = {b.student_id for b in missing_in_master}

    # Phase E — composer + log
    started_at = datetime.now(tz=KST)
    log_rows: list[DispatchLogRow] = []
    drafts_with_pdfs: list[tuple] = []
    entries_by_sid: dict[str, EmailMappingEntry] = {
        e.student_id: e for e in entries
    }

    for bundle in bundles:
        sid = bundle.student_id

        if sid in missing_sids:
            log_rows.append(
                _skip_row(
                    bundle=bundle,
                    email="",
                    started_at=started_at,
                    mode=mode,
                    error_kind="email_not_found",
                    error_detail="student_id absent from master",
                    exam_name=args.exam_name,
                    cohort=cohort,
                )
            )
            continue

        verify_result = verify_by_sid.get(sid)
        if verify_result is None or not verify_result.ok:
            kind = (
                verify_result.error_kind
                if verify_result is not None
                else "pdf_no_student_id"
            )
            email = (
                str(entries_by_sid[sid].email)
                if sid in entries_by_sid
                else ""
            )
            status = (
                DispatchStatus.FAILED
                if kind == "attachment_size_exceeded"
                else DispatchStatus.SKIPPED
            )
            log_rows.append(
                _skip_row(
                    bundle=bundle,
                    email=email,
                    started_at=started_at,
                    mode=mode,
                    error_kind=kind,
                    error_detail=f"phase D check failed ({kind})",
                    exam_name=args.exam_name,
                    cohort=cohort,
                    status=status,
                )
            )
            continue

        entry = entries_by_sid.get(sid)
        if entry is None:
            log_rows.append(
                _skip_row(
                    bundle=bundle,
                    email="",
                    started_at=started_at,
                    mode=mode,
                    error_kind="invalid_email",
                    error_detail="student_id has no diagnostic CSV row",
                    exam_name=args.exam_name,
                    cohort=cohort,
                )
            )
            continue

        draft = build_email_draft(
            profile=profile,
            mapping_entry=entry,
            pdf_bundle=bundle,
            course_name_kr=course_name_kr,
            course_slug=args.course,
            semester=args.semester,
            exam_name=args.exam_name,
            sent_date=sent_date,
            mode=mode,
        )
        drafts_with_pdfs.append((draft, bundle))
        log_rows.append(
            _ok_row(
                draft=draft,
                bundle=bundle,
                started_at=started_at,
                mode=mode,
                status=DispatchStatus.DRY_RUN
                if not args.send
                else DispatchStatus.SUCCESS,
                exam_name=args.exam_name,
                cohort=cohort,
            )
        )

    # Dry-run vs send
    paths["gold_email_dir"].mkdir(parents=True, exist_ok=True)

    if not args.send:
        preview_dir = paths["preview_dir"]
        if profile.profile_kind == "test":
            preview_dir = preview_dir / "_test"
        write_eml_preview_files(drafts_with_pdfs, preview_dir)
    else:
        print(
            "ERROR [immersio email]: live send modes (--send) land in spec "
            "006 Phase 4 (US2) and Phase 5 (US3). v0.1.0 Phase 3 ships "
            "dry-run only.",
            file=sys.stderr,
        )
        return 2

    # Manifest + log + report
    counts = _aggregate_counts(log_rows)
    completed_at = datetime.now(tz=KST)
    bronze_sha = _sha256_file(paths["bronze_csv"])
    master_sha = (
        _sha256_file(paths["silver_master"])
        if paths["silver_master"].is_file()
        else "0" * 64
    )
    manifest = EmailManifest(
        semester=args.semester,
        course_slug=args.course,
        course_name_kr=course_name_kr,
        exam_name=args.exam_name,
        sent_date_kst=sent_date,
        mode=mode,
        profile_name=profile.profile_name,
        profile_kind=profile.profile_kind,
        profile_secrets_ref_env_var_name=profile.secrets_ref.service_account_json_path_env,
        inputs=EmailManifestInputs(
            bronze_csv_path=str(paths["bronze_csv"].resolve()),
            bronze_csv_sha256=bronze_sha,
            gold_pdf_dir_path=str(paths["gold_pdf_dir"].resolve()),
            gold_pdf_count=len(bundles),
            silver_master_path=str(paths["silver_master"].resolve()),
            silver_master_sha256=master_sha,
        ),
        outputs=EmailManifestOutputs(
            silver_mapping_path=str(silver_mapping_path.resolve()),
            silver_mapping_rows=len(entries),
            dispatch_log_path=str(
                (paths["gold_email_dir"] / "메일_발송로그.csv").resolve()
            ),
            report_md_path=str(
                (paths["gold_email_dir"] / "메일_발송보고서.md").resolve()
            ),
            preview_dir_path=str(paths["preview_dir"].resolve())
            if not args.send
            else "",
        ),
        counts=counts,
        tool_version=EMAIL_VERSION,
        started_at_kst=started_at,
        completed_at_kst=completed_at,
    )
    write_email_manifest(manifest, paths["gold_email_dir"])

    log_csv_path = paths["gold_email_dir"] / "메일_발송로그.csv"
    if profile.profile_kind == "test":
        log_csv_path = paths["gold_email_dir"] / "_test" / "메일_발송로그.csv"
    log_csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_log_csv(log_rows, log_csv_path)

    summary = {s: counts.model_dump()[s.value] for s in DispatchStatus}
    write_dispatch_report_md(
        DispatchReportData(
            manifest=manifest,
            summary_table=summary,
            failed_rows=[
                r for r in log_rows if r.status == DispatchStatus.FAILED
            ],
            skipped_rows=[
                r for r in log_rows if r.status == DispatchStatus.SKIPPED
            ],
            report_generated_at_kst=completed_at,
        ),
        paths["gold_email_dir"],
    )

    if getattr(args, "verbose", False):
        print(
            f"[immersio email] mode={mode.value} dry_run={counts.dry_run} "
            f"skipped={counts.skipped} failed={counts.failed}",
            file=sys.stdout,
        )
    return 0 if counts.failed == 0 else 8


def _resolve_course_name_kr(args: argparse.Namespace) -> str:
    """Resolve course_name_kr from the immersio mapping yaml; fallback = slug."""
    mapping_path = Path(f"data/bronze/매핑/{args.course}.yaml")
    if mapping_path.is_file():
        import yaml

        data = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        meta = data.get("metadata") or {}
        kr = meta.get("course_name_kr")
        if isinstance(kr, str) and kr.strip():
            return kr.strip()
    return args.course


def _ok_row(
    *,
    draft,
    bundle: StudentPDFBundle,
    started_at: datetime,
    mode: DispatchMode,
    status: DispatchStatus,
    exam_name: str,
    cohort: CohortLabel,
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=draft.student_id,
        name_kr=draft.name_kr,
        email=draft.to_header,
        pdf_filename=bundle.pdf_filename,
        pdf_sha256=bundle.pdf_sha256,
        attempt_at_kst=started_at,
        mode=mode,
        status=status,
        smtp_message_id=draft.message_id,
        error_kind="",
        error_detail="",
        exam_name=exam_name,
        cohort=cohort,
    )


def _skip_row(
    *,
    bundle: StudentPDFBundle,
    email: str,
    started_at: datetime,
    mode: DispatchMode,
    error_kind: str,
    error_detail: str,
    exam_name: str,
    cohort: CohortLabel,
    status: DispatchStatus = DispatchStatus.SKIPPED,
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=bundle.student_id,
        name_kr=bundle.name_kr,
        email=email,
        pdf_filename=bundle.pdf_filename,
        pdf_sha256=bundle.pdf_sha256,
        attempt_at_kst=started_at,
        mode=mode,
        status=status,
        smtp_message_id="",
        error_kind=error_kind,
        error_detail=error_detail[:200],
        exam_name=exam_name,
        cohort=cohort,
    )


def _aggregate_counts(rows: list[DispatchLogRow]) -> EmailManifestCounts:
    counts = {s: 0 for s in DispatchStatus}
    for row in rows:
        counts[row.status] += 1
    return EmailManifestCounts(
        success=counts[DispatchStatus.SUCCESS],
        skipped=counts[DispatchStatus.SKIPPED],
        failed=counts[DispatchStatus.FAILED],
        temporary_failure=counts[DispatchStatus.TEMPORARY_FAILURE],
        dry_run=counts[DispatchStatus.DRY_RUN],
        test_dummy=counts[DispatchStatus.TEST_DUMMY],
    )


def _write_log_csv(rows: list[DispatchLogRow], path: Path) -> None:
    """Append-only csv write with the locked 13-column header."""
    is_new = not path.is_file()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(DispatchLogRow.COLUMN_ORDER)
        )
        if is_new:
            writer.writeheader()
        for row in rows:
            dump = row.model_dump(mode="json")
            writer.writerow({c: dump[c] for c in DispatchLogRow.COLUMN_ORDER})


__all__ = ["run_email_dispatch"]
