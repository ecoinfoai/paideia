"""T029-b — yaml writer: nested full-fidelity ExamItemDraft serialisation.

``write_yaml(items, path)`` produces the nested YAML representation of
``list[ExamItemDraft]``.  Unlike the xlsx (which flattens ``textbook_evidence``
and ``distractor_rationale``), the yaml preserves all nested structures:

- ``distractor_rationale``: ``list[str]`` of 5 entries (NOT joined).
- ``textbook_evidence``: nested dict with ``source_file``, ``line``,
  ``found_text``, ``status``, ``search_term``.
- ``emphasis_class_count``: preserved as integer.

Output properties (determinism — spec R6):
- ``sort_keys=True`` — alphabetical key order regardless of insertion order.
- ``allow_unicode=True`` — Korean/Unicode chars written as-is (not \\uXXXX).
- Ends with exactly one newline.
- Two calls with the same ``items`` always produce byte-identical output.

Written atomically via ``examen.output.paths.atomic_write``.

Both ``write_xlsx`` and ``write_yaml`` must be called with the SAME item
list to satisfy SC-010 (no contradiction between xlsx and yaml artefacts).
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import ExamItemDraft

from examen.output.determinism import dump_yaml
from examen.output.paths import atomic_write


def _item_to_dict(item: ExamItemDraft) -> dict[str, object]:
    """Serialise one ExamItemDraft to a plain Python dict for yaml output.

    Uses Pydantic's ``model_dump`` with ``mode="python"`` to preserve nested
    objects (TextbookEvidence → dict) while keeping Python native types.

    Args:
        item: The exam item to serialise.

    Returns:
        Plain Python dict suitable for yaml.dump.
    """
    return item.model_dump(mode="python")


def write_yaml(items: list[ExamItemDraft], path: Path) -> None:
    """Write exam items to a nested full-fidelity yaml file.

    The file is written atomically (temp→rename) and is byte-identical
    for identical inputs (``dump_yaml`` uses ``sort_keys=True`` and
    ``allow_unicode=True``).

    Args:
        items: List of ExamItemDraft objects to write.
        path: Destination yaml path.  Parent directory must exist.

    Note:
        Pair with ``write_xlsx`` using the same ``items`` list to keep
        xlsx and yaml consistent (SC-010).
    """
    # 직렬화 먼저 — 실패 시 파일 부수효과 없음 (constitution V)
    data = [_item_to_dict(item) for item in items]
    serialized = dump_yaml(data)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, _write)


__all__ = ["write_yaml"]
