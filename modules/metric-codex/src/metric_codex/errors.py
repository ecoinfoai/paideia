"""Module-wide located boundary error for metric-codex.

All ingest/validation units raise ``LocatedInputError`` on boundary failures
so the CLI entry point can map the exception to exit code 2 via its existing
``except ValueError`` trap.
"""

from __future__ import annotations


class LocatedInputError(ValueError):
    """Raised when an input file or cell fails boundary validation.

    Carries optional location metadata (file, row, column) and expected/actual
    value context.  Subclasses ``ValueError`` intentionally so the CLI
    ``app()`` handler catches it as exit code 2 without any additional
    import.

    Attributes:
        message: Human-readable English description of the failure.
        file: Source file path or name where the error occurred (optional).
        row: 1-based row number in the source (optional).
        column: Column name or header text in the source (optional).
        expected: Description of the expected form (optional).
        actual: The offending value as a string (optional).
    """

    def __init__(
        self,
        message: str,
        *,
        file: str | None = None,
        row: int | None = None,
        column: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        """Initialise a located error.

        Args:
            message: Human-readable English description of the failure.
            file: Source file path or name (optional).
            row: 1-based row number in the source (optional).
            column: Column header text in the source (optional).
            expected: Description of the expected form (optional).
            actual: The offending value as a string (optional).
        """
        self.message = message
        self.file = file
        self.row = row
        self.column = column
        self.expected = expected
        self.actual = actual
        super().__init__(str(self))

    def __str__(self) -> str:
        """Render a single located line omitting absent fields.

        Format: ``<file>:<row>:<column>: <message> (expected <expected>, got <actual>)``

        Absent prefix parts are omitted; the suffix ``(expected ..., got ...)``
        appears only when at least one of ``expected``/``actual`` is set.

        Returns:
            Human-readable located error string.
        """
        parts: list[str] = []
        if self.file is not None:
            parts.append(self.file)
        if self.row is not None:
            parts.append(str(self.row))
        if self.column is not None:
            parts.append(self.column)

        prefix = ":".join(parts)
        body = f"{prefix}: {self.message}" if prefix else self.message

        if self.expected is not None and self.actual is not None:
            body += f" (expected {self.expected}, got {self.actual})"
        elif self.expected is not None:
            body += f" (expected {self.expected})"
        elif self.actual is not None:
            body += f" (got {self.actual})"

        return body


__all__ = ["LocatedInputError"]
