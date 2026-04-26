"""Property tests: idempotency / round-trip / determinism."""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from immersio.normalize import (
    LIKERT_TEXT_TO_INT,
    expand_multiselect,
    normalize_likert,
    normalize_student_id,
)


@given(
    digits=st.text(alphabet=st.sampled_from("0123456789"), min_size=10, max_size=10),
    pad_chars=st.text(alphabet=st.sampled_from(" \t'\"-"), min_size=0, max_size=4),
)
@settings(max_examples=80, deadline=500)
def test_normalize_student_id_idempotent(digits: str, pad_chars: str) -> None:
    raw = pad_chars + digits + pad_chars
    once = normalize_student_id(raw)
    twice = normalize_student_id(once)
    assert once == twice == digits


@given(text=st.sampled_from(list(LIKERT_TEXT_TO_INT.keys())))
@settings(max_examples=20, deadline=500)
def test_normalize_likert_round_trip(text: str) -> None:
    expected = LIKERT_TEXT_TO_INT[text]
    assert normalize_likert(text) == expected


@given(
    options=st.lists(
        st.text(min_size=1, max_size=10).filter(lambda s: ";" not in s),
        min_size=0,
        max_size=8,
    )
)
@settings(max_examples=80, deadline=500)
def test_expand_multiselect_round_trip(options: list[str]) -> None:
    stripped = [opt.strip() for opt in options if opt.strip()]
    assume(stripped == options or all(opt == opt.strip() for opt in options))
    raw = ";".join(options)
    parsed = expand_multiselect(raw)
    # parsed must be a strict subset of stripped order, dropping empty entries
    assert parsed == [opt for opt in options if opt.strip()]
