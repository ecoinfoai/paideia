"""Diagnostic mapping YAML loader and column-to-axis applier."""

from .apply import apply_mapping
from .loader import load_mapping

__all__ = ["load_mapping", "apply_mapping"]
