"""Shared fixtures for email integration tests."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from reportlab.pdfgen import canvas


def _make_pdf(path: Path, body_text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, body_text)
    c.showPage()
    c.save()


def make_fixture(
    base_dir: Path,
    students: list[tuple[str, str, str]],
) -> dict[str, Path]:
    """Create a minimal end-to-end fixture under ``base_dir``.

    Args:
        base_dir: tmp_path-like root.
        students: list of ``(student_id, name_kr, email)`` triples.

    Returns:
        Dict of all relevant paths the pipeline needs.
    """
    bronze_dir = base_dir / "data" / "bronze" / "진단평가"
    bronze_dir.mkdir(parents=True)
    bronze_csv = bronze_dir / "진단평가_1차_결과.csv"
    with bronze_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["타임스탬프", "사용자 이름", "학번"])
        for sid, _name, email in students:
            writer.writerow([
                "2026/03/03 11:03:36 AM GMT+9",
                email,
                sid,
            ])

    pdf_dir = base_dir / "data" / "gold" / "immersio" / "2026-1-anatomy" / "이메일_발송용"
    pdf_dir.mkdir(parents=True)
    for sid, name, _email in students:
        _make_pdf(pdf_dir / f"{sid}_{name}.pdf", body_text=f"학번 {sid} 결과")

    # post-release fix: paideia immersio Phase 0 ingest writes
    # `student_master.parquet` (English filename, course-scoped).
    silver_dir = base_dir / "data" / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    master_path = silver_dir / "student_master.parquet"
    pq.write_table(
        pa.table(
            {
                "student_id": [s[0] for s in students],
                "name_kr": [s[1] for s in students],
            }
        ),
        master_path,
    )

    return {
        "base": base_dir,
        "bronze_csv": bronze_csv,
        "gold_pdf_dir": pdf_dir,
        "silver_master": master_path,
        "preview_dir": base_dir / "tmp" / "immersio_email_preview" / "2026-1-anatomy",
        "gold_email_dir": base_dir / "data" / "gold" / "immersio" / "2026-1-anatomy",
    }


def make_profile_dir(home: Path, profile_name: str = "alpha-prof") -> Path:
    """Create an XDG-compliant operator profile YAML at ``home``."""
    cfg = home / ".config" / "paideia" / "immersio_email" / "profiles"
    cfg.mkdir(parents=True)
    yaml_text = f"""
profile_kind: operator
profile_name: {profile_name}
sender:
  display_name: 알파교수
  email: alpha@example.ac.kr
send_account:
  email: noreply@example.ac.kr
institution:
  university_name: 알파대학교
  department_name: 알파학과
booking:
  google_calendar_url: https://calendar.google.com/calendar/u/0/appointments/abc
gmail_api:
  service_account_subject: noreply@example.ac.kr
  scopes:
    - https://www.googleapis.com/auth/gmail.send
secrets_ref:
  service_account_json_path_env: PAIDEIA_GCP_SA_JSON_PATH_ALPHA
operational_defaults:
  rate_per_minute: 20
  confirm_sample_size: 3
  attachment_max_bytes: 104857600
"""
    (cfg / f"{profile_name}.yaml").write_text(yaml_text, encoding="utf-8")
    return cfg


def make_test_profile(
    home: Path,
    fixture_dir: Path,
    profile_name: str = "alpha-dev",
) -> Path:
    """Create an XDG-compliant TestProfile YAML at ``home``."""
    cfg = home / ".config" / "paideia" / "immersio_email" / "test_profiles"
    cfg.mkdir(parents=True, exist_ok=True)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    yaml_text = f"""
profile_kind: test
profile_name: {profile_name}
sender:
  display_name: 알파교수
  email: alpha@example.ac.kr
send_account:
  email: noreply@example.ac.kr
institution:
  university_name: 알파대학교
  department_name: 알파학과
booking:
  google_calendar_url: https://calendar.google.com/calendar/u/0/appointments/abc
gmail_api:
  service_account_subject: noreply@example.ac.kr
  scopes:
    - https://www.googleapis.com/auth/gmail.send
secrets_ref:
  service_account_json_path_env: PAIDEIA_GCP_SA_JSON_PATH_ALPHA_DEV
operational_defaults:
  rate_per_minute: 20
  confirm_sample_size: 1
  attachment_max_bytes: 10485760
recipient_pool:
  - pool1@example.com
  - pool2@example.com
dummy_fixture_dir: {fixture_dir}
dummy_students:
  - student_id: '1234567990'
    name_kr: 더미일
  - student_id: '1234567991'
    name_kr: 더미이
"""
    (cfg / f"{profile_name}.yaml").write_text(yaml_text, encoding="utf-8")
    return cfg


def write_student_metrics_parquet(
    silver_dir: Path,
    rows: list[tuple[str, str, float | None]],
) -> Path:
    """Helper for cohort tests: write a 학생지표.parquet stub."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    path = silver_dir / "학생지표.parquet"
    table = pa.table(
        {
            "student_id": [r[0] for r in rows],
            "name_kr": [r[1] for r in rows],
            "score_percent": [r[2] for r in rows],
        }
    )
    pq.write_table(table, path)
    return path


@pytest.fixture
def email_fixture(tmp_path: Path, monkeypatch):
    """5-student end-to-end fixture in a tmp HOME with operator profile."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    students = [
        ("1234567001", "홍길동", "hong@example.com"),
        ("1234567002", "김갑동", "kim@example.com"),
        ("1234567003", "이순신", "lee@example.com"),
        ("1234567004", "유관순", "yoo@example.com"),
        ("1234567005", "안중근", "ahn@example.com"),
    ]
    paths = make_fixture(tmp_path, students)
    make_profile_dir(home, profile_name="alpha-prof")
    paths["home"] = home
    paths["students"] = students
    return paths
