"""Typed exceptions for retro-mester input loaders.

All loaders raise ``InputError`` on boundary failures so the CLI can map
the exception to exit code 2 without importing individual loader modules.
"""

from __future__ import annotations


class InputError(Exception):
    """Raised when an input file is missing, malformed, or fails schema validation.

    Attributes:
        message: Human-readable English description of the failure.
    """


__all__ = ["InputError"]
