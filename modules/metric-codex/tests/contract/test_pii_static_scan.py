"""PII static-scan contract test for metric-codex templates (T056).

Two responsibilities:
1. Load each example template via its real loader to prove the file is valid and
   immediately usable by operators (T057 examples are inert docs otherwise).
2. Scan every file under ``modules/metric-codex/templates/`` for real PII
   (email, 10-digit student id outside the sentinel prefix, counseling markers)
   and assert 0 hits.

Proof-of-non-vacuity
--------------------
Every scan helper is also exercised against an INLINE synthetic violation
fixture (never committed as a separate file) to confirm it *would* catch a
real leak — a bug in the regex that lets real PII slip through would also let
the PASS case silently succeed (false negative).

Placeholder convention
----------------------
A 10-digit run (``\\b\\d{10}\\b``) is ALLOWED only when it starts with the
sentinel prefix ``000000`` (six zeros).  Any other 10-digit run is a
violation.  This means synthetic student IDs like ``0000000001`` pass while
real-looking IDs like ``2026194023`` are caught.

FR-020 counseling/life-info markers
------------------------------------
metric-codex ingests ONLY learning-data sources (성적, 출석, immersio Silver,
needs-map Silver).  Templates must not advertise out-of-scope counseling or
life-info fields.  The scan checks for a small set of markers: 상담, 생활기록,
가정환경, 징계, 건강상태.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# This file lives at modules/metric-codex/tests/contract/
_MODULE_ROOT = Path(__file__).resolve().parents[2]  # modules/metric-codex/
_REPO_ROOT = _MODULE_ROOT.parents[1]  # paideia root
_TEMPLATES_DIR = _MODULE_ROOT / "templates"


# ---------------------------------------------------------------------------
# PII / out-of-scope scan patterns
# ---------------------------------------------------------------------------

# Real-looking email addresses.
_EMAIL_PAT: re.Pattern[str] = re.compile(
    r"[\w.%+\-]+@[\w.\-]+\.\w{2,}",
)

# 10-digit run that does NOT start with the sentinel prefix (000000...).
# Allowed: 0000000001, 0000000002 (6+ leading zeros).
# Violation: 2026194023, 1234567890, etc.
_REAL_STUDENT_ID_PAT: re.Pattern[str] = re.compile(
    r"\b(?!000000)\d{10}\b",
)

# Out-of-scope counseling / life-info markers (FR-020).
# metric-codex ingest only consumes learning-data sources;
# these fields are never acceptable in any template.
_COUNSELING_MARKERS: tuple[str, ...] = (
    "상담",
    "생활기록",
    "가정환경",
    "징계",
    "건강상태",
)
_COUNSELING_PAT: re.Pattern[str] = re.compile(
    "|".join(re.escape(m) for m in _COUNSELING_MARKERS),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_text(
    text: str,
) -> list[tuple[str, str]]:
    """Return a list of (category, matched_literal) PII hits in *text*.

    Lines starting with '#' are treated as comments and skipped.  The
    counseling-marker scan applies even to comments to prevent an operator
    from inadvertently documenting the field names.

    Args:
        text: Full content of a template file.

    Returns:
        List of ``(category, literal)`` tuples; empty list means no violations.
    """
    hits: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        # Comment lines are skipped for email / student-id checks only (the
        # placeholder examples are self-documenting via comments; counseling
        # markers are never acceptable even in comments).
        is_comment = stripped.startswith("#")

        if not is_comment:
            for m in _EMAIL_PAT.finditer(line):
                hits.append(("email", m.group(0)))
            for m in _REAL_STUDENT_ID_PAT.finditer(line):
                hits.append(("real_student_id", m.group(0)))

        for m in _COUNSELING_PAT.finditer(line):
            hits.append(("counseling_marker", m.group(0)))

    return hits


# ---------------------------------------------------------------------------
# T056 PASS case — each template file contains 0 PII hits
# ---------------------------------------------------------------------------


def _template_files() -> list[Path]:
    """Return all non-.gitkeep files under the templates directory."""
    return [
        p
        for p in _TEMPLATES_DIR.rglob("*")
        if p.is_file() and p.suffix != "" and p.name != ".gitkeep"
    ]


@pytest.mark.parametrize(
    "template_path",
    _template_files(),
    ids=lambda p: p.name,
)
def test_template_contains_no_pii(template_path: Path) -> None:
    """PASS: every template file under templates/ carries 0 PII hits."""
    text = template_path.read_text(encoding="utf-8")
    hits = _scan_text(text)
    assert not hits, (
        f"PII / out-of-scope marker found in {template_path.relative_to(_REPO_ROOT)}:\n"
        + "\n".join(f"  [{cat}] {lit!r}" for cat, lit in hits)
    )


# ---------------------------------------------------------------------------
# T056 Proof-of-non-vacuity — synthetic violation must be caught
# ---------------------------------------------------------------------------

# Inline synthetic violation fixture.  This content is NEVER written to disk.
# Each check category must fire at least once to prove the detector is live.
_VIOLATION_FIXTURE = """\
# Intentional PII violations — meta-test fixture (T056 proof-of-non-vacuity).
# DO NOT IMPORT OR USE IN PRODUCTION.

