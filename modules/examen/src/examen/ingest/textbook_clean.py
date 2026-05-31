"""T021 — Deterministic textbook rule cleaner.

Strips noise introduced by PDF extraction from raw textbook .txt files and
returns a list of kept (original_lineno, text) pairs plus a removed_spans
audit log.  All decisions are rule-based; no LLM is involved.

Noise categories handled
------------------------
1. Spaced-letter headers  — lines where every visible "word" is a single
   uppercase character separated by spaces, e.g. "C H A P T E R  10" or
   "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y".
2. Running chapter headers — lines that match the pattern "제NNN장 …" which
   repeat at the top of each printed page.
3. Standalone page numbers — a line containing only digits (optionally
   surrounded by whitespace).
4. Figure captions        — lines starting "그림 NN-N" (Korean figure label).
5. Table captions         — lines starting "표 NN-N" (Korean table label).
6. 연습문제 block           — from a line equal to "연습문제" (or a variant) to
   the end of the file (chapter-level exercises always appear at the tail).
7. 참고문헌 section          — from a line starting "참고문헌" to end of file.
8. Footnote marker lines  — lines starting with †, *, ※ followed by text
   (i.e. footnote body lines, NOT body text that happens to reference a note).

Body text and numbered section headings are explicitly KEPT.

Uncertain spans are logged with reason "review" rather than silently dropped.

Usage::

    from examen.ingest.textbook_clean import clean_textbook

    kept, removed_spans = clean_textbook(lines)
    # kept: list[tuple[int, str]]  — (1-based original lineno, text)
    # removed_spans: list[str]     — human-readable audit log entries
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Compiled regex patterns (compiled once at module load for determinism)
# ---------------------------------------------------------------------------

# 단독 페이지 번호 패턴은 regex로; 자간헤더는 토큰 기반 함수로 판별
# (이중 공백으로 구분된 패턴이 단순 regex로는 안정적으로 처리되지 않음)

# 단독 페이지 번호: 줄 전체가 숫자만
_RE_PAGE_NUMBER: Final = re.compile(r"^\s*\d+\s*$")

# 그림 캡션: "그림 " 으로 시작 (뒤에 번호·텍스트)
_RE_FIGURE_CAPTION: Final = re.compile(r"^그림\s+\d+")

# 표 캡션: "표 " 으로 시작
_RE_TABLE_CAPTION: Final = re.compile(r"^표\s+\d+")

# 달리는 챕터 헤더: "제NNN장" 패턴 (단독 줄 — 본문에서 이렇게 단독으로 나오는 경우)
_RE_RUNNING_HEADER: Final = re.compile(r"^제\d+장\s")

# 연습문제 블록 시작 — 헤딩 변형 허용:
#   "연습문제", "연습 문제", "연습문제:", "연습문제 (10문항)", "■ 연습문제", "[연습문제]"
# 본문 문장("연습문제는 중요하다.")과 구분하기 위해, "연습 문제" 토큰 뒤에는
# 임의의 한글 텍스트가 아니라 헤딩성 꼬리(구두점·괄호 안 문항수·번호)만 허용한다.
_RE_EXERCISE_START: Final = re.compile(
    r"^[\s■□▶◆●○\[\(]*"          # 선두 장식 기호·여는 괄호
    r"연습\s*문제"                  # "연습문제" 또는 "연습 문제"
    r"\s*[:\-–—\]\)]*"             # 콜론·대시·닫는 괄호
    r"\s*(?:\([0-9가-힣\s]+\))?"   # 선택적 "(10문항)" 같은 꼬리
    r"\s*$"
)

# 참고문헌 섹션 시작
_RE_REFERENCE_START: Final = re.compile(r"^참고문헌")

# 각주 마커 줄: †, *, ※ 로 시작하는 줄
_RE_FOOTNOTE_LINE: Final = re.compile(r"^[†*※]")

# 허용되는 자간헤더 토큰 (단일 대문자·숫자·기호)
_SPACED_HEADER_ALLOWED_TOKENS: frozenset[str] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789&%"
)


def _is_spaced_letter_header(stripped: str) -> bool:
    """Return True if *stripped* looks like a spaced-letter header.

    A spaced-letter header is a line where every whitespace-delimited token
    is **at most two characters** drawn from uppercase letters, digits, or the
    symbols ``&`` / ``%``, AND there are at least 3 such tokens (to avoid
    false-positives on short section labels).  The ≤2-char allowance lets a
    trailing chapter number ride along, e.g. the ``10`` in "C H A P T E R  10".

    Examples::
        "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y"  → True
        "C H A P T E R  10"                                   → True (10 is a 2-char token)
        "A"                                                    → False (too short)
        "갑상샘"                                                → False
    """
    tokens = stripped.split()
    if len(tokens) < 3:  # 최소 3 토큰 이상이어야 자간헤더로 간주
        return False
    return all(
        len(t) <= 2 and all(ch in _SPACED_HEADER_ALLOWED_TOKENS for ch in t)
        for t in tokens
    )


def clean_textbook(
    lines: list[str],
) -> tuple[list[tuple[int, str]], list[str]]:
    """Remove textbook noise from a list of raw lines.

    The function is *stateless and deterministic*: identical input always
    produces identical output.  It never raises on valid input; malformed or
    ambiguous lines that match no rule are silently kept (except uncertain
    spans which are flagged as "review").

    Args:
        lines: Raw lines from a PDF-extracted textbook .txt file.  The list
            is 0-indexed internally but returned line numbers are 1-based to
            match the original file's line numbering.

    Returns:
        A 2-tuple of:
        - kept: ``list[tuple[int, str]]`` — ``(1-based_lineno, text)`` for
          every line that survived cleaning.
        - removed_spans: ``list[str]`` — human-readable audit log of every
          removed region, one entry per distinct noise span.  Format:
          ``"[reason] line <N>: <text>"`` for single lines, or
          ``"[reason] lines <start>–<end>"`` for multi-line blocks.
    """
    if not lines:
        return [], []

    kept: list[tuple[int, str]] = []
    removed_spans: list[str] = []

    # 1-based line numbers for readability in audit log
    n = len(lines)

    # Pass 1: identify terminal block starts (연습문제 / 참고문헌)
    # The first occurrence of such a marker causes everything from that line
    # onwards to be removed (chapter-level blocks always end the file).
    terminal_start: int | None = None  # 1-based
    terminal_reason: str | None = None

    for i, line in enumerate(lines):
        lineno = i + 1
        stripped = line.strip()
        if _RE_EXERCISE_START.match(stripped):
            terminal_start = lineno
            terminal_reason = "연습문제"
            break
        if _RE_REFERENCE_START.match(stripped):
            terminal_start = lineno
            terminal_reason = "참고문헌"
            break

    # Log the terminal block as a single removed span
    if terminal_start is not None:
        end_lineno = n
        removed_spans.append(
            f"[{terminal_reason}/exercise_block] "
            f"lines {terminal_start}–{end_lineno}: "
            f"'{lines[terminal_start - 1].strip()}' … "
            f"({end_lineno - terminal_start + 1} lines)"
        )

    # Pass 2: line-by-line classification
    for i, line in enumerate(lines):
        lineno = i + 1
        stripped = line.strip()

        # Skip terminal block lines
        if terminal_start is not None and lineno >= terminal_start:
            continue

        # Blank lines — keep (preserve structure)
        if stripped == "":
            kept.append((lineno, line))
            continue

        # Rule 1: spaced-letter header
        if _is_spaced_letter_header(stripped):
            removed_spans.append(
                f"[spaced_header] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 2: running chapter header (제N장 …)
        if _RE_RUNNING_HEADER.match(stripped):
            removed_spans.append(
                f"[running_header] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 3: standalone page number
        if _RE_PAGE_NUMBER.match(stripped):
            removed_spans.append(
                f"[page_number] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 4: figure caption
        if _RE_FIGURE_CAPTION.match(stripped):
            removed_spans.append(
                f"[figure_caption/그림] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 5: table caption
        if _RE_TABLE_CAPTION.match(stripped):
            removed_spans.append(
                f"[table_caption/표] line {lineno}: '{stripped}'"
            )
            continue

        # Rule 6: footnote marker line
        if _RE_FOOTNOTE_LINE.match(stripped):
            removed_spans.append(
                f"[footnote/각주] line {lineno}: '{stripped}'"
            )
            continue

        # No rule matched — keep the line
        kept.append((lineno, line))

    return kept, removed_spans


__all__ = ["clean_textbook"]
