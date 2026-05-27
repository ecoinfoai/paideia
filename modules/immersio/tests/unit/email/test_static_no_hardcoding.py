"""Static hardcoding-detection contract test (T029 — ADR-009).

Greps the immersio-email source tree + tests + shared schemas + the
secrets/ tree for 11 forbidden patterns: real emails, student IDs,
Korean person names, institution names, App Passwords, generic API
tokens, RSA private keys, JSON ``private_key`` values, ``private_key_
id`` hex40, GCP service-account domain, and LLM SDK imports
(anthropic/openai/instructor — FR-B01 reinforcement).

False-positive whitelist (ADR-009 §"허용 예외 3종"):
1. ``cohort_filter.py`` — the constant ``SCORE_THRESHOLD_PCT_100 = 60``
   (FR-H03 explicit operator policy).
2. ``cohort_filter.py`` — the cohort-label Korean translation dict
   (operational labels, not student PII).
3. ``composer.py`` — ``EMAIL_BODY_TEMPLATE_KO`` (FR-G06 — variable
   placeholders only, no student/professor identifiers).

Meta-test: an intentional-violation fixture is also scanned so a
false-negative regression in the regex set is caught.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pytest

# ---------------------------------------------------------------------------
# Repository root resolution (this file lives at
# modules/immersio/tests/unit/email/test_static_no_hardcoding.py — 5 levels
# below repo root).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[5]


# ---------------------------------------------------------------------------
# 12 regex patterns (ADR-009 + secrets_contract.md + Reflag #3).
# ---------------------------------------------------------------------------
_PATTERNS: dict[str, re.Pattern[str]] = {
    "real_email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "student_id": re.compile(r"\b20\d{8}\b"),
    "korean_name_role": re.compile(r"[가-힣]{2,4}\s*(교수|학생|선생|박사)"),
    "school_terms": re.compile(r"(부산보건대|부산보건대학교|RISE)"),
    "app_password": re.compile(r"\b[a-z]{4}\s+[a-z]{4}\s+[a-z]{4}\s+[a-z]{4}\b"),
    "api_token": re.compile(r"(AKIA|sk-|xoxb-|ghp_)[A-Za-z0-9_-]{8,}"),
    "rsa_private_key": re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----"),
    "json_private_key": re.compile(r'"private_key"\s*:\s*"[^"]+"'),
    "json_private_key_id": re.compile(r'"private_key_id"\s*:\s*"[a-f0-9]{40}"'),
    "sa_domain": re.compile(r"\.iam\.gserviceaccount\.com"),
    "llm_sdk_import": re.compile(
        r"^\s*(import|from)\s+(anthropic|openai|instructor)\b", re.MULTILINE
    ),
    # Reflag #3: bare ``yaml.load`` (without an explicit safe Loader) is
    # unsafe — it can deserialize arbitrary Python objects (RCE risk).
    # Allowed: ``yaml.safe_load``, ``yaml.safe_load_all``, ``yaml.SafeLoader``.
    "unsafe_yaml_load": re.compile(r"\byaml\.load(?!_?safe|_all|er)\b"),
}


# ---------------------------------------------------------------------------
# Search scope (ADR-009).
# ---------------------------------------------------------------------------
_SCAN_DIRS: tuple[Path, ...] = (
    _REPO_ROOT / "modules" / "immersio" / "src" / "immersio" / "email",
    _REPO_ROOT / "modules" / "immersio" / "tests" / "unit" / "email",
    _REPO_ROOT / "modules" / "immersio" / "tests" / "contract" / "email",
    _REPO_ROOT / "modules" / "immersio" / "tests" / "integration" / "email",
    _REPO_ROOT / "shared" / "paideia_shared" / "src" / "paideia_shared" / "schemas",
)
_SCAN_GLOBS: tuple[str, ...] = ("**/*.py",)
_SECRETS_DIR = _REPO_ROOT / "secrets"


# ---------------------------------------------------------------------------
# False-positive whitelist (ADR-009 §"허용 예외 3종").
# ---------------------------------------------------------------------------
_ALLOWED_LITERALS: frozenset[str] = frozenset({
    # 3-2: cohort-label Korean translation dict (operational labels)
    "저득점",
    "나머지",
    "전체",
    # 3-3: example-domain placeholders that show up in test fixtures /
    # docstrings (NOT real personal addresses) — RFC 2606 reserves
    # example.com / example.ac.kr / example.org for documentation use.
    "student@example.com",
    "alpha@example.ac.kr",
    "noreply@example.ac.kr",
    "kjeong@example.ac.kr",
    "ok@example.com",
    "pool1@example.com",
    "pool2@example.com",
    "abc@example.com",
    "deterministic@example.ac.kr",
    "mixed.case@example.com",
    "first@example.com",
    "second@example.com",
    "alice@example.com",
    "bob@example.com",
    "operator@example.ac.kr",
    "hong@example.com",
    "kim@example.com",
    "lee@example.com",
    "yoo@example.com",
    "ahn@example.com",
    "a@example.com",
    "b@example.com",
    # Deterministic Message-ID literal asserted in tests — same domain
    # (example.ac.kr) prefixed with the synthetic message-id form
    "1234567890.2026-05-01.anatomy.2026-1@example.ac.kr",
    "x@example.ac.kr",  # synthetic short message-id literal in csv schema test
    "Alice@Example.COM",  # case-variant for lowercase normalization test
    # ADR-009 allowed exception #3 — operational labels in body template
    # and report headings, not student/professor PII.
    "필요한 학생",
    "다른 학생",
    "실패 학생",
    "누락 학생",
    "해당 학생",  # cohort 명단 md placeholder for empty partition
    "더미 학생",  # dummy_fixture body operational marker
    "테스트학생",  # test fixture name placeholder (no role suffix)
    "상태인 학생",  # v0.1.1 retry-mode notice phrase (FR-G; operational status descriptor)
    "에서 학생",  # docstring connective fragment ("…줄에서 학생 이름…")
    "라인은 학생",  # assertion-context connective ("표본 라인은 학생 이름·이메일…")
    "라인에 학생",  # assertion-context connective ("표본 외 라인에 학생 이름 노출…")
    "선이므로 학생",  # T035 docstring connective ("dry-run 이 우선이므로 학생/본인…")
    "저득점 학생",  # T035 docstring cohort descriptor ("저득점 학생만 대상")
    # Mock service-account placeholders (non-routable, fake-prefixed)
    "fake-sa@fake-project.iam.gserviceaccount.com",
    "x@y.com",
    # Korean placeholder names used in test fixtures — operational
    # placeholders (NOT real student/professor identifiers)
    "알파교수",
    "더미학생1",
    "더미학생2",
    "더미일",
    "더미이",
    "홍길동",
    "김갑동",
    "이순신",
    "유관순",
    "안중근",
    "유령",
    "다른이름",
    "가짜이름",
})

# Files whose contents are domain-specific allowed (whole-file exemption).
_ALLOWED_FILE_NAMES: frozenset[str] = frozenset({
    # The static-search test itself contains every regex pattern — would
    # match itself recursively without exemption.
    "test_static_no_hardcoding.py",
    # Reflag #1 PII bidirectional contract test — the FAIL-case fixture
    # must contain real-shape PII so the meta-test can verify regex
    # match. Whole-file exemption mirrors the static-search test pattern.
    "test_pii_static_scan.py",
})


def _iter_python_files() -> Iterable[Path]:
    """Yield every .py file inside the scan scope."""
    seen: set[Path] = set()
    for root in _SCAN_DIRS:
        if not root.exists():
            continue
        for glob in _SCAN_GLOBS:
            for path in root.glob(glob):
                if not path.is_file():
                    continue
                if path.name in _ALLOWED_FILE_NAMES:
                    continue
                # Skip our own (paideia_shared) schemas that pre-date spec
                # 006 — only audit files matching email_* and the brand-
                # new spec-006 modules.
                if root.name == "schemas" and not path.name.startswith(
                    ("email_", "professor_profile", "test_profile", "student_pdf_bundle")
                ):
                    continue
                if path in seen:
                    continue
                seen.add(path)
                yield path


def _iter_secrets_files() -> Iterable[Path]:
    """Yield every secrets/*.json (plaintext) — should be 0 in a clean repo."""
    if not _SECRETS_DIR.exists():
        return
    yield from (p for p in _SECRETS_DIR.glob("*.json") if p.is_file())


def _scan_file(path: Path) -> list[tuple[str, str, int]]:
    """Return ``[(pattern_name, match, line_no), ...]`` after whitelist."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    hits: list[tuple[str, str, int]] = []
    for name, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            literal = m.group(0)
            if literal in _ALLOWED_LITERALS:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            line = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
            stripped = line.strip()
            # Allow placeholders / inline-allow comments
            if "<" in literal and ">" in literal:
                continue
            if "ALLOW_HARDCODING" in line:
                continue
            hits.append((name, literal, line_no))
    return hits


def test_no_hardcoded_secrets_or_pii() -> None:
    """No real email / student-id / SA secret / LLM SDK import in scope."""
    failures: list[tuple[Path, str, str, int]] = []
    for path in _iter_python_files():
        for name, literal, line_no in _scan_file(path):
            failures.append((path, name, literal, line_no))
    for path in _iter_secrets_files():
        for name, literal, line_no in _scan_file(path):
            failures.append((path, name, literal, line_no))
    if failures:
        pretty = "\n".join(
            f"  {path.relative_to(_REPO_ROOT)}:{line} [{name}] {literal!r}"
            for path, name, literal, line in failures
        )
        pytest.fail(
            f"ADR-009: hardcoded secret / PII / forbidden import detected "
            f"({len(failures)} hit(s)):\n{pretty}"
        )


# ---------------------------------------------------------------------------
# Meta-test: intentional-violation fixture must be detected by every
# pattern category (so a regex regression that lets real values through
# also fails this test).
# ---------------------------------------------------------------------------

_INTENTIONAL_VIOLATION_FIXTURE = """\
# Intentional ADR-009 violations — meta-test fixture.
# DO NOT IMPORT FROM PRODUCTION CODE.

real_email_violation = "real-person@university.edu"
student_id_violation = "2026194023"
korean_name_violation = "홍길동 교수"
school_violation = "부산보건대학교"
app_password_violation = "abcd efgh ijkl mnop"
api_token_violation = "sk-AbCdEfGhIjKlMnOpQrStUvWxYz"
rsa_violation = "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----"
json_pk_violation = '"private_key": "fake-bytes"'
json_pk_id_violation = '"private_key_id": "0123456789abcdef0123456789abcdef01234567"'
sa_domain_violation = "fake-sa@project.iam.gserviceaccount.com"
import anthropic  # noqa
from openai import OpenAI  # noqa
unsafe_yaml = yaml.load(stream)  # bare load — RCE risk
"""


def test_meta_intentional_violation_fixture_caught(tmp_path: Path) -> None:
    """Each of the 11 patterns must catch its corresponding violation."""
    fixture_path = tmp_path / "_hardcoded_email_violation.py.bad"
    fixture_path.write_text(_INTENTIONAL_VIOLATION_FIXTURE, encoding="utf-8")

    text = fixture_path.read_text(encoding="utf-8")
    matched_patterns: set[str] = set()
    for name, pat in _PATTERNS.items():
        if pat.search(text):
            matched_patterns.add(name)

    expected = set(_PATTERNS.keys())
    missing = expected - matched_patterns
    assert not missing, (
        f"ADR-009 meta-test: regex pattern(s) {missing!r} failed to match "
        f"the intentional-violation fixture — false-negative risk."
    )
