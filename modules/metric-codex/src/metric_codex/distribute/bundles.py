"""T050 — Per-advisor bundle grouping and writing for metric-codex.

Provides:
- ``group_by_advisor`` — partition student md files by advisor assignment.
- ``write_advisor_bundles`` — copy each advisee's md to the advisor's Gold dir
  and write a deterministic ``_index.md``.

No-cross-leak guarantee (FR-017/SC-003/SKIP-03): the ENTIRE ``지도교수별/`` tree
is cleared once before writing, so stale files — including a whole directory for
an advisor dropped from the new roster — never linger across runs.
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
) -> tuple[dict[str, list[Path]], list[str], dict[str, str | None]]:
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
        A three-tuple ``(per_advisor, unassigned_student_ids, names)`` where:

        - ``per_advisor``: ``{advisor_id: [sorted list of Path]}`` — each path
          is the student's Gold md file; lists are sorted deterministically.
        - ``unassigned_student_ids``: sorted list of student_ids with no roster
          entry.
        - ``names``: ``{student_id: name_kr | None}`` for every student md
          found (name parsed from the filename), so the caller need not re-walk
          ``학생별/``.

    Raises:
        LocatedInputError: If ``학생별/`` is missing (generate not yet run) or any
            md filename does not begin with a 10-digit student_id.
    """
    student_dir = gold_dir / "학생별"
    if not student_dir.is_dir():
        raise LocatedInputError(
            "'학생별' not found — run generate before distribute",
            file=str(student_dir),
            expected="a 학생별/ directory with one md per student",
            actual="missing",
        )
    md_files = sorted(student_dir.glob("*.md"))

    sid_to_advisor: dict[str, str] = {e.student_id: e.advisor_id for e in roster}

    per_advisor: dict[str, list[Path]] = {}
    unassigned: list[str] = []
    names: dict[str, str | None] = {}

    for md_path in md_files:
        sid = _parse_student_id(md_path.name, md_path)
        names[sid] = _parse_name_from_stem(md_path.stem)
        advisor_id = sid_to_advisor.get(sid)
        if advisor_id is not None:
            per_advisor.setdefault(advisor_id, []).append(md_path)
        else:
            unassigned.append(sid)

    # Sort each advisor's file list for determinism.
    for advisor_id in per_advisor:
        per_advisor[advisor_id] = sorted(per_advisor[advisor_id])

    return per_advisor, sorted(unassigned), names


def write_advisor_bundles(
    *,
    gold_dir: Path,
    per_advisor: dict[str, list[Path]],
) -> None:
    """Write per-advisor Gold bundles under ``gold_dir/지도교수별/``.

    1. Clears the ENTIRE ``지도교수별/`` tree once, so a re-run with a different
       roster leaves no stale advisee files — including a whole directory for an
       advisor dropped from the new roster (FR-017/SC-003/SKIP-03).
    2. For each advisor, copies each advisee's md content atomically to
       ``{gold_dir}/지도교수별/{advisor_id}/{filename}``.
    3. Writes a deterministic ``_index.md`` listing all advisees
       (student_id + name if parseable from the filename).

    Security (defense-in-depth): every resolved advisor directory is asserted to
    remain inside ``지도교수별/`` BEFORE any destructive op, so a malformed
    ``advisor_id`` (path traversal) cannot escape — even if the schema pattern
    were bypassed.

    The copy writes the SOURCE FILE's bytes (not re-serialised), so the
    output is byte-identical to the student Gold md and does not introduce
    any new content.

    Args:
        gold_dir: The Gold-layer directory for the semester/course.
        per_advisor: ``{advisor_id: [list of md Path]}`` from
            :func:`group_by_advisor`.

    Raises:
        LocatedInputError: If any ``advisor_id`` resolves outside ``지도교수별/``.
    """
    bundle_root = gold_dir / "지도교수별"
    resolved_root = bundle_root.resolve()

    # Defense-in-depth: validate EVERY advisor dir stays inside the bundle root
    # BEFORE the destructive clear, so a path-traversal advisor_id aborts the
    # whole operation without touching the filesystem.
    for advisor_id in per_advisor:
        adv_dir = bundle_root / advisor_id
        if not adv_dir.resolve().is_relative_to(resolved_root):
            raise LocatedInputError(
                "advisor_id escapes the 지도교수별 bundle root",
                file=str(adv_dir),
                expected=f"a path inside {bundle_root}",
                actual=advisor_id,
            )

    # Clear the whole tree once — drops stale dirs for removed advisors too.
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True)

    for advisor_id, md_paths in sorted(per_advisor.items()):
        adv_dir = bundle_root / advisor_id
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


__all__ = [
    "group_by_advisor",
    "write_advisor_bundles",
    "_parse_name_from_stem",
    "_parse_student_id",
]
