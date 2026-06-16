"""get_gmail_credentials unit tests (T024).

7 scenarios per contracts/secrets_contract.md:
1. env var unset
2. file not found
3. permission != 0400
4. JSON parse error
5. type != "service_account"
6. required field missing
7. happy path → Credentials.from_service_account_info called

Every error message must redact secret content (only env-var name +
file path appear).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from immersio.email.secrets import SecretsError, get_gmail_credentials
from paideia_shared.schemas import ProfessorProfile


def _profile(env_var: str = "PAIDEIA_GCP_SA_JSON_PATH_ALPHA") -> ProfessorProfile:
    yaml_text = f"""\
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
  service_account_json_path_env: {env_var}
operational_defaults:
  rate_per_minute: 20
  confirm_sample_size: 3
  attachment_max_bytes: 104857600
"""
    return ProfessorProfile.model_validate(yaml.safe_load(yaml_text))


@pytest.fixture
def whitelist_tmp_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Whitelist tmp_path under the SA-allowlist for tests reaching past it.

    The production allowlist is /run/agenix, ~/.config/paideia, etc. —
    tests must whitelist tmp_path explicitly to exercise the
    permission/parse/type/missing-field paths beyond the path gate.
    Tests that *want* to verify the path-traversal defence (the dedicated
    Reflag #2 test) MUST NOT use this fixture.
    """
    monkeypatch.setattr(
        "immersio.email.secrets._allowed_sa_path_prefixes",
        lambda: (tmp_path,),
    )
    return tmp_path


def _make_sa_json(tmp_path: Path, *, mode: int = 0o400, **overrides) -> Path:
    base = {
        "type": "service_account",
        "client_email": "fake-sa@fake-project.iam.gserviceaccount.com",  # ALLOW_HARDCODING: fake fixture for secrets test
        "private_key": (  # ALLOW_HARDCODING: fake bytes for secrets test
            "-----BEGIN PRIVATE KEY-----\nfake-bytes\n-----END PRIVATE KEY-----\n"  # ALLOW_HARDCODING: fake bytes for secrets test
        ),
        "private_key_id": "0123456789abcdef0123456789abcdef01234567",  # ALLOW_HARDCODING: fake hex40 for secrets test
        "project_id": "fake-project",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    base.update(overrides)
    path = tmp_path / "fake-sa.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    path.chmod(mode)
    return path


def test_env_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", raising=False)
    profile = _profile()
    with pytest.raises(SecretsError) as exc_info:
        get_gmail_credentials(profile)
    msg = str(exc_info.value)
    assert "FR-C07" in msg
    assert "PAIDEIA_GCP_SA_JSON_PATH_ALPHA" in msg
    assert "BEGIN PRIVATE KEY" not in msg
    assert "private_key" not in msg


def test_file_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "PAIDEIA_GCP_SA_JSON_PATH_ALPHA",
        str(tmp_path / "missing.json"),
    )
    profile = _profile()
    with pytest.raises(SecretsError, match="not found"):
        get_gmail_credentials(profile)


def test_permission_too_loose(monkeypatch: pytest.MonkeyPatch, whitelist_tmp_path: Path) -> None:
    sa = _make_sa_json(whitelist_tmp_path, mode=0o644)
    monkeypatch.setenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", str(sa))
    profile = _profile()
    with pytest.raises(SecretsError) as exc_info:
        get_gmail_credentials(profile)
    msg = str(exc_info.value)
    assert "permissions too loose" in msg
    # Critical: never leak SA contents in error message
    assert "BEGIN PRIVATE KEY" not in msg
    assert "fake-bytes" not in msg
    assert "fake-sa@fake-project" not in msg


def test_json_parse_error(monkeypatch: pytest.MonkeyPatch, whitelist_tmp_path: Path) -> None:
    bad = whitelist_tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    bad.chmod(0o400)
    monkeypatch.setenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", str(bad))
    profile = _profile()
    with pytest.raises(SecretsError, match="parse error"):
        get_gmail_credentials(profile)


