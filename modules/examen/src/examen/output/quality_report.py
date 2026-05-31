"""T051 — Quality report: build 출제품질리포트.md + targets_vs_actual dict.

Provides:
- ``build_targets_vs_actual(items, blueprint)`` — compute the structured
  targets-vs-actual metrics dict for the manifest.
- ``build_quality_report(items, blueprint)`` — render the human-readable
  ``출제품질리포트.md`` Markdown string.
- ``write_quality_report(path, text)`` — write atomically to Gold dir.

Report sections (출제품질리포트.md):
1. 헤더: exam_name, generation run
2. 챕터별 문항 수 (목표 vs 실측)
3. 난이도 분포 (목표 vs 실측) — ✅/⚠️ flagged
4. 출처 구성비 (목표 vs 실측)
5. 정답 번호 분포 (목표: 15–25% each, 연속 ≤ 2) — ✅/⚠️ flagged
6. 근거 확인 (groundedness) 요약

Design
------
- Pure function: ``build_quality_report`` takes items + blueprint and returns
  a Markdown string.  No filesystem I/O.
- ``build_targets_vs_actual`` returns a JSON-serialisable dict for the manifest.
- Deterministic: same inputs → same output (no timestamps, no random).
- ``write_quality_report`` wraps ``atomic_write`` for constitution V compliance.
- ✅ = within target range; ⚠️ = outside target range.

Korean comments OK; English docstrings/errors required.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from paideia_shared.schemas import ExamenBlueprint, ExamItemDraft

from examen.output.paths import atomic_write

# ---------------------------------------------------------------------------
# Target ranges
# ---------------------------------------------------------------------------

# 정답 번호 분포 허용 범위 (SC-007 / FR-013)
_ANSWER_NO_MIN_RATIO = 0.15
_ANSWER_NO_MAX_RATIO = 0.25

# 난이도 목표 편차 허용 범위 (SC-004: ±10%p)
_DIFFICULTY_TOLERANCE = 0.10


def build_targets_vs_actual(
    items: list[ExamItemDraft],
    blueprint: ExamenBlueprint,
) -> dict[str, Any]:
    """Compute structured targets-vs-actual metrics for the manifest.

    Returns a JSON-serialisable dict with the following keys:
    - ``"difficulty"``: target ratios vs actual ratios for easy/medium/hard.
    - ``"chapter_even_maxdiff"``: max - min chapter item counts.
    - ``"source_breakdown"``: target vs actual item counts per source.
    - ``"answer_no_balance"``: per-answer-number ratios + conformance flag.

    Args:
        items: The balanced, verified exam items.
        blueprint: The exam blueprint (declares targets).

    Returns:
        JSON-serialisable dict for ``ExamenManifest.targets_vs_actual``.
    """
    total = len(items)
    if total == 0:
        return {
            "difficulty": {"target": [0.45, 0.35, 0.20], "actual": [0.0, 0.0, 0.0]},
            "chapter_even_maxdiff": 0,
            "source_breakdown": {"target": {}, "actual": {}},
            "answer_no_balance": {"distribution": {}, "in_range": True, "max_run": 0},
        }

    # 난이도 실측
    easy_n = sum(1 for i in items if i.difficulty == "1_쉬움")
    med_n = sum(1 for i in items if i.difficulty == "2_보통")
    hard_n = sum(1 for i in items if i.difficulty == "3_어려움")

    # 챕터 균등 최대 차
    ch_counts = list(Counter(i.chapter for i in items).values())
    chapter_even_maxdiff = (max(ch_counts) - min(ch_counts)) if ch_counts else 0

    # 출처 실측 vs 목표
    src_actual = dict(Counter(i.source for i in items))
    src_target = dict(blueprint.source_mix)

    # 정답 번호 분포
    ans_counts = Counter(i.answer_no for i in items)
    ans_dist: dict[str, Any] = {}
    all_in_range = True
    for num in range(1, 6):
        cnt = ans_counts.get(num, 0)
        ratio = cnt / total
        in_range = _ANSWER_NO_MIN_RATIO <= ratio <= _ANSWER_NO_MAX_RATIO
        if not in_range:
            all_in_range = False
        ans_dist[str(num)] = {
            "count": cnt,
            "ratio": round(ratio, 4),
            "in_range": in_range,
        }

    # 최장 연속 실행 계산
    max_run = 1
    current_run = 1
    for i in range(1, len(items)):
        if items[i].answer_no == items[i - 1].answer_no:
            current_run += 1
            if current_run > max_run:
                max_run = current_run
        else:
            current_run = 1

    return {
        "difficulty": {
            "target": [
                blueprint.difficulty_targets.get("easy", 0.45),
                blueprint.difficulty_targets.get("medium", 0.35),
                blueprint.difficulty_targets.get("hard", 0.20),
            ],
            "actual": [
                round(easy_n / total, 4),
                round(med_n / total, 4),
                round(hard_n / total, 4),
            ],
        },
        "chapter_even_maxdiff": chapter_even_maxdiff,
        "source_breakdown": {
            "target": src_target,
            "actual": src_actual,
        },
        "answer_no_balance": {
            "distribution": ans_dist,
            "in_range": all_in_range,
            "max_run": max_run,
        },
    }


def build_quality_report(
    items: list[ExamItemDraft],
    blueprint: ExamenBlueprint,
) -> str:
    """Render the 출제품질리포트.md as a Markdown string.

    Sections:
    1. 개요
    2. 챕터별 문항 수
    3. 난이도 분포 (목표 vs 실측, ✅/⚠️)
    4. 출처 구성비 (목표 vs 실측, ✅/⚠️)
    5. 정답 번호 분포 (목표 15–25%, 연속 ≤2, ✅/⚠️)
    6. 교재 근거 확인 요약

    Args:
        items: The exam items to report on.
        blueprint: The exam blueprint declaring targets.

    Returns:
        Markdown-formatted quality report string.
    """
    tva = build_targets_vs_actual(items, blueprint)
    total = len(items)
    lines: list[str] = []

    # ----------------------------------------------------------------
    # 1. 헤더
    # ----------------------------------------------------------------
    lines.append("# 출제품질리포트")
    lines.append("")
    lines.append(f"- **시험**: {blueprint.exam_name}")
    lines.append(f"- **과목**: {blueprint.course_slug}")
    lines.append(f"- **학기**: {blueprint.semester}")
    lines.append(f"- **총 문항 수**: {total}문항 (목표 {blueprint.total_items})")
    lines.append("")

    # ----------------------------------------------------------------
    # 2. 챕터별 문항 수
    # ----------------------------------------------------------------
    lines.append("## 챕터별 문항 수")
    lines.append("")
    ch_counter = Counter(i.chapter for i in items)
    # 챕터 목록을 blueprint.chapters 순서로 정렬
    ordered_chapters = [ch for ch in blueprint.chapters if ch in ch_counter]
    # blueprint 에 없는 챕터도 포함 (있다면)
    extra = [ch for ch in ch_counter if ch not in set(blueprint.chapters)]
    ordered_chapters += sorted(extra)

    # 목표: 챕터 균등 (total // len(chapters) ±1)
    n_ch = len(blueprint.chapters) if blueprint.chapters else 1
    target_per_ch = total / n_ch
    maxdiff = tva["chapter_even_maxdiff"]
    maxdiff_ok = maxdiff <= 1
    maxdiff_icon = "✅" if maxdiff_ok else "⚠️"

    lines.append("| 챕터 | 문항 수 |")
    lines.append("|------|---------|")
    for ch in ordered_chapters:
        cnt = ch_counter.get(ch, 0)
        lines.append(f"| {ch} | {cnt} |")
    lines.append("")
    lines.append(
        f"{maxdiff_icon} 챕터별 최대 편차: **{maxdiff}** "
        f"(목표 ≤1, 목표 균등 {target_per_ch:.1f}문항/챕터)"
    )
    lines.append("")

    # ----------------------------------------------------------------
    # 3. 난이도 분포
    # ----------------------------------------------------------------
    lines.append("## 난이도 분포 (목표 vs 실측)")
    lines.append("")
    diff_targets = tva["difficulty"]["target"]
    diff_actuals = tva["difficulty"]["actual"]
    labels = ["쉬움 (1_쉬움)", "보통 (2_보통)", "어려움 (3_어려움)"]
    lines.append("| 난이도 | 목표 | 실측 | 편차 | 판정 |")
    lines.append("|--------|------|------|------|------|")
    for label, tgt, act in zip(labels, diff_targets, diff_actuals, strict=False):
        diff_val = act - tgt
        ok = abs(diff_val) <= _DIFFICULTY_TOLERANCE
        icon = "✅" if ok else "⚠️"
        lines.append(
            f"| {label} | {tgt:.1%} | {act:.1%} | {diff_val:+.1%} | {icon} |"
        )
    lines.append("")

    # ----------------------------------------------------------------
    # 4. 출처 구성비
    # ----------------------------------------------------------------
    lines.append("## 출처 구성비 (목표 vs 실측)")
    lines.append("")
    src_target = tva["source_breakdown"]["target"]
    src_actual = tva["source_breakdown"]["actual"]
    all_sources = sorted(set(list(src_target.keys()) + list(src_actual.keys())))
    lines.append("| 출처 | 목표 | 실측 | 판정 |")
    lines.append("|------|------|------|------|")
    for src in all_sources:
        tgt_n = src_target.get(src, 0)
        act_n = src_actual.get(src, 0)
        ok = tgt_n == act_n
        icon = "✅" if ok else "⚠️"
        lines.append(f"| {src} | {tgt_n} | {act_n} | {icon} |")
    lines.append("")

    # ----------------------------------------------------------------
    # 5. 정답 번호 분포
    # ----------------------------------------------------------------
    lines.append("## 정답 번호 분포 (목표: 각 15~25%, 연속 ≤2)")
    lines.append("")
    ans_bal = tva["answer_no_balance"]
    max_run = ans_bal["max_run"]
    run_ok = max_run <= 2
    run_icon = "✅" if run_ok else "⚠️"

    lines.append("| 정답번호 | 문항 수 | 비율 | 판정 |")
    lines.append("|----------|---------|------|------|")
    for num in range(1, 6):
        entry = ans_bal["distribution"].get(str(num), {"count": 0, "ratio": 0.0, "in_range": False})
        cnt = entry["count"]
        ratio = entry["ratio"]
        in_range = entry["in_range"]
        icon = "✅" if in_range else "⚠️"
        lines.append(f"| {num}번 | {cnt} | {ratio:.1%} | {icon} |")
    lines.append("")
    lines.append(
        f"{run_icon} 최장 연속 동일 정답번호: **{max_run}** (목표 ≤2)"
    )
    overall_bal = "✅" if ans_bal["in_range"] and run_ok else "⚠️"
    balance_status = "적합" if ans_bal["in_range"] and run_ok else "이탈"
    lines.append(f"{overall_bal} 정답 번호 균형 전체: {balance_status}")
    lines.append("")

    # ----------------------------------------------------------------
    # 6. 교재 근거 확인 요약
    # ----------------------------------------------------------------
    lines.append("## 교재 근거 확인 (Groundedness)")
    lines.append("")
    confirmed = sum(
        1 for i in items
        if i.textbook_evidence and i.textbook_evidence.status == "확인"
    )
    unconfirmed = total - confirmed
    conf_ratio = confirmed / total if total > 0 else 0.0
    unconf_ok = unconfirmed == 0
    unconf_icon = "✅" if unconf_ok else "⚠️"
    lines.append("| 상태 | 문항 수 | 비율 |")
    lines.append("|------|---------|------|")
    lines.append(f"| 확인 | {confirmed} | {conf_ratio:.1%} |")
    lines.append(f"| 미확인 | {unconfirmed} | {1 - conf_ratio:.1%} |")
    lines.append("")
    lines.append(f"{unconf_icon} 미확인 문항: {unconfirmed}건")
    lines.append("")

    return "\n".join(lines)


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


__all__ = [
    "build_targets_vs_actual",
    "build_quality_report",
    "write_quality_report",
]
