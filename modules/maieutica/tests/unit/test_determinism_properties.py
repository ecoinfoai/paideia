"""T056 — Property tests: determinism invariants (US6, hypothesis).

Tests three invariants that must hold for any valid QuizItemCandidate:

(a) ``option_length_ok`` is True iff every option is 30–50 codepoints
    (including spaces).

(b) ``explanation_length_ok`` is True iff both ``wrong_explanation`` and
    ``leap.text`` are each ≤200 codepoints (including spaces).

(c) Fold round-trip: ``answer_explanation_combined.split(" ─ 도약 ─ ", 1)``
    recovers ``(wrong_explanation, leap.text)`` for any valid candidate.

Uses hypothesis strategies only; no external state, no LLM, no filesystem I/O.
All runs are deterministic (``@settings(deriving_settings=False)`` not needed —
hypothesis defaults are deterministic for the same seed).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from maieutica.verify.format_checks import (
    _EXPLANATION_MAX_LEN,
    _OPTION_MAX_LEN,
    _OPTION_MIN_LEN,
    _compute_explanation_length_ok,
    _compute_option_length_ok,
)

# ---------------------------------------------------------------------------
# Shared text strategy helpers
# ---------------------------------------------------------------------------

# Korean + ASCII printable mix — representative of real option content.
_PRINTABLE = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters=" 가나다라마바사아자차카타파하폐포기관지",
    ),
    min_size=0,
    max_size=120,
)


@st.composite
def _option_text(draw: st.DrawFn, min_len: int, max_len: int) -> str:
    """Draw a text string with codepoint length in [min_len, max_len]."""
    length = draw(st.integers(min_value=min_len, max_value=max_len))
    base = draw(
        st.text(
            alphabet="가나다라마바사아자차카타파하폐포기관지 ABCDEFGabcdefg0123456789",
            min_size=length,
            max_size=length,
        )
    )
    return base


# ---------------------------------------------------------------------------
# (a) option_length_ok invariant
# ---------------------------------------------------------------------------


@given(
    options=st.lists(
        _option_text(min_len=_OPTION_MIN_LEN, max_len=_OPTION_MAX_LEN),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=200)
def test_option_length_ok_true_iff_all_in_window(options: list[str]) -> None:
    """option_length_ok is True when all options are in [30, 50] codepoints."""
    result = _compute_option_length_ok(options)
    # By construction every option is in range, so result must be True.
    assert result is True, (
        f"expected True for all-in-range options, got False. "
        f"Lengths: {[len(o) for o in options]}"
    )


@given(
    in_range=st.lists(
        _option_text(min_len=_OPTION_MIN_LEN, max_len=_OPTION_MAX_LEN),
        min_size=1,
        max_size=4,
    ),
    out_of_range=_option_text(min_len=_OPTION_MAX_LEN + 1, max_len=80),
)
@settings(max_examples=200)
def test_option_length_ok_false_when_any_out_of_range(
    in_range: list[str], out_of_range: str
) -> None:
    """option_length_ok is False when at least one option exceeds the window."""
    options = in_range + [out_of_range]
    result = _compute_option_length_ok(options)
    assert result is False, (
        f"expected False for options with one too-long entry. "
        f"Lengths: {[len(o) for o in options]}"
    )


@given(
    in_range=st.lists(
        _option_text(min_len=_OPTION_MIN_LEN, max_len=_OPTION_MAX_LEN),
        min_size=1,
        max_size=4,
    ),
    too_short=_option_text(min_len=1, max_len=_OPTION_MIN_LEN - 1),
)
@settings(max_examples=200)
def test_option_length_ok_false_when_any_too_short(
    in_range: list[str], too_short: str
) -> None:
    """option_length_ok is False when at least one option is under 30 codepoints."""
    options = in_range + [too_short]
    result = _compute_option_length_ok(options)
    assert result is False, (
        f"expected False for options with one too-short entry. "
        f"Lengths: {[len(o) for o in options]}"
    )


def test_option_length_ok_false_for_empty_list() -> None:
    """option_length_ok is False for an empty option list."""
    assert _compute_option_length_ok([]) is False


# ---------------------------------------------------------------------------
# (b) explanation_length_ok invariant
# ---------------------------------------------------------------------------


@given(
    wrong=st.text(min_size=0, max_size=_EXPLANATION_MAX_LEN),
    leap=st.text(min_size=0, max_size=_EXPLANATION_MAX_LEN),
)
@settings(max_examples=300)
def test_explanation_length_ok_true_iff_both_within_limit(
    wrong: str, leap: str
) -> None:
    """explanation_length_ok is True when both texts are ≤200 codepoints."""
    result = _compute_explanation_length_ok(wrong, leap)
    assert result is True, (
        f"expected True for both ≤200 chars. "
        f"wrong={len(wrong)}, leap={len(leap)}"
    )


@given(
    wrong_ok=st.text(min_size=0, max_size=_EXPLANATION_MAX_LEN),
    leap_over=st.text(min_size=_EXPLANATION_MAX_LEN + 1, max_size=400),
)
@settings(max_examples=200)
def test_explanation_length_ok_false_when_leap_over_limit(
    wrong_ok: str, leap_over: str
) -> None:
    """explanation_length_ok is False when leap.text exceeds 200 codepoints."""
    result = _compute_explanation_length_ok(wrong_ok, leap_over)
    assert result is False, (
        f"expected False (leap over limit). "
        f"wrong={len(wrong_ok)}, leap={len(leap_over)}"
    )


@given(
    wrong_over=st.text(min_size=_EXPLANATION_MAX_LEN + 1, max_size=400),
    leap_ok=st.text(min_size=0, max_size=_EXPLANATION_MAX_LEN),
)
@settings(max_examples=200)
def test_explanation_length_ok_false_when_wrong_over_limit(
    wrong_over: str, leap_ok: str
) -> None:
    """explanation_length_ok is False when wrong_explanation exceeds 200 codepoints."""
    result = _compute_explanation_length_ok(wrong_over, leap_ok)
    assert result is False, (
        f"expected False (wrong over limit). "
        f"wrong={len(wrong_over)}, leap={len(leap_ok)}"
    )


# ---------------------------------------------------------------------------
# (c) Fold round-trip invariant
# ---------------------------------------------------------------------------

# The canonical separator from QuizItemCandidate V4 (also used in leap_fold.py).
_SEPARATOR = " ─ 도약 ─ "


@given(
    wrong=st.text(
        # Exclude the separator itself so split(maxsplit=1) unambiguously
        # recovers the two parts (no embedded separator in wrong_explanation).
        alphabet=st.characters(blacklist_characters="─"),
        min_size=0,
        max_size=200,
    ),
    leap_text=st.text(
        min_size=0,
        max_size=200,
    ),
)
@settings(max_examples=500)
def test_fold_round_trip(wrong: str, leap_text: str) -> None:
    """answer_explanation_combined.split(sep, 1) recovers (wrong_explanation, leap.text).

    For any pair of strings where ``wrong`` does not contain the separator,
    the fold ``f"{wrong} ─ 도약 ─ {leap_text}"`` round-trips exactly:
    ``combined.split(" ─ 도약 ─ ", 1)`` → ``[wrong, leap_text]``.

    This matches QuizItemCandidate V4 which enforces:
        answer_explanation_combined == f"{wrong_explanation} ─ 도약 ─ {leap.text}"
    """
    combined = f"{wrong}{_SEPARATOR}{leap_text}"
    parts = combined.split(_SEPARATOR, 1)
    assert len(parts) == 2, (
        f"split produced {len(parts)} parts, expected 2. combined={combined!r}"
    )
    recovered_wrong, recovered_leap = parts
    assert recovered_wrong == wrong, (
        f"round-trip: wrong_explanation mismatch.\n"
        f"  original:  {wrong!r}\n"
        f"  recovered: {recovered_wrong!r}"
    )
    assert recovered_leap == leap_text, (
        f"round-trip: leap.text mismatch.\n"
        f"  original:  {leap_text!r}\n"
        f"  recovered: {recovered_leap!r}"
    )