def test_type_not_service_account(
    monkeypatch: pytest.MonkeyPatch, whitelist_tmp_path: Path
) -> None:
    sa = _make_sa_json(whitelist_tmp_path, type="user_credentials")
    monkeypatch.setenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", str(sa))
    profile = _profile()
    with pytest.raises(SecretsError, match="not a service account"):
        get_gmail_credentials(profile)


def test_missing_required_field(monkeypatch: pytest.MonkeyPatch, whitelist_tmp_path: Path) -> None:
    # Drop private_key to trigger missing-field check
    sa = whitelist_tmp_path / "missing.json"
    sa.write_text(
        json.dumps(
            {"type": "service_account", "client_email": "x@y.com"}
        ),  # ALLOW_HARDCODING: fake placeholder for missing-field test
        encoding="utf-8",
    )
    sa.chmod(0o400)
    monkeypatch.setenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", str(sa))
    profile = _profile()
    with pytest.raises(SecretsError, match="missing required field"):
        get_gmail_credentials(profile)


def test_happy_path_calls_from_service_account_info(
    monkeypatch: pytest.MonkeyPatch, whitelist_tmp_path: Path
) -> None:
    """Valid SA JSON → Credentials.from_service_account_info(...) called."""
    sa = _make_sa_json(whitelist_tmp_path)
    monkeypatch.setenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", str(sa))
    profile = _profile()

    with patch("immersio.email.secrets.Credentials.from_service_account_info") as mock_from_info:
        mock_from_info.return_value = "creds-obj"
        result = get_gmail_credentials(profile)

    assert result == "creds-obj"
    mock_from_info.assert_called_once()
    call_kwargs = mock_from_info.call_args.kwargs
    assert call_kwargs["scopes"] == ["https://www.googleapis.com/auth/gmail.send"]
    assert call_kwargs["subject"] == "noreply@example.ac.kr"


def test_path_outside_allowlist_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Reflag #2 / AV-A1: SA JSON path outside allowlist → SecretsError.

    Even when file content is valid (mode 0400, parses, type=service_
    account, all required fields present), a path under /tmp without an
    explicit allowlist whitelist must be rejected before
    ``Credentials.from_service_account_info`` is ever called. Defence
    against env-var injection or misconfigured agenix paths pointing at
    e.g. ``/etc/passwd``.
    """
    sa = _make_sa_json(tmp_path)
    monkeypatch.setenv("PAIDEIA_GCP_SA_JSON_PATH_ALPHA", str(sa))
    # Do NOT monkeypatch _allowed_sa_path_prefixes — production allowlist
    # is in effect, so /tmp is rejected.
    profile = _profile()
    with pytest.raises(SecretsError) as exc_info:
        get_gmail_credentials(profile)
    msg = str(exc_info.value)
    assert "not in allowlist" in msg
    # Defence-in-depth: never leak SA contents in error message
    assert "BEGIN PRIVATE KEY" not in msg
    assert "fake-bytes" not in msg
    assert "fake-sa@fake-project" not in msg


def test_invalid_env_var_name_pattern() -> None:
    """Profile carrying lowercase env-var name fails fast (defence-in-depth).

    The Pydantic validator on ProfessorProfile already rejects lowercase,
    so this is reachable only if a profile is constructed bypassing
    validation. The function still validates as a belt-and-braces check.
    """

    # Build a profile with valid uppercase, then mutate via Pydantic
    # update mechanism would fail (frozen=True), so build a ad-hoc duck.
    class _DuckSecretsRef:
        service_account_json_path_env = "lowercase_var"

    class _DuckGmailApi:
        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        service_account_subject = "noreply@example.ac.kr"

    class _DuckProfile:
        secrets_ref = _DuckSecretsRef()
        gmail_api = _DuckGmailApi()

    with pytest.raises(SecretsError, match="FR-G02"):
        get_gmail_credentials(_DuckProfile())  # type: ignore[arg-type]