real_email: "violator@university.ac.kr"
real_student_id: "2026194023"
counseling_marker: "상담기록 가정환경"
"""

_COUNSELING_FIXTURE = """\
field: "생활기록부 및 징계 내역"
"""


def test_email_scan_catches_real_email() -> None:
    """Detector must flag a real-shaped email address."""
    hits = _scan_text("contact: user@example.ac.kr")
    cats = [c for c, _ in hits]
    assert "email" in cats, (
        "Email regex false-negative: 'user@example.ac.kr' was not flagged."
    )


def test_student_id_scan_catches_real_id() -> None:
    """Detector must flag a 10-digit id that lacks the 000000 sentinel prefix."""
    hits = _scan_text("id: 2026194023")
    cats = [c for c, _ in hits]
    assert "real_student_id" in cats, (
        "Student-ID regex false-negative: '2026194023' was not flagged."
    )


def test_student_id_scan_allows_sentinel() -> None:
    """Sentinel-prefixed 10-digit ids (000000xxxx) must NOT be flagged."""
    hits = _scan_text("student_id: '0000000001'")
    cats = [c for c, _ in hits]
    assert "real_student_id" not in cats, (
        "Student-ID regex false-positive: sentinel id '0000000001' should not be flagged."
    )


def test_counseling_scan_catches_marker() -> None:
    """Detector must flag an out-of-scope counseling marker (FR-020)."""
    hits = _scan_text(_COUNSELING_FIXTURE)
    cats = [c for c, _ in hits]
    assert "counseling_marker" in cats, (
        "Counseling-marker regex false-negative: '생활기록' / '징계' was not flagged."
    )


def test_all_violation_categories_fire_on_fixture() -> None:
    """All three PII categories must fire on the combined violation fixture.

    A failing test here means a regex regression — the detector is a false
    negative and would let real PII through in production.
    """
    hits = _scan_text(_VIOLATION_FIXTURE)
    cats = {c for c, _ in hits}
    expected = {"email", "real_student_id", "counseling_marker"}
    missing = expected - cats
    assert not missing, (
        f"T056 meta-test failure: categories {missing!r} did not fire on the "
        f"intentional-violation fixture — false-negative regression."
    )


def test_no_violation_file_committed_to_repo() -> None:
    """No ``_pii_violation.py.bad`` file exists in the repository tree.

    The violation fixture is inlined above; committing a separate file would
    be misclassified as production content by the scanner.
    """
    bad_paths = list(_REPO_ROOT.rglob("_pii_violation.py.bad"))
    assert not bad_paths, (
        f"T056: do not commit _pii_violation.py.bad — inline the fixture in "
        f"tests instead. Found: {bad_paths!r}"
    )


# ---------------------------------------------------------------------------
# T056 PASS case — loader round-trips (examples validate against real loaders)
# ---------------------------------------------------------------------------


def test_school_excel_map_example_loads() -> None:
    """성적출석_map.example.yaml must validate via load_school_excel_map."""
    from metric_codex.ingest.bronze_copies import SchoolExcelMap, load_school_excel_map

    path = _TEMPLATES_DIR / "성적출석_map.example.yaml"
    assert path.is_file(), f"Template not found: {path}"
    result = load_school_excel_map(path)
    assert isinstance(result, SchoolExcelMap)
    assert result.columns.student_id  # must map at least the id column


def test_roster_example_loads() -> None:
    """지도교수배정.example.yaml must validate via load_roster."""
    from metric_codex.distribute.roster import load_roster
    from paideia_shared.schemas.metric_codex import AdvisorRosterEntry

    path = _TEMPLATES_DIR / "지도교수배정.example.yaml"
    assert path.is_file(), f"Template not found: {path}"
    entries = load_roster(path)
    assert len(entries) >= 1
    assert all(isinstance(e, AdvisorRosterEntry) for e in entries)


def test_question_set_example_loads() -> None:
    """question_set.example.yaml must validate via load_question_set → QuestionSet."""
    from metric_codex.retrieve.query import QuestionSet, load_question_set

    path = _TEMPLATES_DIR / "question_set.example.yaml"
    assert path.is_file(), f"Template not found: {path}"
    qs = load_question_set(path)
    assert isinstance(qs, QuestionSet)
    assert len(qs.questions) >= 1


# ---------------------------------------------------------------------------
# T056 Optional — gitignore assertions (cheap, mirrors retro-mester)
# ---------------------------------------------------------------------------


def test_data_dir_is_gitignored() -> None:
    """Repo-root .gitignore must exclude data/ to prevent PII commits."""
    gitignore = _REPO_ROOT / ".gitignore"
    assert gitignore.exists(), f"No .gitignore found at {gitignore}"
    content = gitignore.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in content.splitlines()]
    data_excluded = any(
        ln in ("data/", "data") or ln.startswith("data/")
        for ln in lines
        if not ln.startswith("#") and ln
    )
    assert data_excluded, (
        f"data/ is not excluded in {gitignore}. "
        "Add 'data/' to .gitignore to prevent student PII from being committed."
    )


def test_templates_dir_is_tracked() -> None:
    """templates/ (example files) must NOT be gitignored — they are reference docs.

    Runs ``git check-ignore -q`` against the templates directory.  An exit
    code of 1 means the path is NOT ignored (expected for reference docs).
    If git is unavailable the test is skipped rather than failed.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", str(_TEMPLATES_DIR)],  # noqa: S607
            capture_output=True,
            cwd=str(_REPO_ROOT),
            timeout=10,
        )
        # check-ignore exits 0 if ignored, 1 if NOT ignored.
        assert result.returncode == 1, (
            f"templates/ appears to be gitignored but should be tracked: "
            f"{_TEMPLATES_DIR}"
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("git not available — skipping gitignore assertion")
