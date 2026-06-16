"""ProfileLoader unit tests (T023).

6 scenarios per the contract: operator-only, test-only, both-found,
neither-found, format violation, credentials precheck call.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.email.profile import ProfileError, ProfileLoader


def _operator_yaml(profile_name: str = "alpha-prof") -> str:
    return f"""\
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


def _test_yaml(tmp_path: Path, profile_name: str = "alpha-dev") -> str:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    return f"""\
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
  - student_id: '1234567890'
    name_kr: 더미일
  - student_id: '1234567891'
    name_kr: 더미이
"""


@pytest.fixture
def config_home(tmp_path: Path) -> Path:
    home = tmp_path / "config"
    (home / "profiles").mkdir(parents=True)
    (home / "test_profiles").mkdir(parents=True)
    return home


def test_load_operator_profile(config_home: Path) -> None:
    (config_home / "profiles" / "alpha-prof.yaml").write_text(_operator_yaml(), encoding="utf-8")
    loader = ProfileLoader(config_home=config_home)
    profile = loader.load("alpha-prof")
    assert profile.profile_kind == "operator"
    assert profile.profile_name == "alpha-prof"


def test_load_test_profile(config_home: Path, tmp_path: Path) -> None:
    (config_home / "test_profiles" / "alpha-dev.yaml").write_text(
        _test_yaml(tmp_path), encoding="utf-8"
    )
    loader = ProfileLoader(config_home=config_home)
    profile = loader.load("alpha-dev")
    assert profile.profile_kind == "test"
    assert len(profile.recipient_pool) == 2


def test_both_directories_match_rejected(config_home: Path, tmp_path: Path) -> None:
    """FR-G08: profile must exist in exactly one location."""
    (config_home / "profiles" / "duplicate.yaml").write_text(
        _operator_yaml("duplicate"), encoding="utf-8"
    )
    (config_home / "test_profiles" / "duplicate.yaml").write_text(
        _test_yaml(tmp_path, "duplicate"), encoding="utf-8"
    )
    loader = ProfileLoader(config_home=config_home)
    with pytest.raises(ProfileError) as exc_info:
        loader.load("duplicate")
    assert "FR-G08" in str(exc_info.value)
    assert "multiple" in str(exc_info.value).lower()


def test_neither_directory_match_rejected(config_home: Path) -> None:
    loader = ProfileLoader(config_home=config_home)
    with pytest.raises(ProfileError) as exc_info:
        loader.load("missing")
    assert "FR-G08" in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()


def test_invalid_yaml_format_rejected(config_home: Path) -> None:
    (config_home / "profiles" / "bad.yaml").write_text(
        "profile_kind: operator\nprofile_name: bad\nsender: not-a-dict",
        encoding="utf-8",
    )
    loader = ProfileLoader(config_home=config_home)
    with pytest.raises(ProfileError):
        loader.load("bad")


def test_credentials_precheck_called(config_home: Path) -> None:
    (config_home / "profiles" / "alpha-prof.yaml").write_text(_operator_yaml(), encoding="utf-8")
    called_with: list = []

    def precheck(profile) -> None:
        called_with.append(profile)

    loader = ProfileLoader(
        config_home=config_home,
        credentials_precheck=precheck,
    )
    profile = loader.load("alpha-prof")
    assert len(called_with) == 1
    assert called_with[0] is profile


def test_credentials_precheck_failure_propagates(config_home: Path) -> None:
    (config_home / "profiles" / "alpha-prof.yaml").write_text(_operator_yaml(), encoding="utf-8")

    def precheck(profile) -> None:
        raise ProfileError("FR-C07: env var unset")

    loader = ProfileLoader(
        config_home=config_home,
        credentials_precheck=precheck,
    )
    with pytest.raises(ProfileError, match="FR-C07"):
        loader.load("alpha-prof")
