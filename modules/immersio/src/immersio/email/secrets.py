"""Gmail API service-account credential loader (T028).

Implements contracts/secrets_contract.md exactly: env var → file path →
permission 0400 → JSON parse → required fields → ``Credentials.from_
service_account_info``. Every error message redacts secret content
(only the env-var name and path are referenced).
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from google.oauth2.service_account import Credentials

if TYPE_CHECKING:
    from paideia_shared.schemas import ProfessorProfile, TestProfile

_ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
_REQUIRED_SA_FIELDS: tuple[str, ...] = (
    "type",
    "client_email",
    "private_key",
    "private_key_id",
)


def _is_under(child: Path, parent: Path) -> bool:
    """True if ``child`` is the same as or descended from ``parent``."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _allowed_sa_path_prefixes() -> tuple[Path, ...]:
    """Return canonical prefixes the SA JSON file is allowed to live under.

    Path-traversal defence (Reflag #2 / adversary AV-A1). Any path that
    resolves outside this allowlist is rejected so a misconfigured
    agenix path or hostile env-var injection cannot point the loader at,
    for example, ``/etc/passwd``.
    """
    home = Path.home()
    return (
        Path("/run/agenix"),
        home / ".config" / "paideia",
        home / ".local" / "share" / "paideia",
        home / ".config" / "keys",
    )


class SecretsError(RuntimeError):
    """Raised on any agenix / SA JSON precondition failure (FR-C07).

    Error messages MUST never include the SA JSON contents — only the
    env-var name and absolute path are referenced.
    """


class _ProfileShape(Protocol):
    """Minimal duck-type for both ProfessorProfile and TestProfile."""

    @property
    def gmail_api(self) -> object: ...
    @property
    def secrets_ref(self) -> object: ...


def get_gmail_credentials(
    profile: ProfessorProfile | TestProfile,
) -> Credentials:
    """Resolve the Service Account credentials referenced by ``profile``.

    Args:
        profile: A loaded ProfessorProfile or TestProfile carrying
            ``secrets_ref.service_account_json_path_env`` and
            ``gmail_api.{service_account_subject, scopes}``.

    Returns:
        Live ``google.oauth2.service_account.Credentials`` impersonating
        ``profile.gmail_api.service_account_subject`` with the
        ``gmail.send`` scope.

    Raises:
        SecretsError: For any of the 7 fail-fast conditions enumerated
            in contracts/secrets_contract.md (env var unset, file
            missing, permissions != 0400, JSON parse fail, type
            mismatch, missing required field, env-var name pattern
            violation). Never raises a message containing JSON
            contents.
    """
    env_var = profile.secrets_ref.service_account_json_path_env
    if not _ENV_VAR_RE.fullmatch(env_var):
        raise SecretsError(
            f"FR-G02: invalid env var name pattern: {env_var!r} (must match ^[A-Z][A-Z0-9_]+$)"
        )

    path_str = os.environ.get(env_var)
    if path_str is None:
        raise SecretsError(
            f"FR-C07: env var {env_var!r} not set. "
            f"Activate agenix: 'home-manager switch' or 'direnv reload'."
        )

    path = Path(path_str)
    if not path.is_file():
        raise SecretsError(f"FR-C07: SA JSON file not found at {str(path)!r}")

    # Path-traversal defence (Reflag #2 / AV-A1) — reject any SA JSON path
    # that, after symlink resolution, escapes the canonical allowlist.
    resolved = path.resolve()
    allowed_prefixes = tuple(p.resolve() for p in _allowed_sa_path_prefixes())
    if not any(resolved == prefix or _is_under(resolved, prefix) for prefix in allowed_prefixes):
        raise SecretsError(
            f"FR-C07: SA JSON path {str(resolved)!r} not in allowlist. "
            f"Allowed prefixes: {[str(p) for p in allowed_prefixes]}"
        )

    try:
        st = path.stat()
    except OSError as exc:
        raise SecretsError(f"FR-C07: cannot stat SA JSON at {str(path)!r}: {exc}") from exc

    loose_bits = st.st_mode & (
        stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH | stat.S_IXGRP | stat.S_IXOTH
    )
    if loose_bits:
        raise SecretsError(
            f"FR-C07: SA JSON file {str(path)!r} permissions too loose "
            f"(mode={oct(st.st_mode & 0o777)}, expected 0400). "
            f"Run: chmod 0400 {path}"
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecretsError(f"FR-C07: cannot read SA JSON at {str(path)!r}: {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SecretsError(
            f"FR-C07: SA JSON parse error at {str(path)!r}: {exc.msg} (line {exc.lineno})"
        ) from exc

    if not isinstance(data, dict):
        raise SecretsError(f"FR-C07: SA JSON top-level must be object at {str(path)!r}")

    missing = [f for f in _REQUIRED_SA_FIELDS if f not in data]
    if missing:
        raise SecretsError(
            f"FR-C07: SA JSON missing required field(s) {missing!r} at {str(path)!r}"
        )

    if data["type"] != "service_account":
        raise SecretsError(
            f"FR-C07: not a service account JSON at {str(path)!r} "
            f"(type={data['type']!r}, expected 'service_account')"
        )

    creds = Credentials.from_service_account_info(
        data,
        scopes=list(profile.gmail_api.scopes),
        subject=profile.gmail_api.service_account_subject,
    )
    return creds


__all__ = ["SecretsError", "get_gmail_credentials"]
