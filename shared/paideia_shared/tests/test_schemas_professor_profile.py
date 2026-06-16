"""Contract tests for ProfessorProfile (T007).

Verifies the 9 spec validators per data-model.md §1.1 and the Pydantic
discriminator on ``profile_kind``.
"""

from __future__ import annotations

import pytest
import yaml
from paideia_shared.schemas import ProfessorProfile
from pydantic import ValidationError

_VALID_OPERATOR_YAML = """
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


def _load(text: str) -> dict:
    return yaml.safe_load(text)


def test_valid_operator_profile_loads() -> None:
    profile = ProfessorProfile.model_validate(_load(_VALID_OPERATOR_YAML))
    assert profile.profile_kind == "operator"
    assert profile.profile_name == "alpha-prof"
    assert profile.sender.email == "alpha@example.ac.kr"
    assert profile.send_account.email == "noreply@example.ac.kr"


def test_yaml_round_trip_preserves_fields() -> None:
    """YAML → model → dict → YAML round-trip is field-equivalent."""
    profile = ProfessorProfile.model_validate(_load(_VALID_OPERATOR_YAML))
    dumped = profile.model_dump(mode="json")
    again = ProfessorProfile.model_validate(dumped)
    assert again == profile


def test_profile_name_regex_violation_rejected() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["profile_name"] = "Alpha-Prof"  # uppercase forbidden
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_subject_must_match_send_account_email() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["gmail_api"]["service_account_subject"] = "different@example.ac.kr"
    with pytest.raises(ValidationError) as exc_info:
        ProfessorProfile.model_validate(data)
    assert "service_account_subject" in str(exc_info.value)


def test_scopes_must_be_exactly_gmail_send() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["gmail_api"]["scopes"] = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_calendar_host_must_be_google() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["booking"]["google_calendar_url"] = "https://other.example.com/abc"
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_env_var_name_pattern_enforced() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["secrets_ref"]["service_account_json_path_env"] = "lower_case"
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_rate_per_minute_range() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["operational_defaults"]["rate_per_minute"] = 31
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)
    data["operational_defaults"]["rate_per_minute"] = 0
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_attachment_max_bytes_upper_bound() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["operational_defaults"]["attachment_max_bytes"] = 209715201  # 200MB+1
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_confirm_sample_size_range() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["operational_defaults"]["confirm_sample_size"] = 11
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)


def test_extra_field_rejected() -> None:
    data = _load(_VALID_OPERATOR_YAML)
    data["extra_field"] = "leak"
    with pytest.raises(ValidationError):
        ProfessorProfile.model_validate(data)
