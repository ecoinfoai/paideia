"""T033 — 형성평가 source inventory loader.

``load_formative_inventory`` parses:
1. 형성평가_실제_출제문제들.txt — the actually-administered subset
   (format: ``{week}주차 {n}. {stem}``)
2. ``Ch*_FormativeTest.yaml`` — per-chapter YAML files with model_answer,
   keywords, rubric.

For each administered item the matching question is looked up in the YAML
files and a ``SourceInventoryEntry`` is emitted with all fields populated.

Fail-fast (located error) if an administered item cannot be matched to a
YAML question — no silent drop (constitution: 조용한 누락 금지).

Usage::

    from examen.ingest.source_inventory import load_formative_inventory

    inventory = load_formative_inventory(
        actual_txt=Path("형성평가_실제_출제문제들.txt"),
        chapter_yamls=[Path("Ch8_FormativeTest.yaml"), ...],
        curriculum_map=curriculum_map,
        semester="2026-1",
        course_slug="anatomy",
    )
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from paideia_shared.schemas import CurriculumMap, SourceInventoryEntry

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# 형식: "9주차 1. 들숨과 날숨 ..." (전각 숫자 없음, ASCII 마침표)
_ACTUAL_LINE_RE = re.compile(
    r"^(?P<week>\d+)주차\s+(?P<ordinal>\d+)\.\s+(?P<stem>.+)$",
    re.UNICODE,
)


def _parse_actual_txt(path: Path) -> list[dict[str, Any]]:
    """Parse 형성평가_실제_출제문제들.txt into a list of dicts.

    Each dict has keys: ``week`` (int), ``ordinal`` (int), ``stem`` (str).

    Args:
        path: Path to the actually-administered formative questions file.

    Returns:
        List of parsed administered-item dicts (in file order).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If a non-blank line does not match the expected format.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"load_formative_inventory: actual_txt not found: {path}"
        )

    items: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        m = _ACTUAL_LINE_RE.match(line)
        if m is None:
            raise ValueError(
                f"load_formative_inventory: actual_txt line {lineno} does not match "
                f"expected format '{{week}}주차 {{n}}. {{stem}}': {line!r}"
            )
        items.append(
            {
                "week": int(m.group("week")),
                "ordinal": int(m.group("ordinal")),
                "stem": m.group("stem").strip(),
            }
        )
    return items


