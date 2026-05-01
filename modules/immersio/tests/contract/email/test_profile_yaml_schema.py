"""Contract test for profile YAML schema (T025).

Validates the discriminated union behavior, YAML round-trip parity, and
``dummy_students`` ↔ ``recipient_pool`` length parity at load time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Union

import pytest
import yaml
from pydantic import Discriminator, TypeAdapter, ValidationError

from paideia_shared.schemas import ProfessorProfile, TestProfile

ProfileUnion = Annotated[
    Union[ProfessorProfile, TestProfile],
    Discriminator("profile_kind"),
]
_ADAPTER: TypeAdapter[ProfessorProfile | TestProfile] = TypeAdapter(ProfileUnion)


def _operator_yaml() -> str:
    return """\
profile_kind: operator
profile_name: alpha-prof
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


def _test_yaml(fixture_dir: Path) -> str:
    return f"""\
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


def test_operator_yaml_round_trip() -> None:
    raw = yaml.safe_load(_operator_yaml())
    profile = _ADAPTER.validate_python(raw)
    assert isinstance(profile, ProfessorProfile)
    again = _ADAPTER.validate_python(profile.model_dump(mode="json"))
    assert again == profile


def test_test_yaml_round_trip(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    raw = yaml.safe_load(_test_yaml(fixture_dir))
    profile = _ADAPTER.validate_python(raw)
    assert isinstance(profile, TestProfile)


def test_discriminator_routes_correctly(tmp_path: Path) -> None:
    op_raw = yaml.safe_load(_operator_yaml())
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    test_raw = yaml.safe_load(_test_yaml(fixture_dir))
    assert isinstance(_ADAPTER.validate_python(op_raw), ProfessorProfile)
    assert isinstance(_ADAPTER.validate_python(test_raw), TestProfile)


def test_invalid_profile_kind_rejected() -> None:
    raw = yaml.safe_load(_operator_yaml())
    raw["profile_kind"] = "unknown"
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(raw)


def test_dummy_students_length_mismatch_rejected_at_load(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    raw = yaml.safe_load(_test_yaml(fixture_dir))
    raw["dummy_students"].pop()  # 2 pool, 1 dummy
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(raw)
