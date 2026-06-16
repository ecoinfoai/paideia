"""ProfileLoader — XDG search + discriminator-aware YAML loader (T027).

Searches two canonical paths (operator vs test). FR-G08 demands exactly
one match — both-found and neither-found cases raise. The optional
``credentials_precheck`` hook is called after parse so the CLI can fail
fast on missing agenix env vars without writing a single byte to disk.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import yaml
from paideia_shared.schemas import ProfessorProfile, TestProfile
from pydantic import Discriminator, TypeAdapter, ValidationError

ProfileUnion = Annotated[
    ProfessorProfile | TestProfile,
    Discriminator("profile_kind"),
]
_PROFILE_ADAPTER: TypeAdapter[ProfessorProfile | TestProfile] = TypeAdapter(
    ProfileUnion  # type: ignore[arg-type]
)


class ProfileError(RuntimeError):
    """Raised when profile load violates FR-G08 / spec 006 rules."""


def _default_config_home() -> Path:
    """Resolve the canonical ``~/.config/paideia/immersio_email`` root."""
    return Path.home() / ".config" / "paideia" / "immersio_email"


class ProfileLoader:
    """Load a profile by name with strict 1-of-2 discovery (FR-G08).

    Args:
        config_home: Override for the default XDG path. Tests pass
            tmp_path-rooted directories here.
        credentials_precheck: Optional callable invoked with the loaded
            profile right before return. Used by the CLI to assert agenix
            env vars exist before any side-effect runs.
    """

    def __init__(
        self,
        *,
        config_home: Path | None = None,
        credentials_precheck: (Callable[[ProfessorProfile | TestProfile], None] | None) = None,
    ) -> None:
        self._config_home = config_home or _default_config_home()
        self._credentials_precheck = credentials_precheck

    def load(self, profile_name: str) -> ProfessorProfile | TestProfile:
        """Search both directories, validate, run credential precheck.

        Args:
            profile_name: The profile identifier passed to ``--profile``.

        Returns:
            The validated discriminated-union profile model.

        Raises:
            ProfileError: When 0 or 2+ matches found, or YAML/schema is
                invalid, or credentials precheck fails.
        """
        if not isinstance(profile_name, str) or not profile_name:
            raise ProfileError(f"profile_name must be non-empty string (got {profile_name!r})")

        operator_path = self._config_home / "profiles" / f"{profile_name}.yaml"
        test_path = self._config_home / "test_profiles" / f"{profile_name}.yaml"

        found_in: list[Path] = [p for p in (operator_path, test_path) if p.is_file()]

        if len(found_in) == 0:
            raise ProfileError(
                f"FR-G08: profile {profile_name!r} not found in either "
                f"{operator_path} or {test_path}"
            )
        if len(found_in) > 1:
            raise ProfileError(
                f"FR-G08: profile {profile_name!r} found in multiple "
                f"locations — must exist in exactly one. Found: "
                f"{[str(p) for p in found_in]}"
            )

        path = found_in[0]
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ProfileError(f"profile {profile_name!r} at {path}: invalid YAML — {exc}") from exc

        if not isinstance(raw, dict):
            raise ProfileError(
                f"profile {profile_name!r} at {path}: top-level YAML must be "
                f"a mapping (got {type(raw).__name__})"
            )

        try:
            profile = _PROFILE_ADAPTER.validate_python(raw)
        except ValidationError as exc:
            raise ProfileError(
                f"profile {profile_name!r} at {path}: schema validation failed:\n{exc}"
            ) from exc

        # Cross-check: operator profile must live under profiles/, test
        # under test_profiles/. Reject mismatch (FR-G08 path consistency).
        expected_dir = "profiles" if profile.profile_kind == "operator" else "test_profiles"
        if path.parent.name != expected_dir:
            raise ProfileError(
                f"profile {profile_name!r}: profile_kind={profile.profile_kind!r} "
                f"located in {path.parent.name!r} (expected {expected_dir!r})"
            )

        if self._credentials_precheck is not None:
            self._credentials_precheck(profile)

        return profile


__all__ = ["ProfileError", "ProfileLoader"]
