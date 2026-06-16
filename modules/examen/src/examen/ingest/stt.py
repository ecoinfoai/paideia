"""T055 — STT (lecture-recording) filename parsing + missing-session report.

Lecture-emphasis enrichment (US7) reads STT (speech-to-text) transcripts laid
out as::

    {stt_dir}/{week}주차/{CLASS}_{week}주차_{session}차시.txt

where ``CLASS`` is a class-section id (e.g. ``1A`` ... ``1D``).  This module
provides:

``parse_stt_filename(name)``
    Strict regex parse of a single filename → ``(class_id, week, session)`` or
    ``None`` when the name does not match the contract.  A ``None`` result is
    NEVER silently dropped by callers — it is recorded as a filename violation
    (FR-024).

``scan_stt_dir(stt_dir)``
    Recursively scan a directory for ``*.txt`` STT files and return an
    :class:`SttScan` carrying the parsed sessions, the human-readable list of
    missing sessions, the offending (unparseable) filenames, and the
    expected/found counts.

Degrade contract (FR-026 / SC-013): if ``stt_dir`` is ``None`` or does not
exist, :func:`scan_stt_dir` returns an empty :class:`SttScan` (expected=0,
found=0) without raising — the Core pipeline must complete regardless.

The "missing" definition is deterministic: the expected grid is
``(all class_ids observed across the whole dir) × (per week, the union of
session numbers observed across classes that week)``.  Any grid cell with no
file is reported as missing.  This is asymmetric on purpose — a class that was
never observed at all does not invent sessions, but a class that *is* observed
elsewhere and lacks a session another class taught that week IS flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Strict filename contract:  {CLASS}_{WEEK}주차_{SESSION}차시  (optional .txt)
# CLASS = a single digit followed by an uppercase letter A-D (e.g. 1A..1D).
_STT_NAME_RE = re.compile(r"^(?P<cls>\d[A-D])_(?P<week>\d+)주차_(?P<session>\d+)차시$")


def parse_stt_filename(name: str) -> tuple[str, int, int] | None:
    """Strictly parse an STT filename into ``(class_id, week, session)``.

    The ``.txt`` suffix (if present) is stripped before matching.  The match is
    strict: separators, the ``주차``/``차시`` tokens, and the ``\\d[A-D]`` class
    shape must all be present, otherwise ``None`` is returned (and the caller
    records the name as a violation rather than dropping it silently).

    Args:
        name: A filename (with or without the ``.txt`` extension).

    Returns:
        ``(class_id, week, session)`` on a successful strict match, else
        ``None``.
    """
    stem = name[:-4] if name.endswith(".txt") else name
    match = _STT_NAME_RE.match(stem)
    if match is None:
        return None
    return (
        match.group("cls"),
        int(match.group("week")),
        int(match.group("session")),
    )


@dataclass(frozen=True)
class SttSession:
    """One parsed STT transcript session.

    Attributes:
        class_id: Class-section id (e.g. ``"1A"``).
        week: Teaching week number.
        session: Session (차시) number within the week.
        path: Path to the source ``.txt`` file.
        text: Full UTF-8 transcript text of the session.
    """

    class_id: str
    week: int
    session: int
    path: Path
    text: str


@dataclass(frozen=True)
class SttScan:
    """Result of scanning an STT directory.

    Attributes:
        sessions: All successfully parsed sessions (sorted deterministically).
        missing: Human-readable missing-session labels (``"1C/11주차/2차시"``),
            sorted.
        filename_violations: Offending filenames that did not parse, sorted.
        expected: Size of the expected (class × week × session) grid.
        found: Number of parsed sessions.
    """

    sessions: list[SttSession] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    filename_violations: list[str] = field(default_factory=list)
    expected: int = 0
    found: int = 0


def _missing_label(class_id: str, week: int, session: int) -> str:
    """Return the human-readable missing-session label ``"1C/11주차/2차시"``."""
    return f"{class_id}/{week}주차/{session}차시"


def scan_stt_dir(stt_dir: Path | None) -> SttScan:
    """Scan ``stt_dir`` recursively for STT ``.txt`` files.

    Files whose names do not parse (see :func:`parse_stt_filename`) are recorded
    in ``filename_violations`` and excluded from ``sessions``.  The missing grid
    is derived as described in the module docstring.

    Degrade: if ``stt_dir`` is ``None`` or does not exist, an empty
    :class:`SttScan` is returned (no raise).

    Args:
        stt_dir: Root directory of STT transcripts, or ``None``.

    Returns:
        A deterministic :class:`SttScan`.
    """
    if stt_dir is None or not stt_dir.exists():
        return SttScan()

    sessions: list[SttSession] = []
    violations: list[str] = []

    for path in sorted(stt_dir.glob("**/*.txt")):
        parsed = parse_stt_filename(path.name)
        if parsed is None:
            violations.append(path.name)
            continue
        class_id, week, session = parsed
        sessions.append(
            SttSession(
                class_id=class_id,
                week=week,
                session=session,
                path=path,
                text=path.read_text(encoding="utf-8"),
            )
        )

    sessions.sort(key=lambda s: (s.week, s.class_id, s.session))

    # Expected grid: all observed class_ids × (per week, union of sessions).
    all_classes = sorted({s.class_id for s in sessions})
    sessions_by_week: dict[int, set[int]] = {}
    present: set[tuple[str, int, int]] = set()
    for s in sessions:
        sessions_by_week.setdefault(s.week, set()).add(s.session)
        present.add((s.class_id, s.week, s.session))

    missing: list[str] = []
    expected = 0
    for week in sorted(sessions_by_week):
        for session in sorted(sessions_by_week[week]):
            for class_id in all_classes:
                expected += 1
                if (class_id, week, session) not in present:
                    missing.append(_missing_label(class_id, week, session))

    missing.sort()

    return SttScan(
        sessions=sessions,
        missing=missing,
        filename_violations=sorted(violations),
        expected=expected,
        found=len(sessions),
    )


__all__ = [
    "parse_stt_filename",
    "SttSession",
    "SttScan",
    "scan_stt_dir",
]
