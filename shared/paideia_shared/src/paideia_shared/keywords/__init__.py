"""Free-text keyword dictionary (M8 in data-model.md).

Pydantic schema + ``load(language)`` helper. Dictionaries themselves live as
``{language}.yaml`` files inside this package and ship in the wheel via
``hatch.build.targets.wheel.force-include`` (configured at the package
``pyproject.toml`` level).

The dictionary is shared with immersio Phase 5 per FR-026; bumping its contents
constitutes a paideia minor-version break.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class KeywordEntry(BaseModel):
    """One category → patterns mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Annotated[str, Field(min_length=1, max_length=50)]
    patterns: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]


class KeywordDictionary(BaseModel):
    """Validated representation of a ``{lang}.yaml`` keyword dictionary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: Annotated[str, Field(pattern=r"^[a-z]{2}$")]
    version: Annotated[int, Field(ge=1)]
    entries: Annotated[list[KeywordEntry], Field(min_length=1)]

    @model_validator(mode="after")
    def v1_categories_unique(self) -> Self:
        cats = [e.category for e in self.entries]
        if len(cats) != len(set(cats)):
            seen: set[str] = set()
            duplicates: list[str] = []
            for c in cats:
                if c in seen:
                    duplicates.append(c)
                seen.add(c)
            raise ValueError(
                f"KeywordDictionary V1: duplicate categories: {sorted(set(duplicates))}."
            )
        return self


def load(language: str = "ko") -> KeywordDictionary:
    """Load the packaged keyword dictionary by ISO 639-1 language code.

    Args:
        language: Two-letter lowercase ISO 639-1 code (e.g. ``"ko"``).

    Returns:
        Validated :class:`KeywordDictionary` instance.

    Raises:
        FileNotFoundError: If ``{language}.yaml`` is not bundled in the package.
        ValueError: If YAML content fails Pydantic validation.
    """
    if not (len(language) == 2 and language.isascii() and language.islower()):
        raise ValueError(
            f"load(language={language!r}): expected lowercase ISO 639-1 (2 ASCII letters)."
        )
    resource = files(__package__) / f"{language}.yaml"
    if not resource.is_file():
        raise FileNotFoundError(
            f"Keyword dictionary not bundled: {language}.yaml (package={__package__})."
        )
    yaml_text = resource.read_text(encoding="utf-8")
    return KeywordDictionary.model_validate(yaml.safe_load(yaml_text))
