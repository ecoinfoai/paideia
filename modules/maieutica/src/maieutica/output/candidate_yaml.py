"""T040 — nested full-fidelity candidate yaml writer (``출제후보_완전판.yaml``).

``write_candidate_yaml(items, path)`` serialises ``list[QuizItemCandidate]`` to a
nested YAML file preserving full fidelity that the flattened LMS ``.xls`` cannot
carry:

- ``leap.text`` — the FULL, untruncated leap (the ``.xls`` may truncate it at
  write time, but the candidate and this yaml always keep it whole).
- ``leap.textbook_evidence`` — leap groundedness (T038), nested.
- ``option_evidence`` — the per-option evidence list (5 entries, NOT joined).
- ``textbook_evidence`` — the item-level groundedness, nested.

The ``─ 도약 ─`` separator inside ``answer_explanation_combined`` is preserved
verbatim, so a consumer can mechanically round-trip-split the combined string
back into ``wrong_explanation`` + ``leap.text``.

Output determinism (R6) is provided by
:func:`maieutica.output.determinism.dump_yaml` (``sort_keys=True``,
``allow_unicode=True``, one trailing newline) and the file is written atomically
via :func:`maieutica.output.paths.atomic_write`.

US4/T048 will extend this writer to ALL candidate metadata (review_note,
adoption_status, etc.); for now it carries the full ``model_dump`` so leap +
evidence fidelity is already guaranteed.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import QuizItemCandidate

from maieutica.output.determinism import dump_yaml
from maieutica.output.paths import atomic_write


def write_candidate_yaml(items: list[QuizItemCandidate], path: Path) -> None:
    """Write quiz candidates to the nested full-fidelity ``출제후보_완전판.yaml``.

    Serialises each candidate with Pydantic's ``model_dump`` (preserving nested
    ``leap`` and ``textbook_evidence`` objects), then dumps deterministically.
    The full ``leap.text`` is always preserved (never the ``.xls``-truncated
    form).  Written atomically — a serialisation failure leaves no partial file
    (constitution V).

    Args:
        items: Quiz candidates to serialise.
        path: Destination yaml path.  Parent directories are created if missing.
    """
    data = [item.model_dump(mode="python") for item in items]
    serialized = dump_yaml(data)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, _write)


__all__ = ["write_candidate_yaml"]
