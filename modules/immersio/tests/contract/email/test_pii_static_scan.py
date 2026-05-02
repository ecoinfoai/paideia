"""Bidirectional PII static-scan contract test (Reflag #1 / qa-engineer N2).

Two scenarios prove the static-search regex set is *both* a clean-pass
detector for placeholder-only inputs *and* a true-positive detector for
intentional-violation fixtures. Without the FAIL-case fixture, a regex
regression that lets real PII slip through would also let the PASS case
silently succeed (false negative).

PASS case: ``modules/immersio/docs/email_profile_example.yaml`` and
``test_profile_example.yaml`` — placeholder-only, must produce 0 hits.

FAIL case: an inline fixture with one real-shape student id + email
+ Korean name-role + institution. Each ADR-009 PII pattern MUST match
at least once — proves the detector still catches actual violations.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Repo root: this file lives at modules/immersio/tests/contract/email/
_REPO_ROOT = Path(__file__).resolve().parents[5]


# 4 PII-shape patterns from ADR-009 (real_email / student_id /
# korean_name_role / school_terms). The wider regex set lives in
# test_static_no_hardcoding.py — this contract test isolates the PII
# subset because that is what SC-011 names directly.
_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "real_email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "student_id": re.compile(r"\b20\d{8}\b"),
    "korean_name_role": re.compile(r"[가-힣]{2,4}\s*(교수|학생|선생|박사)"),
    "school_terms": re.compile(r"(부산보건대|부산보건대학교|RISE)"),
}


# ---------------------------------------------------------------------------
# PASS case — example YAML placeholder files contain 0 PII hits.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path",
    [
        "modules/immersio/docs/email_profile_example.yaml",
        "modules/immersio/docs/test_profile_example.yaml",
    ],
)
def test_example_yaml_pass_no_pii(rel_path: str) -> None:
    """PASS: docs/*example*.yaml carry 0 real-PII matches (placeholders only)."""
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    hits: list[tuple[str, str]] = []
    for name, pat in _PII_PATTERNS.items():
        for m in pat.finditer(text):
            literal = m.group(0)
            # Placeholder convention: <...> wrapped → not a real value
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = text[line_start:line_end if line_end != -1 else None]
            if "<" in line and ">" in line:
                continue
            if line.lstrip().startswith("#"):
                continue
            hits.append((name, literal))
    assert not hits, (
        f"SC-011 PASS-case violation: {rel_path} contains real-shape PII:\n"
        + "\n".join(f"  [{n}] {lit!r}" for n, lit in hits)
    )


# ---------------------------------------------------------------------------
# FAIL case — intentional-violation fixture must trigger every PII pattern.
# ---------------------------------------------------------------------------

_INTENTIONAL_PII_VIOLATION = """\
# Intentional SC-011 violations — meta-test fixture for Reflag #1.
# DO NOT IMPORT FROM PRODUCTION CODE.

real_student_email = "real-person@university.edu"
real_student_id = "2025194023"
real_professor_name = "정광석 교수"
institution = "부산보건대학교 RISE 사업단"
"""


def test_intentional_pii_fixture_caught_by_every_pattern() -> None:
    """FAIL-case fixture must trigger ALL 4 PII pattern categories.

    A pattern that fails to match here is a false-negative regression —
    the detector would silently let real PII through in production.
    """
    matched: set[str] = set()
    for name, pat in _PII_PATTERNS.items():
        if pat.search(_INTENTIONAL_PII_VIOLATION):
            matched.add(name)
    expected = set(_PII_PATTERNS.keys())
    missing = expected - matched
    assert not missing, (
        f"Reflag #1 meta-test failure: PII regex {missing!r} did not match "
        f"the intentional-violation fixture — false-negative regression."
    )


def test_no_pii_violation_fixture_committed_to_repo() -> None:
    """No real-PII fixture file (``_pii_violation.py.bad``) sits in the tree.

    The bad-fixture content is inlined into this test (above). If a
    file with that suffix is committed accidentally, the static scan
    would misclassify it as production code. This guard makes the
    convention explicit.
    """
    bad_paths = list(_REPO_ROOT.rglob("_pii_violation.py.bad"))
    assert not bad_paths, (
        f"Reflag #1: do not commit _pii_violation.py.bad — "
        f"inline the fixture in tests instead. Found: {bad_paths!r}"
    )
