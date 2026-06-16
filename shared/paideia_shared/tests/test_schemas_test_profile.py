"""Contract tests for TestProfile + DummyStudent (T008).

Verifies inheritance of operator-shape fields plus 3 test-only fields,
and the recipient_pool ↔ dummy_students 1:1 length match (TC-003).
"""

from __future__ import annotations

import pytest
import yaml
from paideia_shared.schemas import DummyStudent, TestProfile
from pydantic import ValidationError


def _valid_test_yaml(tmp_path) -> str:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    return f"""
profile_kind: test
profile_name: alpha-dev
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
  - student_id: '1234567890'
    name_kr: 더미일
  - student_id: '1234567891'
    name_kr: 더미이
"""


def test_valid_test_profile_loads(tmp_path) -> None:
    profile = TestProfile.model_validate(yaml.safe_load(_valid_test_yaml(tmp_path)))
    assert profile.profile_kind == "test"
    assert len(profile.recipient_pool) == 2
    assert len(profile.dummy_students) == 2
    assert profile.dummy_students[0].student_id == "1234567890"


def test_recipient_pool_length_must_equal_dummy_students(tmp_path) -> None:
    data = yaml.safe_load(_valid_test_yaml(tmp_path))
    data["dummy_students"].pop()  # 2 pool, 1 dummy
    with pytest.raises(ValidationError) as exc_info:
        TestProfile.model_validate(data)
    assert "1:1 matching" in str(exc_info.value) or "must equal" in str(exc_info.value)


def test_recipient_pool_unique_addresses(tmp_path) -> None:
    data = yaml.safe_load(_valid_test_yaml(tmp_path))
    data["recipient_pool"][1] = data["recipient_pool"][0]
    with pytest.raises(ValidationError) as exc_info:
        TestProfile.model_validate(data)
    assert "duplicate" in str(exc_info.value).lower()


def test_dummy_students_student_ids_unique(tmp_path) -> None:
    data = yaml.safe_load(_valid_test_yaml(tmp_path))
    data["dummy_students"][1]["student_id"] = data["dummy_students"][0]["student_id"]
    with pytest.raises(ValidationError) as exc_info:
        TestProfile.model_validate(data)
    assert "unique" in str(exc_info.value).lower()


def test_dummy_student_id_must_be_ten_digits() -> None:
    with pytest.raises(ValidationError):
        DummyStudent(student_id="123456789", name_kr="아홉자리")  # 9 digits


def test_dummy_student_name_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        DummyStudent(student_id="1234567890", name_kr="")


def test_dummy_fixture_dir_must_exist(tmp_path) -> None:
    data = yaml.safe_load(_valid_test_yaml(tmp_path))
    data["dummy_fixture_dir"] = "/nonexistent/path/does/not/exist"
    with pytest.raises(ValidationError):
        TestProfile.model_validate(data)


def test_recipient_pool_max_ten(tmp_path) -> None:
    data = yaml.safe_load(_valid_test_yaml(tmp_path))
    data["recipient_pool"] = [f"pool{i}@example.com" for i in range(11)]
    data["dummy_students"] = [
        {"student_id": f"123456789{i}", "name_kr": f"학생{i}"} for i in range(11)
    ]
    with pytest.raises(ValidationError):
        TestProfile.model_validate(data)