def _load_chapter_yaml(path: Path) -> dict[str, Any]:
    """Load and return a Ch*_FormativeTest.yaml file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML dict with ``metadata`` and ``questions`` keys.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the YAML is malformed or missing expected keys.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"load_formative_inventory: chapter YAML not found: {path}"
        )
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"load_formative_inventory: YAML {path.name} must be a mapping, "
            f"got {type(data).__name__}"
        )
    if "questions" not in data:
        raise ValueError(
            f"load_formative_inventory: YAML {path.name} missing 'questions' key"
        )
    return data


def _build_yaml_index(
    chapter_yamls: list[Path],
) -> dict[int, dict[str, Any]]:
    """Build a chapter_no → YAML data index from a list of YAML paths.

    Args:
        chapter_yamls: List of paths to Ch*_FormativeTest.yaml files.

    Returns:
        Dict mapping ``chapter_no`` (int) → parsed YAML data dict.

    Raises:
        ValueError: If a YAML file is missing the ``metadata.chapter`` key.
    """
    index: dict[int, dict[str, Any]] = {}
    for yaml_path in chapter_yamls:
        data = _load_chapter_yaml(yaml_path)
        metadata = data.get("metadata", {})
        if "chapter" not in metadata:
            raise ValueError(
                f"load_formative_inventory: YAML {yaml_path.name} missing "
                "'metadata.chapter' field"
            )
        ch_no = int(metadata["chapter"])
        index[ch_no] = data
    return index


def _week_to_chapter_no(week: int, curriculum_map: CurriculumMap) -> int | None:
    """Resolve week → chapter_no via curriculum_map.

    Returns the chapter_no for the first matching entry, or None if not found.

    Args:
        week: Week number.
        curriculum_map: Validated CurriculumMap.

    Returns:
        Integer chapter_no or None.
    """
    for entry in curriculum_map.entries:
        if entry.week == week:
            return entry.chapter_no
    return None


def _stem_matches(administered_stem: str, yaml_stem: str) -> bool:
    """Return True if the administered stem matches a YAML question stem.

    Matching strategy:
    1. Exact match (after strip).
    2. Substring match: administered stem is a prefix of the yaml stem (or vice
       versa) when each exceeds 10 characters — handles minor trailing edits.

    Args:
        administered_stem: Stem from 형성평가_실제_출제문제들.txt.
        yaml_stem: Stem from Ch*_FormativeTest.yaml question.stem.

    Returns:
        True if considered a match.
    """
    a = administered_stem.strip()
    y = yaml_stem.strip()
    if a == y:
        return True
    # 줄임 매칭: 실제 출제문이 YAML 보다 짧게 기재된 경우 (앞 부분 일치)
    min_len = 10
    if len(a) >= min_len and len(y) >= min_len:
        shorter = a if len(a) <= len(y) else y
        longer = y if len(a) <= len(y) else a
        if longer.startswith(shorter):
            return True
    return False


def _find_matching_question(
    week: int,
    ordinal: int,
    administered_stem: str,
    chapter_no: int,
    yaml_index: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Find the YAML question record matching an administered item.

    Primary key: chapter_no + ordinal (sn) when ordinal matches.
    Fallback: stem-based matching within the chapter.

    Args:
        week: Week number (used in error messages).
        ordinal: 1-based ordinal from the actual file.
        administered_stem: Stem text from the actual file.
        chapter_no: Resolved chapter number from curriculum_map.
        yaml_index: chapter_no → YAML data index.

    Returns:
        The matched YAML question dict (with sn, question, model_answer, etc.).

    Raises:
        ValueError: If no matching question is found (fail-fast, located error).
    """
    yaml_data = yaml_index.get(chapter_no)
    if yaml_data is None:
        raise ValueError(
            f"load_formative_inventory: 형성평가_실제_출제문제들.txt의 "
            f"{week}주차 {ordinal}번 문제(chapter_no={chapter_no})에 대응하는 "
            f"Ch{chapter_no}_FormativeTest.yaml 이 없습니다. "
            "chapter_yamls 목록을 확인하세요."
        )

    questions: list[dict[str, Any]] = yaml_data.get("questions", [])

    # 전략 1: sn == ordinal 으로 직접 매핑.
    # 단, sn 이 일치해도 stem 이 호환되지 않으면(교수가 순서를 바꿔 출제한 경우)
    # 잘못된 문제에 바인딩될 수 있으므로 stem 호환성을 추가로 검증한다.
    # 호환되지 않으면 전략 2(stem 매칭)로 폴백한다.
    for q in questions:
        if q.get("sn") == ordinal:
            yaml_stem = str(q.get("question", ""))
            if _stem_matches(administered_stem, yaml_stem):
                return q
            # sn 은 맞지만 stem 불일치 → 폴백 (조용히 잘못 바인딩 금지)
            break

    # 전략 2: stem 유사 매칭 (ordinal 불일치 허용).
    # 모호성 방지: 동일 administered stem 에 둘 이상의 yaml 문제가 매칭되면
    # 어떤 것을 바인딩할지 확정할 수 없으므로 located error 를 던진다.
    matches: list[dict[str, Any]] = []
    for q in questions:
        yaml_stem = str(q.get("question", ""))
        if _stem_matches(administered_stem, yaml_stem):
            matches.append(q)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        matched_sns = [q.get("sn") for q in matches]
        raise ValueError(
            f"load_formative_inventory: 실제 출제 형성평가 문제가 YAML 의 여러 문제와 "
            f"모호하게 매칭됩니다(매칭 sn={matched_sns}). "
            f"week={week}, ordinal={ordinal}, chapter_no={chapter_no}, "
            f"stem={administered_stem!r}. "
            "Ch{chapter}_FormativeTest.yaml 의 중복 stem 을 확인하거나 stem 을 더 "
            "구체적으로 기재하세요(모호한 자동 바인딩 금지)."
        )

    # 매칭 실패 → fail-fast (조용한 누락 금지)
    raise ValueError(
        f"load_formative_inventory: 실제 출제된 형성평가 문제를 YAML에서 찾을 수 없습니다. "
        f"week={week}, ordinal={ordinal}, chapter_no={chapter_no}, "
        f"stem={administered_stem!r}. "
        f"Ch{chapter_no}_FormativeTest.yaml 의 questions 목록({len(questions)}개)을 확인하세요. "
        "조용한 누락 금지(constitution): administered 문항은 전수 포함되어야 합니다."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_formative_inventory(
    actual_txt: Path,
    chapter_yamls: list[Path],
    curriculum_map: CurriculumMap,
    semester: str,
    course_slug: str,
) -> list[SourceInventoryEntry]:
    """Parse formative inventory from actual_txt + chapter YAMLs.

    For each item in ``actual_txt`` (the actually-administered subset), finds
    the matching question in the per-chapter YAML and emits a
    ``SourceInventoryEntry(source="formative", ...)`` with model_answer,
    keywords, and rubric populated.

    Args:
        actual_txt: Path to 형성평가_실제_출제문제들.txt (administered items).
        chapter_yamls: List of paths to Ch*_FormativeTest.yaml files.
        curriculum_map: Validated CurriculumMap (week → chapter_no lookup).
        semester: SemesterCode for the SourceInventoryEntry.
        course_slug: CourseSlug for the SourceInventoryEntry.

    Returns:
        List of SourceInventoryEntry objects (one per administered item, in
        file order).

    Raises:
        FileNotFoundError: If actual_txt or any chapter YAML is missing.
        ValueError: If a line in actual_txt cannot be parsed, if the
            week→chapter mapping is missing, or if an administered item has
            no matching YAML question (fail-fast, located error).
    """
    # Step 1: parse actually-administered items
    administered = _parse_actual_txt(actual_txt)

    # Step 2: build chapter_no → YAML data index
    yaml_index = _build_yaml_index(chapter_yamls)

    # Step 3: for each administered item, resolve chapter_no and find match
    entries: list[SourceInventoryEntry] = []
    for adm in administered:
        week = adm["week"]
        ordinal = adm["ordinal"]
        stem = adm["stem"]

        # week → chapter_no via curriculum_map
        chapter_no = _week_to_chapter_no(week, curriculum_map)
        if chapter_no is None:
            raise ValueError(
                f"load_formative_inventory: curriculum_map에 {week}주차 항목이 없습니다. "
                f"(실제 출제문: {stem!r}) "
                "curriculum_map에 해당 주차를 추가하세요."
            )

        # Find matching YAML question (fail-fast if not found)
        q = _find_matching_question(
            week=week,
            ordinal=ordinal,
            administered_stem=stem,
            chapter_no=chapter_no,
            yaml_index=yaml_index,
        )

        sn = q.get("sn", ordinal)  # prefer YAML sn; fall back to ordinal
        source_ref = f"형성평가:{chapter_no}장#{sn}"

        # Support 정보 (공유정보) — 선택적으로 model_answer 에 병합
        support: dict[str, str] | None = q.get("support")
        model_answer_text: str = q.get("model_answer", "")
        if support:
            # 공유정보를 model_answer 끝에 덧붙여 convert_formative 에서 활용 가능하게
            support_text = " ".join(support.values())
            model_answer_text = f"{model_answer_text}\n[공유정보] {support_text}"

        entry = SourceInventoryEntry(
            semester=semester,
            course_slug=course_slug,
            source="formative",
            source_ref=source_ref,
            chapter_no=chapter_no,
            week=week,
            stem=stem,
            model_answer=model_answer_text or None,
            keywords=q.get("keywords", []),
            rubric=q.get("rubric"),
        )
        entries.append(entry)

    return entries


__all__ = ["load_formative_inventory"]
