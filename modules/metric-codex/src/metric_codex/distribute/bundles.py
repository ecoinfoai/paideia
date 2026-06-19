"""T050 — Per-advisor bundle grouping and writing for metric-codex.

Provides:
- ``group_by_advisor`` — partition student md files by advisor assignment.
- ``write_advisor_bundles`` — copy each advisee's md to the advisor's Gold dir
  and write a deterministic ``_index.md``.

No-cross-leak guarantee (FR-017/SC-003/SKIP-03): each advisor directory is
cleared before writing, so stale files from a prior roster never linger.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from paideia_shared.schemas.metric_codex import AdvisorRosterEntry

from metric_codex.errors import LocatedInputError
from metric_codex.output.determinism import atomic_write

_STUDENT_ID_RE = re.compile(r"^(\d{10})")


def _parse_student_id(filename: str, md_path: Path) -> str:
    """Extract the leading 10-digit student_id from a filename stem.

    Args:
        filename: The filename (e.g. ``"2026000001_김철수.md"``).
        md_path: Full path for error reporting.

    Returns:
        The 10-digit student_id string.

    Raises:
        LocatedInputError: If the filename stem does not begin with 10 digits.
    """
    stem = Path(filename).stem
    m = _STUDENT_ID_RE.match(stem)
    if m is None:
        raise LocatedInputError(
            "Gold 학생별 file name does not begin with a 10-digit student_id",
            file=str(md_path),
            expected="^\\d{10} prefix in filename stem",
            actual=stem,
        )
    return m.group(1)


def _parse_name_from_stem(stem: str) -> str | None:
    """Extract the Korean name portion from a filename stem.

    Expected pattern: ``{student_id}_{name}`` or ``{student_id}``.

    Args:
        stem: Filename stem without extension.

    Returns:
        Name string if present after the underscore, else ``None``.
    """
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[1]:
        return parts[1]
    return None


def group_by_advisor(
    *,
    gold_dir: Path,
    roster: list[AdvisorRosterEntry],
) -> tuple[dict[str, list[Path]], list[str]]:
    """Partition Gold student md files by advisor assignment.

    Enumerates ``gold_dir/학생별/*.md``.  For each file, parses the leading
    10 characters of the filename stem as a ``student_id``.  Students found in
    the roster are placed in their advisor's group; students absent from the
    roster are added to the unassigned list.

    Args:
        gold_dir: The Gold-layer directory for the semester/course.  Must
            contain a ``학생별/`` subdirectory with one ``.md`` per student.
        roster: Validated roster entries from :func:`metric_codex.distribute.roster.load_roster`.

    Returns:
        A two-tuple ``(per_advisor, unassigned_student_ids)`` where:

        - ``per_advisor``: ``{advisor_id: [sorted list of Path]}`` — each path
          is the student's Gold md file; lists are sorted deterministically.
        - ``unassigned_student_ids``: sorted list of student_ids with no roster
          entry.

    Raises:
        LocatedInputError: If any md filename does not begin with a 10-digit
            student_id.
    """
    student_dir = gold_dir / "학생별"
    md_files = sorted(student_dir.glob("*.md"))

    sid_to_advisor: dict[str, str] = {e.student_id: e.advisor_id for e in roster}

    per_advisor: dict[str, list[Path]] = {}
    unassigned: list[str] = []

    for md_path in md_files:
        sid = _parse_student_id(md_path.name, md_path)
        advisor_id = sid_to_advisor.get(sid)
        if advisor_id is not None:
            per_advisor.setdefault(advisor_id, []).append(md_path)
        else:
            unassigned.append(sid)

    # Sort each advisor's file list for determinism.
    for advisor_id in per_advisor:
        per_advisor[advisor_id] = sorted(per_advisor[advisor_id])

    return per_advisor, sorted(unassigned)


def write_advisor_bundles(
    *,
    gold_dir: Path,
    per_advisor: dict[str, list[Path]],
) -> None:
    """Write per-advisor Gold bundles under ``gold_dir/지도교수별/``.

    For each advisor:

    1. Clears (and recreates) their directory to prevent stale-file cross-leak
       from a prior roster (FR-017/SC-003/SKIP-03).
    2. Copies each advisee's md content atomically to
       ``{gold_dir}/지도교수별/{advisor_id}/{filename}``.
    3. Writes a deterministic ``_index.md`` listing all advisees
       (student_id + name if parseable from the filename).

    The copy writes the SOURCE FILE's bytes (not re-serialised), so the
    output is byte-identical to the student Gold md and does not introduce
    any new content.

    Args:
        gold_dir: The Gold-layer directory for the semester/course.
        per_advisor: ``{advisor_id: [list of md Path]}`` from
            :func:`group_by_advisor`.
    """
    bundle_root = gold_dir / "지도교수별"
    bundle_root.mkdir(parents=True, exist_ok=True)

    for advisor_id, md_paths in sorted(per_advisor.items()):
        adv_dir = bundle_root / advisor_id

        # Clear the dir to prevent stale cross-leak (re-running with a
        # different roster must not leave files from the previous assignment).
        if adv_dir.exists():
            shutil.rmtree(adv_dir)
        adv_dir.mkdir(parents=True)

        # Copy each advisee's md atomically.
        for md_path in md_paths:
            dest = adv_dir / md_path.name
            content = md_path.read_bytes()

            def _write_copy(tmp: Path, _content: bytes = content) -> None:
                tmp.write_bytes(_content)

            atomic_write(dest, _write_copy)

        # Build deterministic _index.md.
        lines: list[str] = [f"# {advisor_id} 지도학생 목록\n"]
        for md_path in md_paths:
            stem = md_path.stem
            sid_m = _STUDENT_ID_RE.match(stem)
            sid_str = sid_m.group(1) if sid_m else stem
            name = _parse_name_from_stem(stem)
            if name:
                lines.append(f"- {sid_str} {name}\n")
            else:
                lines.append(f"- {sid_str}\n")

        index_content = "".join(lines)
        index_path = adv_dir / "_index.md"

        def _write_index(tmp: Path, _text: str = index_content) -> None:
            tmp.write_text(_text, encoding="utf-8")

        atomic_write(index_path, _write_index)


__all__ = ["group_by_advisor", "write_advisor_bundles"]
