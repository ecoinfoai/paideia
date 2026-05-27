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
from datetime import date, datetime, timedelta, timezone
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
from .cohort_filter import (
    CohortError,
    filter_by_cohort,
    write_cohort_md,
    write_cohort_silver,
)
from .composer import build_email_draft
from .confirm_gate import ConfirmGateAborted, confirm_first_n
from .log import (
    DispatchLockError,
    RetryMode,
    _latest_status_by_sid,
    append_dispatch_log_row,
    idempotent_skip_filter,
    mask_secrets_in_error_detail,
    read_dispatch_log,
)
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
            else Path(
                # post-release fix: paideia immersio Phase 0 ingest writes
                # `student_master.parquet` (English filename, course-scoped),
                # not `학생마스터.parquet` (Korean, course-agnostic) which
                # spec mistakenly assumed.
                f"data/silver/immersio/{semester}-{course}/student_master.parquet"
            )
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

    # T089 — TestProfile mode override: use dummy_fixture_dir as PDF
    # source, route outputs to _test/ subtree. Reject explicit
    # --bronze-csv / --gold-pdf-dir overrides (those are operator
    # production paths and meaningless under a test profile).
    if profile.profile_kind == "test":
        if args.bronze_csv is not None or args.gold_pdf_dir is not None:
            print(
                "ERROR [immersio email]: --bronze-csv / --gold-pdf-dir are "
                "not allowed with a test profile (TestProfile uses "
                "dummy_fixture_dir + recipient_pool).",
                file=sys.stderr,
            )
            return 2
        # Use the TestProfile-declared dummy fixture dir as the PDF source.
        # The bronze CSV is auto-generated below from dummy_students +
        # recipient_pool — we still write to a synthetic CSV path so the
        # roster phase reads canonical UTF-8/ISO timestamps.
        from pathlib import Path as _Path

        paths["gold_pdf_dir"] = _Path(str(profile.dummy_fixture_dir))

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

    # v0.1.1 (T014): dry-run vs send 산출 파일 분리 (FR-C03a/b/c).
    # Dry-run 은 ``메일_발송로그_dryrun.csv`` + ``메일_발송보고서_dryrun.md``
    # 만 truncate-write 하고 send-mode 파일 (``메일_발송로그.csv`` 등) 은
    # 미터치. Idempotent skip 판정 용 *읽기* path 는 항상 send-mode csv
    # (dry-run 도 prior --send 의 결과를 봐야 함, contracts/dry_run_outputs.md §2).
    is_dry_run = not args.send

    # Read the prior dispatch log BEFORE archival moves it (US4 idempotent
    # re-run depends on knowing which students already succeeded).
    prior_log_csv_path = paths["gold_email_dir"] / "메일_발송로그.csv"
    if profile.profile_kind == "test":
        prior_log_csv_path = (
            paths["gold_email_dir"] / "_test" / "메일_발송로그.csv"
        )
    prior_log_rows: list[DispatchLogRow] = []
    if prior_log_csv_path.is_file():
        try:
            prior_log_rows = read_dispatch_log(prior_log_csv_path)
        except OSError as exc:
            print(
                f"ERROR [immersio email]: cannot read prior dispatch log "
                f"{prior_log_csv_path}: {exc}",
                file=sys.stderr,
            )
            return 3

    if args.send:
        try:
            archive_previous_run(paths["gold_email_dir"])
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR [immersio email]: archival — {exc}", file=sys.stderr)
            return 4

    # T089 — TestProfile auto-generates a synthetic bronze CSV from
    # dummy_students × recipient_pool (1:1 by sorted student_id ↔ pool
    # order — TC-007). The CSV is written to a deterministic test path
    # so Phase A reads it normally.
    if profile.profile_kind == "test":
        synthetic_bronze = (
            paths["silver_email_dir"] / "_test_bronze_synthetic.csv"
        )
        synthetic_bronze.parent.mkdir(parents=True, exist_ok=True)
        from csv import writer as _csv_writer

        sorted_students = sorted(
            profile.dummy_students, key=lambda s: s.student_id
        )
        # recipient_pool is treated as parallel — same length as
        # dummy_students per TestProfile validator
        with synthetic_bronze.open(
            "w", encoding="utf-8", newline=""
        ) as fh:
            w = _csv_writer(fh)
            w.writerow(["타임스탬프", "사용자 이름", "학번"])
            for student, recipient in zip(
                sorted_students, profile.recipient_pool, strict=True
            ):
                w.writerow(
                    [
                        "2026/03/03 11:03:36 AM GMT+9",
                        str(recipient),
                        student.student_id,
                    ]
                )
        paths["bronze_csv"] = synthetic_bronze

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

    # Phase A.5 — cohort filter (US6 / FR-H02/H06).
    # Reads 학생지표.parquet → partitions students into low_score / rest.
    # Writes 2 silver parquets + 3 cohort 명단 md (regardless of dry-run
    # / send mode), then narrows ``entries`` to the requested cohort.
    cohort_score_unavailable_sids: set[str] = set()
    # T089 post-release fix: TestProfile mode skips cohort filter entirely.
    # Dummy students are synthetic and have no entry in production
    # 학생지표.parquet — running cohort_filter would classify them as
    # score_unavailable and block dispatch (FR-G07 + TC-003 intent:
    # cohort分類 is for real students; test profile validates rendering only).
    student_metrics_path: Path | None = None
    if profile.profile_kind != "test":
        student_metrics_path = (
            Path(args.silver_student_metrics)
            if getattr(args, "silver_student_metrics", None) is not None
            else paths["silver_email_dir"] / "학생지표.parquet"
        )
    if (
        student_metrics_path is not None
        and not student_metrics_path.is_file()
        and cohort != CohortLabel.ALL
    ):
        # AV-C10 fail-fast: explicit --cohort low_score|rest with missing
        # 학생지표.parquet would silently fall back to "all" mode without
        # this guard — a serious operator-confusion risk (the operator
        # *intended* a partial send but receives the full roster).
        print(
            f"ERROR [immersio email]: --cohort {cohort.value} requires "
            f"학생지표.parquet at {student_metrics_path} (run "
            f"`immersio analyze` first or pass --silver-student-metrics).",
            file=sys.stderr,
        )
        return 3

    if student_metrics_path is not None and student_metrics_path.is_file():
        try:
            cohort_result = filter_by_cohort(
                entries, student_metrics_path, cohort
            )
        except CohortError as exc:
            print(
                f"ERROR [immersio email]: phase A.5 cohort — {exc}",
                file=sys.stderr,
            )
            return 3
        # Filter mapping_entries to only the requested cohort (or all).
        entries = cohort_result.keep_entries
        cohort_score_unavailable_sids = set(cohort_result.unavailable_sids)
        # Write cohort silvers + md regardless of mode (operator
        # planning artefact independent of send vs dry-run).
        cohort_silver_dir = paths["silver_email_dir"]
        if cohort_result.low_rows:
            write_cohort_silver(
                cohort_result.low_rows,
                cohort_silver_dir / "cohort_저득점.parquet",
            )
        if cohort_result.rest_rows:
            write_cohort_silver(
                cohort_result.rest_rows,
                cohort_silver_dir / "cohort_나머지.parquet",
            )
        write_cohort_md(
            cohort_result.low_rows,
            cohort_result.rest_rows,
            paths["gold_email_dir"],
        )

    # Phase B — pdf scan
    try:
        bundles = scan_pdf_directory(paths["gold_pdf_dir"])
    except PDFScanError as exc:
        print(
            f"ERROR [immersio email]: phase B pdf-scan — {exc}",
            file=sys.stderr,
        )
        return 4

    # Phase C — master cross-check. T089: TestProfile skips master
    # cross-check entirely (dummy students aren't in production master).
    if profile.profile_kind == "test":
        matched = list(bundles)
        missing_in_master = []
    else:
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

    # Phase D.5 — idempotent skip (US3 / US4 production re-runs).
    is_self_test = bool(args.send and args.self_test is not None)
    # v0.1.1 (T014): dry-run 은 write 만 ``_dryrun.csv`` 로 분기, *읽기*
    # (idempotent skip prior log 조회) 는 항상 send-mode csv. send 모드는
    # v0.1.0 그대로 — 같은 path 로 읽고 append.
    send_log_csv_path = paths["gold_email_dir"] / "메일_발송로그.csv"
    dryrun_log_csv_path = (
        paths["gold_email_dir"] / "메일_발송로그_dryrun.csv"
    )
    if profile.profile_kind == "test":
        send_log_csv_path = (
            paths["gold_email_dir"] / "_test" / "메일_발송로그.csv"
        )
        dryrun_log_csv_path = (
            paths["gold_email_dir"] / "_test" / "메일_발송로그_dryrun.csv"
        )
    log_csv_path = (
        dryrun_log_csv_path if is_dry_run else send_log_csv_path
    )
    # v0.1.1 (T015, FR-C03d + contracts/dry_run_outputs.md §3): dry-run
    # report md → ``메일_발송보고서_dryrun.md`` so the send-mode report is
    # never overwritten by a dry-run preview. Resolved early so the
    # manifest's ``outputs.report_md_path`` (below) can point at the same
    # file the report writer (further down) emits.
    report_md_filename = (
        "메일_발송보고서_dryrun.md" if is_dry_run else "메일_발송보고서.md"
    )

    retry_mode = _resolve_retry_mode(args)
    if args.send and not is_self_test:
        # Use the log snapshot captured BEFORE archival (above) so the
        # filter sees yesterday's success rows even after archival has
        # moved them to _archive/.
        all_sids = [b.student_id for b in bundles]
        keep_sids = set(
            idempotent_skip_filter(all_sids, prior_log_rows, mode=retry_mode)
        )
        bundles = [b for b in bundles if b.student_id in keep_sids]

    # Phase E — composer + log. ``override_to`` is set when self-test
    # mode is active (US2): all drafts share the operator's own email
    # and the student's email is *not used at all* (FR-C05).
    operator_to: str | None = profile.sender.email if is_self_test else None

    # M3 advisory: --created-at-utc external override pins manifest
    # started_at/completed_at to a fixed UTC timestamp so re-runs of
    # the same input produce byte-identical manifest_email.json. When
    # absent, the wall clock is used (matches prior behaviour).
    created_at_override: datetime | None = None
    if getattr(args, "created_at_utc", None) is not None:
        try:
            override_str = args.created_at_utc
            if not override_str.endswith("Z"):
                raise ValueError(
                    f"--created-at-utc must end with 'Z' (UTC) — got "
                    f"{override_str!r}"
                )
            created_at_override = datetime.fromisoformat(
                override_str.replace("Z", "+00:00")
            ).astimezone(KST)
        except ValueError as exc:
            print(
                f"ERROR [immersio email]: invalid --created-at-utc — {exc}",
                file=sys.stderr,
            )
            return 1
    # v0.1.1 (T014, FR-C03a + contracts/dry_run_outputs.md §8): dry-run
    # csv 의 truncate-write 는 *결정적* 이어야 — 같은 input + 같은
    # ``--sent-date`` → byte-identical csv. 따라서 dry-run 에서
    # ``--created-at-utc`` 가 없으면 ``sent_date`` 자정(KST)을 사용하여
    # ``attempt_at_kst`` 컬럼을 안정화. send 모드는 v0.1.0 그대로 — 실
    # 발송 시각이 기록되어야 audit 의미가 있으므로 wall clock 유지.
    if created_at_override is not None:
        started_at = created_at_override
    elif is_dry_run:
        started_at = datetime.combine(
            sent_date, datetime.min.time(), tzinfo=KST
        )
    else:
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
            # Distinguish (a) student dropped by cohort filter due to
            # missing score → score_unavailable (FR-H04 / US6) from
            # (b) student missing from the diagnostic CSV → invalid_email.
            if sid in cohort_score_unavailable_sids:
                error_kind = "score_unavailable"
                error_detail = (
                    "score_percent absent — student excluded from cohort"
                )
            else:
                error_kind = "invalid_email"
                error_detail = "student_id has no diagnostic CSV row"
            log_rows.append(
                _skip_row(
                    bundle=bundle,
                    email="",
                    started_at=started_at,
                    mode=mode,
                    error_kind=error_kind,
                    error_detail=error_detail,
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
            override_to=operator_to,
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
        # Dry-run (US1): write .eml previews, no Gmail API call.
        preview_dir = paths["preview_dir"]
        if profile.profile_kind == "test":
            preview_dir = preview_dir / "_test"
        write_eml_preview_files(drafts_with_pdfs, preview_dir)
    elif is_self_test:
        # Self-test (US2): first N drafts → operator's own mailbox.
        # Student emails are NOT used (override_to applied above).
        n = args.self_test
        if n < 1 or n > 10:
            print(
                f"ERROR [immersio email]: --self-test must be 1 ≤ N ≤ 10 "
                f"(got {n}).",
                file=sys.stderr,
            )
            return 2
        if len(drafts_with_pdfs) < n:
            print(
                f"ERROR [immersio email]: only {len(drafts_with_pdfs)} "
                f"sendable drafts available — cannot satisfy --self-test "
                f"{n}.",
                file=sys.stderr,
            )
            return 2
        rc = _run_self_test_send(
            drafts_with_pdfs[:n],
            profile=profile,
            log_rows=log_rows,
        )
        if rc != 0:
            return rc
    else:
        # Production send (US3): Phase G (confirm gate) + Phase H
        # (per-student GmailAPIDispatcher.send_one + log append).
        sample_size = (
            args.confirm_sample
            if args.confirm_sample is not None
            else profile.operational_defaults.confirm_sample_size
        )
        if drafts_with_pdfs:
            try:
                confirm_first_n(
                    drafts_with_pdfs,
                    sample_size=sample_size,
                    stdin=getattr(args, "_stdin", None),
                    stdout=getattr(args, "_stdout", None),
                )
            except ConfirmGateAborted as exc:
                print(
                    f"[immersio email] 운영자 중단 — {exc}. 학생 도달 0.",
                    file=sys.stderr,
                )
                return 0
            except ValueError as exc:
                print(
                    f"ERROR [immersio email]: {exc}", file=sys.stderr
                )
                return 2
        # Resolve rate-per-minute from CLI override or profile default.
        rate_per_minute = (
            args.rate_per_min
            if args.rate_per_min is not None
            else profile.operational_defaults.rate_per_minute
        )
        try:
            production_rc = _run_production_send(
                drafts_with_pdfs,
                profile=profile,
                log_rows=log_rows,
                log_csv_path=log_csv_path,
                rate_per_minute=rate_per_minute,
            )
        except DispatchLockError as exc:
            print(
                f"ERROR [immersio email]: 동시 실행 차단 — {exc}",
                file=sys.stderr,
            )
            return 7

    # Manifest + log + report
    counts = _aggregate_counts(log_rows)
    # v0.1.1 (T014): mirror started_at — dry-run + no ``--created-at-utc``
    # uses sent_date 자정(KST) so the manifest/csv stay byte-identical
    # across re-runs of the same input.
    if created_at_override is not None:
        completed_at = created_at_override
    elif is_dry_run:
        completed_at = datetime.combine(
            sent_date, datetime.min.time(), tzinfo=KST
        )
    else:
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
            # v0.1.1 (T015, FR-C03d): manifest paths follow the mode —
            # dry-run → ``_dryrun`` suffix variants, send → unsuffixed
            # production paths. Resolved via the same ``log_csv_path`` /
            # ``report_md_filename`` used by the csv writer + report
            # writer so manifest always points at the actual file emitted.
            dispatch_log_path=str(log_csv_path.resolve()),
            report_md_path=str(
                (paths["gold_email_dir"] / report_md_filename).resolve()
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

    # Production-send mode already appended rows durably (per-row flock
    # + fsync via append_dispatch_log_row). Other modes write the bulk
    # log here. v0.1.1 (T014): dry-run uses ``메일_발송로그_dryrun.csv``
    # truncate-write so re-running dry-run is byte-identical for the
    # same input and the send-mode csv is *never touched*.
    if not (args.send and not is_self_test):
        log_csv_path.parent.mkdir(parents=True, exist_ok=True)
        _write_log_csv(log_rows, log_csv_path, truncate=is_dry_run)

    summary = {s: counts.model_dump()[s.value] for s in DispatchStatus}
    # v0.1.1 (T016, SC-008 / FR-C04f): ``--retry-skipped`` 모드에서 우선순위
    # ALLOW_HARDCODING: operational notice computation, no PII
    # 결정 결과 ``failed`` 상태인 학번 수. 보고서 md 안내 1줄에 명시되어
    # 운영자가 ``--retry-failed`` 로 명시 재시도해야 함을 인지하도록.
    # 다른 mode 에서는 0 — 안내가 emit 되지 않음. ``prior_log_rows`` 는
    # archival 이전에 캡처되어 있으므로 send/dry-run 모드 모두 안전.
    failed_skipped_count = 0
    if retry_mode == RetryMode.RETRY_SKIPPED and prior_log_rows:
        latest_status = _latest_status_by_sid(prior_log_rows)
        failed_skipped_count = sum(
            1
            for status in latest_status.values()
            if status == DispatchStatus.FAILED
        )
    # v0.1.1 (T015): ``report_md_filename`` resolved earlier (alongside
    # ``log_csv_path``) so manifest + report writer agree on path.
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
        filename=report_md_filename,
        retry_mode=retry_mode,
        failed_skipped_count=failed_skipped_count,
    )

    if getattr(args, "verbose", False):
        print(
            f"[immersio email] mode={mode.value} dry_run={counts.dry_run} "
            f"skipped={counts.skipped} failed={counts.failed}",
            file=sys.stdout,
        )
    # Production-send returns its own rc (0 / 5 / 8) so the auth-fail
    # path (gmail_api_auth_failed → 5) propagates to the CLI exit. Other
    # modes use the count-based default.
    if args.send and not is_self_test and "production_rc" in locals():
        return production_rc
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
    counts = dict.fromkeys(DispatchStatus, 0)
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


def _resolve_retry_mode(args: argparse.Namespace) -> RetryMode:
    """Map the CLI's mutually-exclusive retry flags to ``RetryMode``."""
    if getattr(args, "retry_failed", False):
        return RetryMode.RETRY_FAILED
    if getattr(args, "retry_skipped", False):
        return RetryMode.RETRY_SKIPPED
    return RetryMode.DEFAULT


def _run_production_send(
    drafts_with_pdfs: list[tuple],
    *,
    profile,
    log_rows: list[DispatchLogRow],
    log_csv_path: Path,
    rate_per_minute: int | None = None,
) -> int:
    """Send each draft via Gmail API + append result to dispatch log durably.

    Args:
        drafts_with_pdfs: All ``(draft, bundle)`` pairs to send (already
            idempotent-filtered upstream).
        profile: ProfessorProfile or TestProfile carrying SA credentials.
        log_rows: Mutable list of DispatchLogRow rows. Each placeholder
            row is replaced in-place with the live send result; a copy
            is also appended durably to ``log_csv_path``. On early-exit
            (auth fail / dispatcher exception) any un-attempted SUCCESS
            placeholder is rewritten to ``TEMPORARY_FAILURE`` with
            ``error_kind="not_attempted_after_early_exit"`` so the
            csv/manifest don't claim fake successes.
        log_csv_path: Path to ``메일_발송로그.csv`` (production gold dir).

    Returns:
        ``0`` on full success; ``5`` on Gmail auth failure (FR-C07);
        ``8`` if any send returned FAILED other than auth.

    Raises:
        DispatchLockError: When another process holds LOCK_EX on the
            log file (caller maps to exit 7).
    """
    # Lazy import — keeps the dry-run path free of the Gmail API SDK
    # (test_dry_run_no_send_call.py guards this scope).
    from .sender import GmailAPIDispatcher

    failed_count = 0
    sid_to_log_idx = {row.student_id: i for i, row in enumerate(log_rows)}
    attempted_sids: set[str] = set()
    log_csv_path.parent.mkdir(parents=True, exist_ok=True)
    rc: int | None = None

    try:
        with GmailAPIDispatcher(
            profile, rate_per_minute=rate_per_minute
        ) as dispatcher:
            total = len(drafts_with_pdfs)
            for index, (draft, bundle) in enumerate(drafts_with_pdfs):
                attempted_sids.add(draft.student_id)
                pdf_bytes = bundle.pdf_path.read_bytes()
                result = dispatcher.send_one(draft, pdf_bytes=pdf_bytes)

                idx = sid_to_log_idx.get(draft.student_id)
                if idx is None:
                    # M5: drafts ⊂ log_rows is an upstream invariant —
                    # composer adds a placeholder row for every draft it
                    # builds. Reaching here means the invariant broke.
                    raise RuntimeError(
                        f"invariant violation: draft for student_id "
                        f"{draft.student_id!r} has no matching log row"
                    )
                old = log_rows[idx]
                new_row = DispatchLogRow(
                    student_id=old.student_id,
                    name_kr=old.name_kr,
                    email=old.email,
                    pdf_filename=old.pdf_filename,
                    pdf_sha256=old.pdf_sha256,
                    attempt_at_kst=old.attempt_at_kst,
                    mode=old.mode,
                    status=result.status,
                    smtp_message_id=old.smtp_message_id,
                    error_kind=result.error_kind,
                    error_detail=mask_secrets_in_error_detail(
                        result.error_detail
                    )[:200],
                    exam_name=old.exam_name,
                    cohort=old.cohort,
                )
                log_rows[idx] = new_row
                append_dispatch_log_row(log_csv_path, new_row)

                if result.error_kind == "gmail_api_auth_failed":
                    print(
                        f"ERROR [immersio email]: Gmail API auth failed — "
                        f"{new_row.error_detail}",
                        file=sys.stderr,
                    )
                    rc = 5
                    break
                if result.status == DispatchStatus.FAILED:
                    failed_count += 1
                # US5 / FR-E01: rate-limit sleep BETWEEN sends (skip
                # after the final send — no successor needs spacing).
                # ``getattr`` fallback keeps test fake dispatchers
                # backward-compatible (they may not implement the
                # sleep_between_sends method).
                if index < total - 1:
                    sleep_fn = getattr(
                        dispatcher, "sleep_between_sends", None
                    )
                    if sleep_fn is not None:
                        sleep_fn()
    except DispatchLockError:
        raise
    except Exception as exc:  # noqa: BLE001 — last-resort safety net
        print(
            f"ERROR [immersio email]: dispatcher error — {exc}",
            file=sys.stderr,
        )
        rc = 5

    # Post-release bug fix: when the loop returns early (auth fail /
    # dispatcher exception) any draft after the failure point still
    # carries its SUCCESS placeholder — the manifest would lie about
    # 'success' counts. Rewrite un-attempted SUCCESS rows to
    # TEMPORARY_FAILURE and durably append them so the csv on disk
    # matches the rewritten in-memory state. Idempotent re-run will
    # then retry these rows correctly under RetryMode.DEFAULT.
    rewritten = _rewrite_unattempted_success_rows(
        log_rows,
        attempted_sids=attempted_sids,
        replacement_status=DispatchStatus.TEMPORARY_FAILURE,
        error_kind="not_attempted_after_early_exit",
        error_detail=(
            "production-send loop returned early; this row was not attempted"
        ),
    )
    for row in rewritten:
        append_dispatch_log_row(log_csv_path, row)

    if rc is not None:
        return rc
    return 0 if failed_count == 0 else 8


def _run_self_test_send(
    drafts_with_pdfs: list[tuple],
    *,
    profile,
    log_rows: list[DispatchLogRow],
) -> int:
    """Send the first N drafts via Gmail API to the operator's own mailbox.

    Args:
        drafts_with_pdfs: ``(draft, bundle)`` pairs already pre-built with
            ``override_to=profile.sender.email`` so each ``To`` header is
            the operator's own address (FR-C05 — student emails not used).
        profile: ProfessorProfile or TestProfile carrying SA credentials.
        log_rows: Mutable list of DispatchLogRow rows. Self-test rows are
            updated in-place with the actual send result + status.
            Un-attempted SUCCESS placeholders (drafts NOT in the [:N]
            slice, or attempts cut short by auth-fail / exception) are
            rewritten to ``SKIPPED`` with ``error_kind=
            "self_test_not_attempted"`` so the csv/manifest don't claim
            fake successes for non-sent rows.

    Returns:
        ``0`` on full success; ``5`` on Gmail auth failure (FR-C07);
        ``8`` if any send returned FAILED other than auth.
    """
    # Lazy import — keeps the dry-run path free of the Gmail API SDK
    # (test_dry_run_no_send_call.py guards this scope).
    from .sender import GmailAPIDispatcher

    failed_count = 0
    sid_to_log_idx = {row.student_id: i for i, row in enumerate(log_rows)}
    attempted_sids: set[str] = set()
    rc: int | None = None

    try:
        with GmailAPIDispatcher(profile) as dispatcher:
            for draft, bundle in drafts_with_pdfs:
                attempted_sids.add(draft.student_id)
                pdf_bytes = bundle.pdf_path.read_bytes()
                result = dispatcher.send_one(draft, pdf_bytes=pdf_bytes)

                idx = sid_to_log_idx.get(draft.student_id)
                if idx is None:
                    # M5: drafts ⊂ log_rows is an upstream invariant —
                    # composer adds a placeholder row for every draft it
                    # builds. Reaching here means the invariant broke.
                    raise RuntimeError(
                        f"invariant violation: draft for student_id "
                        f"{draft.student_id!r} has no matching log row"
                    )
                old = log_rows[idx]
                # Self-test → log status TEST_DUMMY on success (FR-D08)
                # so prod reports never count these as live sends.
                effective_status = (
                    DispatchStatus.TEST_DUMMY
                    if result.status == DispatchStatus.SUCCESS
                    else result.status
                )
                log_rows[idx] = DispatchLogRow(
                    student_id=old.student_id,
                    name_kr=old.name_kr,
                    email=old.email,
                    pdf_filename=old.pdf_filename,
                    pdf_sha256=old.pdf_sha256,
                    attempt_at_kst=old.attempt_at_kst,
                    mode=old.mode,
                    status=effective_status,
                    smtp_message_id=old.smtp_message_id,
                    error_kind=result.error_kind,
                    error_detail=result.error_detail[:200],
                    exam_name=old.exam_name,
                    cohort=old.cohort,
                )
                if result.error_kind == "gmail_api_auth_failed":
                    print(
                        f"ERROR [immersio email]: Gmail API auth failed — "
                        f"{result.error_detail}",
                        file=sys.stderr,
                    )
                    rc = 5
                    break
                if result.status == DispatchStatus.FAILED:
                    failed_count += 1
    except Exception as exc:  # noqa: BLE001 — last-resort safety net
        print(
            f"ERROR [immersio email]: dispatcher error — {exc}",
            file=sys.stderr,
        )
        rc = 5

    # Post-release bug fix: rewrite un-attempted SUCCESS placeholders so
    # the csv/manifest don't show fake successes for drafts that were
    # never actually sent (most common: M-N drafts outside the [:N]
    # self-test slice). Two cases caught:
    #   (a) drafts not in the [:N] slice — never targeted in this run;
    #   (b) drafts inside [:N] but skipped because the loop broke after
    #       gmail_api_auth_failed / dispatcher exception.
    _rewrite_unattempted_success_rows(
        log_rows,
        attempted_sids=attempted_sids,
        replacement_status=DispatchStatus.SKIPPED,
        error_kind="self_test_not_attempted",
        error_detail=(
            "self-test sent only first N drafts; this row was not attempted"
        ),
    )

    if rc is not None:
        return rc
    return 0 if failed_count == 0 else 8


def _rewrite_unattempted_success_rows(
    log_rows: list[DispatchLogRow],
    *,
    attempted_sids: set[str],
    replacement_status: DispatchStatus,
    error_kind: str,
    error_detail: str,
) -> list[DispatchLogRow]:
    """Convert SUCCESS placeholder rows for un-attempted drafts.

    The per-bundle loop in ``run_email_dispatch`` pre-populates each
    sendable draft's log row with ``status=SUCCESS`` (the optimistic
    placeholder) before the actual send loop runs. When a send function
    sends only a slice of drafts or returns early, the un-attempted
    rows retain the SUCCESS placeholder — that lies to the operator.
    This helper rewrites those leftover SUCCESS rows in-place.

    Returns:
        The list of newly-rewritten rows (post-fixup), in their
        original ``log_rows`` index order. Callers that already
        durably appended attempted rows to disk (production-send path)
        use this list to append the rewritten rows so the csv on disk
        matches in-memory state.
    """
    rewritten: list[DispatchLogRow] = []
    for idx, row in enumerate(log_rows):
        if row.status != DispatchStatus.SUCCESS:
            continue
        if row.student_id in attempted_sids:
            continue
        new_row = DispatchLogRow(
            student_id=row.student_id,
            name_kr=row.name_kr,
            email=row.email,
            pdf_filename=row.pdf_filename,
            pdf_sha256=row.pdf_sha256,
            attempt_at_kst=row.attempt_at_kst,
            mode=row.mode,
            status=replacement_status,
            smtp_message_id="",
            error_kind=error_kind,
            error_detail=error_detail[:200],
            exam_name=row.exam_name,
            cohort=row.cohort,
        )
        log_rows[idx] = new_row
        rewritten.append(new_row)
    return rewritten


def _write_log_csv(
    rows: list[DispatchLogRow], path: Path, *, truncate: bool = False
) -> None:
    """Write rows to the dispatch log csv with the locked 13-column header.

    Args:
        rows: DispatchLogRow rows to write.
        path: Target csv path.
        truncate: When ``True`` (v0.1.1 dry-run mode), open in ``"w"`` mode
            so the file is overwritten — header always emitted and no
            prior contents preserved (FR-C03a, contracts/dry_run_outputs.md §2).
            Default ``False`` matches v0.1.0 append-mode behaviour for the
            send-mode log csv.
    """
    if truncate:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=list(DispatchLogRow.COLUMN_ORDER)
            )
            writer.writeheader()
            for row in rows:
                dump = row.model_dump(mode="json")
                writer.writerow(
                    {c: dump[c] for c in DispatchLogRow.COLUMN_ORDER}
                )
        return
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
