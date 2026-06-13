"""T030 — Deterministic difficulty assignment (R7, N1).

``assign_difficulty(item) -> QuizItemCandidate``

quiz_gen (T027) freezes a PROVISIONAL ``difficulty="중"``.  This stage replaces
it with a final ``상``/``중``/``하`` tag derived from rule-based signals (no LLM
— Principle I; identical input ⇒ identical tag).  The new value is applied via
``model_copy`` (the model is frozen).

Rule (R7)
---------
- 긍정형 명칭매칭 → ``하``: a positive-polarity stem asking which statement is
  correct is, in practice, name-recall — the lowest cognitive load.
- 부정형 단일개념, 낮은 오답 동질성 → ``중``: a negative stem whose distractors
  span distinct concepts requires recognising one wrong statement among
  heterogeneous options.
- 부정형 통합·고동질 오답 (options lexically near) → ``상``: a negative stem whose
  distractors share most vocabulary forces fine-grained integrative
  discrimination — the highest load.

``question_type`` is NOT set here (it is LLM-emitted + enum-validated in T027).
"""

from __future__ import annotations

import re
from itertools import combinations

from paideia_shared.schemas import QuizItemCandidate

# Strips the leading circled-digit option marker before tokenising.
_OPTION_MARKER = re.compile(r"[①②③④⑤]")

# Option-homogeneity threshold (mean pairwise token Jaccard over the 5 options).
# Empirically separates heterogeneous distractors (~0.0) from integrative,
# vocabulary-sharing distractors (~0.4); see tests/unit/test_difficulty.py.
_HIGH_HOMOGENEITY = 0.3


def _option_tokens(option: str) -> set[str]:
    """Return the whitespace token set of an option, sans its number marker.

    Args:
        option: One option string (e.g. ``"① 허파꽈리는 ..."``).

    Returns:
        Set of non-empty whitespace-delimited tokens.
    """
    body = _OPTION_MARKER.sub("", option)
    return {tok for tok in body.split() if tok}


def _option_homogeneity(options: list[str]) -> float:
    """Mean pairwise token-Jaccard similarity across the options.

    Higher values mean the distractors share more vocabulary (an integrative,
    high-homogeneity item).

    Args:
        options: The option strings.

    Returns:
        Mean pairwise Jaccard in ``[0.0, 1.0]``; ``0.0`` when fewer than two
        options are present.
    """
    token_sets = [_option_tokens(opt) for opt in options]
    sims: list[float] = []
    for a, b in combinations(token_sets, 2):
        union = a | b
        sims.append(len(a & b) / len(union) if union else 0.0)
    if not sims:
        return 0.0
    return sum(sims) / len(sims)


def assign_difficulty(item: QuizItemCandidate) -> QuizItemCandidate:
    """Finalize ``item.difficulty`` deterministically, replacing provisional "중".

    Args:
        item: The quiz candidate carrying provisional ``difficulty="중"``.

    Returns:
        A NEW ``QuizItemCandidate`` with the rule-derived ``difficulty``.
    """
    if item.stem_polarity == "긍정형":
        difficulty = "하"
    elif _option_homogeneity(list(item.options)) >= _HIGH_HOMOGENEITY:
        difficulty = "상"
    else:
        difficulty = "중"

    return item.model_copy(update={"difficulty": difficulty})


__all__ = ["assign_difficulty"]
