"""Ingest violation reporting (US2 Fail-Fast)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IngestViolation:
    """One concrete violation with locator and expected/found context.

    Attributes:
        file_path: Path-style string identifying the source artefact.
        row_or_item_id: Optional row number, item_no, or composite identifier.
        column_or_field: Optional column header, mapping field, or model field.
        expected: Human-readable description of the expected value(s).
        found: Concrete bad value or None when not applicable.
        severity: 'error' (default; blocks Silver write) or 'warning'.
    """

    file_path: str
    row_or_item_id: str | int | None
    column_or_field: str | None
    expected: str
    found: object | None
    severity: str = "error"


@dataclass
class IngestValidationError(Exception):
    """Aggregate exception carrying every violation discovered in a single run."""

    violations: list[IngestViolation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.violations, list):
            raise TypeError(
                f"IngestValidationError: violations must be list, got "
                f"{type(self.violations).__name__}."
            )
        for entry in self.violations:
            if not isinstance(entry, IngestViolation):
                raise TypeError(
                    f"IngestValidationError: each entry must be IngestViolation, "
                    f"got {type(entry).__name__}."
                )
        super().__init__(self._render())

    def _render(self) -> str:
        lines = [
            "ERROR: Input validation failed. Silver outputs not written.",
            "",
        ]
        for index, violation in enumerate(self.violations, start=1):
            locator_parts: list[str] = [violation.file_path]
            if violation.row_or_item_id is not None:
                locator_parts.append(f"row {violation.row_or_item_id}")
            if violation.column_or_field is not None:
                locator_parts.append(f'column "{violation.column_or_field}"')
            lines.append(f"  [{index}] " + ", ".join(locator_parts))
            lines.append(f"      Expected: {violation.expected}")
            lines.append(f"      Found:    {violation.found!r}")
        lines.append("")
        lines.append(f"Total: {len(self.violations)} violation(s). Fix inputs and re-run.")
        return "\n".join(lines)


def raise_if_any(violations: list[IngestViolation]) -> None:
    """Raise IngestValidationError if any violation is present."""
    if violations:
        raise IngestValidationError(violations=violations)
