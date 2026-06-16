"""T048 — nested full-fidelity candidate yaml writer (``출제후보_완전판.yaml``).

``write_candidate_yaml(quiz_items, formative_items, path)`` serialises BOTH
``list[QuizItemCandidate]`` and ``list[FormativeItemCandidate]`` to a single
nested YAML file preserving full fidelity that the flattened LMS files cannot
carry.

Top-level structure::

    quiz:      [list of full QuizItemCandidate model_dump dicts]
    formative: [list of full FormativeItemCandidate model_dump dicts]

Quiz section preserves:
- ``leap.text`` — the FULL, untruncated leap (the ``.xls`` may truncate it at
  write time, but the candidate and this yaml always keep it whole).
- ``leap.textbook_evidence`` — leap groundedness (T038), nested.
- ``option_evidence`` — the per-option evidence list (5 entries, NOT joined).
- ``textbook_evidence`` — the item-level groundedness, nested.
- ``key_concept``, ``question_type``, ``difficulty``, ``review_note``,
  ``adoption_status`` — all FR-015 metadata.

Formative section preserves:
- ``topic``, ``rubric_high``/``rubric_mid``/``rubric_low``,
  ``support_high``/``support_mid``/``support_low``, ``keywords``,
  ``textbook_evidence``, ``review_note``, ``adoption_status``.

The ``─ 도약 ─`` separator inside quiz ``answer_explanation_combined`` is preserved
verbatim, so a consumer can mechanically round-trip-split the combined string
back into ``wrong_explanation`` + ``leap.text``.

Output determinism (R6) is provided by
:func:`maieutica.output.determinism.dump_yaml` (``sort_keys=True``,
``allow_unicode=True``, one trailing newline) and the file is written atomically
via :func:`maieutica.output.paths.atomic_write`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from paideia_shared.schemas import FormativeItemCandidate, QuizItemCandidate

from maieutica.output.determinism import dump_yaml
from maieutica.output.paths import atomic_write


def write_candidate_yaml(
    quiz_items: list[QuizItemCandidate],
    formative_items: list[FormativeItemCandidate],
    path: Path,
) -> None:
    """Write quiz + formative candidates to the nested full-fidelity yaml.

    Serialises both candidate lists under top-level keys ``"quiz"`` and
    ``"formative"`` using Pydantic's ``model_dump`` (preserving all nested
    objects).  Written atomically — a serialisation failure leaves no partial
    file (constitution V).

    The full ``leap.text`` is always preserved for quiz items (never the
    ``.xls``-truncated form).

    Args:
        quiz_items: Quiz candidates to serialise.
        formative_items: Formative candidates to serialise.
        path: Destination yaml path.  Parent directories are created if missing.
    """
    data = {
        "quiz": [item.model_dump(mode="python") for item in quiz_items],
        "formative": [item.model_dump(mode="python") for item in formative_items],
    }
    serialized = dump_yaml(data)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, _write)


def read_candidate_yaml(
    path: Path,
) -> tuple[list[QuizItemCandidate], list[FormativeItemCandidate]]:
    """Read the full-fidelity candidate yaml back to typed models.

    Parses the ``출제후보_완전판.yaml`` produced by
    :func:`write_candidate_yaml` and reconstructs each entry via Pydantic's
    ``model_validate``.  Used by the ``verify`` CLI step (T053) to locate and
    re-validate a previously built run's candidates without re-running the full
    pipeline.

    Args:
        path: Path to the full-fidelity candidate yaml (must exist).

    Returns:
        ``(quiz_items, formative_items)`` — lists of typed, frozen Pydantic
        models.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the yaml structure is invalid (missing top-level keys or
            model validation fails on any entry).
    """
    if not path.is_file():
        raise FileNotFoundError(f"candidate yaml not found: {path}")

    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"candidate yaml must be a mapping, got {type(raw).__name__}: {path}")

    quiz_raw = raw.get("quiz")
    formative_raw = raw.get("formative")
    if quiz_raw is None or formative_raw is None:
        raise ValueError(f"candidate yaml must have 'quiz' and 'formative' top-level keys: {path}")

    quiz_items = [QuizItemCandidate.model_validate(d) for d in quiz_raw]
    formative_items = [FormativeItemCandidate.model_validate(d) for d in formative_raw]
    return quiz_items, formative_items


__all__ = ["read_candidate_yaml", "write_candidate_yaml"]
