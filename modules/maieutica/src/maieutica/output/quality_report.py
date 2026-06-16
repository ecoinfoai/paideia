"""T049 — Quality report: build 출제품질리포트.md (maieutica).

Provides:
- ``build_quality_report(quiz_items, formative_items)`` — render the
  human-readable ``출제품질리포트.md`` Markdown string.
- ``write_quality_report(path, text)`` — write atomically to Gold dir.

Report sections (출제품질리포트.md):
1. 헤더: 출제품질리포트
2. 총 문항 수: quiz_count / formative_count
3. 정답 번호 분포: answer_no distribution (1..5)
4. 줄기 극성 분포: stem_polarity breakdown
5. 난이도 분포: difficulty breakdown
6. 교재 근거 확인: groundedness 확인/미확인 counts
7. 형성평가 요약: formative item count + groundedness
8. 주의 항목: option_length_violations, explanation_length_violations,
   duplicate counts

Design
------
- Pure function: ``build_quality_report`` takes item lists and returns a
  Markdown string.  No filesystem I/O.
- Deterministic: same inputs → same output (no timestamps in the body).
- ``write_quality_report`` wraps ``atomic_write`` for constitution V compliance.
- Mirrors ``modules/examen/src/examen/output/quality_report.py`` in structure.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from paideia_shared.schemas import FormativeItemCandidate, QuizItemCandidate

from maieutica.output.paths import atomic_write


@dataclass(frozen=True)
class QuizShortfall:
    """Adopted-vs-requested quiz accounting for the shortfall report sections.

    Bridges the pipeline (producer) and the quality report (consumer).  The
    pipeline guarantees the decomposition invariant::

        capacity_short + dedup_removed + unconfirmed_excluded == requested - produced

    so the three causes always sum to the shortfall ``N − M`` (헌장 V / FR-015,
    no silent omission).

    Attributes:
        requested: ``N`` — the requested quiz count (``spec.quiz_count``).
        produced: ``M`` — the adopted item count after exclusions.
        capacity_short: Slots dropped for lack of subsection capacity
            (``N − capacity``).
        dedup_removed: Anchor-duplicate removals (D2/D3).
        unconfirmed_excluded: 미확인-anchor exclusions (G3).
        available_subsections: Number of subsections actually available
            (``len(chunks)``).  Used for the capacity-short cause LABEL so it
            reads the true subsection count even when ``produced == 0`` leaves
            ``subsection_counts`` empty (the adopted grouping must not drive the
            available-capacity arithmetic).
        subsection_counts: Subsection label → ADOPTED item count, ordered
            deterministically.  Each count is ≤3 (the per-subsection cap).  May be
            empty when ``produced == 0``.
        single_subsection: ``True`` when chunking found a single whole-chapter
            chunk with ``section is None`` (C4 fallback → "소절 미검출").
    """

    requested: int
    produced: int
    capacity_short: int
    dedup_removed: int
    unconfirmed_excluded: int
    available_subsections: int
    subsection_counts: dict[str, int] = field(default_factory=dict)
    single_subsection: bool = False


def build_quality_report(
    quiz_items: list[QuizItemCandidate],
    formative_items: list[FormativeItemCandidate],
    *,
    shortfall: QuizShortfall | None = None,
) -> str:
    """Render the 출제품질리포트.md as a Markdown string.

    Sections:
    1. 헤더
    2. 총 문항 수
    3. 정답 번호 분포
    4. 줄기 극성 분포
    5. 난이도 분포
    6. 교재 근거 확인 (quiz items)
    7. 형성평가 요약
    8. 주의 항목

    When ``shortfall`` is provided, three ADDITIVE sections are appended after the
    existing ones (existing section order/format preserved — QR2 backward-compat):
    9. 요청 대비 산출 (Q1), 10. 소절 분산 (Q2), 11. 부족분 사유 (Q3, only when M<N).
    With ``shortfall is None`` the output is byte-identical to the pre-change
    function (existing callers / tests unaffected).

    Args:
        quiz_items: Quiz candidates to report on.
        formative_items: Formative candidates to report on.
        shortfall: Optional adopted-vs-requested accounting; when given, render the
            additive 요청 대비 산출 / 소절 분산 / 부족분 사유 sections.

    Returns:
        Markdown-formatted quality report string.
    """
    quiz_total = len(quiz_items)
    formative_total = len(formative_items)
    lines: list[str] = []

    # ----------------------------------------------------------------
    # 1. 헤더
    # ----------------------------------------------------------------
    lines.append("# 출제품질리포트")
    lines.append("")

    # ----------------------------------------------------------------
    # 2. 총 문항 수
    # ----------------------------------------------------------------
    lines.append("## 총 문항 수")
    lines.append("")
    lines.append("| 유형 | 문항 수 |")
    lines.append("|------|---------|")
    lines.append(f"| 퀴즈 (객관식) | {quiz_total} |")
    lines.append(f"| 형성평가 (서술형) | {formative_total} |")
    lines.append(f"| 합계 | {quiz_total + formative_total} |")
    lines.append("")

    # ----------------------------------------------------------------
    # 3. 정답 번호 분포 (quiz only)
    # ----------------------------------------------------------------
    lines.append("## 정답 번호 분포")
    lines.append("")
    if quiz_total == 0:
        lines.append("퀴즈 문항 없음.")
        lines.append("")
    else:
        ans_counts = Counter(i.answer_no for i in quiz_items)
        lines.append("| 정답번호 | 문항 수 | 비율 |")
        lines.append("|----------|---------|------|")
        for num in range(1, 6):
            cnt = ans_counts.get(num, 0)
            ratio = cnt / quiz_total if quiz_total > 0 else 0.0
            lines.append(f"| {num}번 | {cnt} | {ratio:.1%} |")
        lines.append("")
        # consecutive-run check
        max_run = _max_consecutive_run([i.answer_no for i in quiz_items])
        run_icon = "✅" if max_run <= 2 else "⚠️"
        lines.append(f"{run_icon} 최장 연속 동일 정답번호: **{max_run}** (목표 ≤2)")
        lines.append("")

    # ----------------------------------------------------------------
    # 4. 줄기 극성 분포
    # ----------------------------------------------------------------
    lines.append("## 줄기 극성 분포")
    lines.append("")
    if quiz_total == 0:
        lines.append("퀴즈 문항 없음.")
        lines.append("")
    else:
        polarity_counts = Counter(i.stem_polarity for i in quiz_items)
        lines.append("| 극성 | 문항 수 | 비율 |")
        lines.append("|------|---------|------|")
        for pol in sorted(polarity_counts):
            cnt = polarity_counts[pol]
            ratio = cnt / quiz_total
            lines.append(f"| {pol} | {cnt} | {ratio:.1%} |")
        lines.append("")

    # ----------------------------------------------------------------
    # 5. 난이도 분포
    # ----------------------------------------------------------------
    lines.append("## 난이도 분포")
    lines.append("")
    if quiz_total == 0:
        lines.append("퀴즈 문항 없음.")
        lines.append("")
    else:
        diff_counts = Counter(i.difficulty for i in quiz_items)
        lines.append("| 난이도 | 문항 수 | 비율 |")
        lines.append("|--------|---------|------|")
        for level in ("상", "중", "하"):
            cnt = diff_counts.get(level, 0)
            ratio = cnt / quiz_total
            lines.append(f"| {level} | {cnt} | {ratio:.1%} |")
        lines.append("")

    # ----------------------------------------------------------------
    # 6. 교재 근거 확인 (quiz)
    # ----------------------------------------------------------------
    lines.append("## 교재 근거 확인")
    lines.append("")
    if quiz_total == 0:
        lines.append("퀴즈 문항 없음.")
        lines.append("")
    else:
        confirmed = sum(
            1 for i in quiz_items if i.textbook_evidence and i.textbook_evidence.status == "확인"
        )
        unconfirmed = quiz_total - confirmed
        conf_ratio = confirmed / quiz_total
        unconf_icon = "✅" if unconfirmed == 0 else "⚠️"
        lines.append("| 상태 | 문항 수 | 비율 |")
        lines.append("|------|---------|------|")
        lines.append(f"| 확인 | {confirmed} | {conf_ratio:.1%} |")
        lines.append(f"| 미확인 | {unconfirmed} | {1 - conf_ratio:.1%} |")
        lines.append("")
        lines.append(f"{unconf_icon} 미확인 문항: {unconfirmed}건")
        lines.append("")

    # ----------------------------------------------------------------
    # 7. 형성평가 요약
    # ----------------------------------------------------------------
    lines.append("## 형성평가 요약")
    lines.append("")
    if formative_total == 0:
        lines.append("형성평가 문항 없음.")
        lines.append("")
    else:
        f_confirmed = sum(
            1
            for f in formative_items
            if f.textbook_evidence and f.textbook_evidence.status == "확인"
        )
        f_unconfirmed = formative_total - f_confirmed
        f_conf_ratio = f_confirmed / formative_total
        f_icon = "✅" if f_unconfirmed == 0 else "⚠️"
        lines.append(f"- 형성평가 문항 수: **{formative_total}**")
        lines.append(f"- 교재 근거 확인: {f_confirmed}건 ({f_conf_ratio:.1%})")
        lines.append(f"- 미확인: {f_unconfirmed}건")
        lines.append("")
        lines.append(f"{f_icon} 형성평가 미확인: {f_unconfirmed}건")
        lines.append("")

    # ----------------------------------------------------------------
    # 8. 주의 항목
    # ----------------------------------------------------------------
    lines.append("## 주의 항목")
    lines.append("")
    option_violations = sum(1 for i in quiz_items if not i.option_length_ok)
    explanation_violations = sum(1 for i in quiz_items if not i.explanation_length_ok)
    duplicate_count = sum(1 for i in quiz_items if i.duplicate_flag)

    lines.append("| 항목 | 건수 |")
    lines.append("|------|------|")
    lines.append(f"| 보기 길이 위반 (option_length_violations) | {option_violations} |")
    lines.append(f"| 설명 길이 위반 (explanation_length_violations) | {explanation_violations} |")
    lines.append(f"| 중복 문항 (duplicate_count) | {duplicate_count} |")
    lines.append("")

    # ----------------------------------------------------------------
    # 9–11. Shortfall / subsection-spread sections (additive — only when a
    # QuizShortfall is supplied; keeps no-shortfall output byte-identical).
    # ----------------------------------------------------------------
    if shortfall is not None:
        _append_shortfall_sections(lines, shortfall)

    return "\n".join(lines)


def _append_shortfall_sections(lines: list[str], shortfall: QuizShortfall) -> None:
    """Append the Q1/Q2/Q3 shortfall sections to ``lines`` in place.

    Q1 (요청 대비 산출): requested N / produced M, ⚠️ when M<N.
    Q2 (소절 분산): per-subsection adopted-count table (≤3 each); single-subsection
        fallback renders "소절 미검출(단일 소절)".
    Q3 (부족분 사유): only when M<N — the three causes whose displayed counts sum
        to ``N − M`` (헌장 V / FR-015, no silent omission); when M==N, "충족".

    Args:
        lines: The report line accumulator (mutated in place).
        shortfall: The adopted-vs-requested accounting to render.
    """
    n = shortfall.requested
    m = shortfall.produced
    deficit = n - m

    # Q1 — 요청 대비 산출
    lines.append("## 요청 대비 산출")
    lines.append("")
    lines.append("| 항목 | 값 |")
    lines.append("|------|-----|")
    lines.append(f"| 요청 퀴즈 수 (N) | {n} |")
    lines.append(f"| 산출 퀴즈 수 (M) | {m} |")
    lines.append("")
    if deficit > 0:
        lines.append(f"⚠️ 부족분 {deficit}건")
    else:
        lines.append("✅ 충족 (요청 = 산출)")
    lines.append("")

    # Q2 — 소절 분산
    lines.append("## 소절 분산")
    lines.append("")
    if shortfall.single_subsection:
        lines.append("소절 미검출(단일 소절)")
        lines.append("")
    else:
        lines.append("| 소절 | 문항 수 |")
        lines.append("|------|---------|")
        for label, count in shortfall.subsection_counts.items():
            lines.append(f"| {label} | {count} |")
        lines.append("")

    # Q3 — 부족분 사유 (only when short; causes sum to N − M)
    if deficit > 0:
        lines.append("## 부족분 사유")
        lines.append("")
        if shortfall.capacity_short > 0:
            # Label the AVAILABLE subsection count (len(chunks)), NOT the adopted
            # grouping — when produced==0 the adopted grouping is empty and would
            # render a nonsensical "소절 0개 × cap 3 = 3" line.
            available = shortfall.available_subsections
            capacity = available * 3
            lines.append(
                f"- 가용 소절 부족: 소절 {available}개 × cap 3 = {capacity} < {n} "
                f"→ {shortfall.capacity_short}건 미달"
            )
        if shortfall.dedup_removed > 0:
            lines.append(f"- 정답 앵커 중복 제거 {shortfall.dedup_removed}건")
        if shortfall.unconfirmed_excluded > 0:
            lines.append(f"- 정답 근거 앵커 미확인 제외 {shortfall.unconfirmed_excluded}건")
        lines.append("")


def _max_consecutive_run(values: list[int]) -> int:
    """Return the length of the longest consecutive run of equal values.

    Args:
        values: Sequence of integer values to scan.

    Returns:
        Length of the longest run of identical consecutive values.
        Returns ``0`` if ``values`` is empty, ``1`` if all values differ.
    """
    if not values:
        return 0
    max_run = 1
    current = 1
    for i in range(1, len(values)):
        if values[i] == values[i - 1]:
            current += 1
            if current > max_run:
                max_run = current
        else:
            current = 1
    return max_run


def write_quality_report(path: Path, text: str) -> None:
    """Write the quality report Markdown atomically to ``path``.

    Ensures the parent directory exists and writes atomically
    (constitution V: 부분 산출 금지).

    Args:
        path: Destination path (e.g. ``run_dir / "출제품질리포트.md"``).
        text: Markdown content to write (UTF-8).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(tmp: Path) -> None:
        content = text if text.endswith("\n") else text + "\n"
        tmp.write_text(content, encoding="utf-8")

    atomic_write(path, _write)


__all__ = ["QuizShortfall", "build_quality_report", "write_quality_report"]
