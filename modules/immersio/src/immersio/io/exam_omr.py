"""OMR XLS/XLSX parser for the four-section, four-sheet department format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from ..ingest.errors import DuplicateStudentIdError
from ..normalize import normalize_student_id

EXPECTED_SHEETS: frozenset[str] = frozenset({"결과", "결시", "OX", "문항분석"})

SectionLabel = Literal["A", "B", "C", "D"]


@dataclass(frozen=True)
class OMRSectionResult:
    """Per-section parsed payload."""

    section: SectionLabel
    responses_long: pd.DataFrame  # cols: student_id, section, item_no, response
    summary: pd.DataFrame  # cols: student_id, section, exam_taken, exam_total/max_score
    items: pd.DataFrame  # item metadata extracted from the 문항분석 sheet


def _engine_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xls":
        return "xlrd"
    if suffix == ".xlsx":
        return "openpyxl"
    raise ValueError(
        f"exam_omr parser: unsupported extension {suffix!r} for {path}; "
        f"expected .xls or .xlsx."
    )


_SECTION_TOKENS: tuple[str, ...] = ("A반", "B반", "C반", "D반")

DEFAULT_RESULT_EXCLUDE_TOKENS: frozenset[str] = frozenset({"(OX)", "(문항분석)", "결시"})
"""Default exclude tokens for the per-section main-result discovery (FR-029).

A file is treated as a *main result* (eligible for analysis) when its name
matches the section pattern AND contains none of these substrings. Operators
can override via ``--exam-result-pattern`` for review or QA workflows.
"""

DEFAULT_ABSENT_PATTERN_TEMPLATE: str = "*{section}반*결시.xls"
"""Default glob template for the absent-list workbook per section (FR-029)."""


def _section_glob_patterns(section: str) -> list[str]:
    """Return the sequence of glob patterns expanded for ``parse_exam_omr_xls``.

    Covers underscore/space/no-separator variants for both ``.xls`` and
    ``.xlsx`` (research §R-08b). Order is deterministic so subsequent
    deduplication preserves insertion order across runs.
    """
    token = f"{section}반"
    suffixes = ("xls", "xlsx")
    separators = (f"_{token}_", f"_{token} ", f" {token} ", f"_{token}", f" {token}")
    patterns: list[str] = []
    for sep in separators:
        for suffix in suffixes:
            patterns.append(f"*{sep}*.{suffix}")
    # Last resort fallback: section token anywhere in the filename.
    for suffix in suffixes:
        patterns.append(f"*{token}*.{suffix}")
    return patterns


def discover_section_files(
    dir_path: Path,
    section: str,
    *,
    result_pattern_override: str | None = None,
    exclude_tokens: frozenset[str] | None = None,
    on_empty: Literal["raise", "empty"] = "empty",
) -> list[Path]:
    """Discover the per-section main-result workbooks under ``dir_path``.

    Args:
        dir_path: Directory holding department OMR exports.
        section: Single-letter section label ("A".."D").
        result_pattern_override: When set, only this glob is matched and
            ``exclude_tokens`` defaults to empty (operator opted in).
        exclude_tokens: Substrings; any matching file is dropped. ``None`` →
            ``DEFAULT_RESULT_EXCLUDE_TOKENS`` for default discovery; empty
            frozenset for override mode (operator selected explicit pattern).
        on_empty: ``"raise"`` raises ``FileNotFoundError`` when no match; the
            default ``"empty"`` returns ``[]`` (caller decides).

    Returns:
        Sorted (by stable Path order) list of unique matched files.

    Raises:
        FileNotFoundError: When ``on_empty='raise'`` and no file matched.
        ValueError: When ``section`` is empty or ``dir_path`` is not a directory.
    """
    if not section:
        raise ValueError("discover_section_files: section must not be empty")
    if not dir_path.is_dir():
        raise ValueError(f"discover_section_files: not a directory: {dir_path}")

    if exclude_tokens is None:
        exclude_tokens = (
            frozenset() if result_pattern_override is not None else DEFAULT_RESULT_EXCLUDE_TOKENS
        )

    if result_pattern_override is not None:
        patterns: list[str] = [result_pattern_override]
    else:
        patterns = _section_glob_patterns(section)

    seen: list[Path] = []
    for pattern in patterns:
        for match in dir_path.glob(pattern):
            if not match.is_file():
                continue
            if any(token in match.name for token in exclude_tokens):
                continue
            if match not in seen:
                seen.append(match)

    if not seen and on_empty == "raise":
        raise FileNotFoundError(
            f"discover_section_files: no per-section file under {dir_path} for "
            f"section {section!r} with patterns {patterns}."
        )
    return sorted(seen)


def _detect_section(path: Path) -> SectionLabel:
    name = path.name
    for token in _SECTION_TOKENS:
        if token in name:
            return token[0]  # type: ignore[return-value]
    raise ValueError(
        f"exam_omr parser: cannot infer section from filename {path.name!r}; "
        f"expected one of {_SECTION_TOKENS}."
    )


def _parse_one_section(path: Path) -> OMRSectionResult:
    section = _detect_section(path)
    engine = _engine_for(path)
    sheets = pd.read_excel(path, sheet_name=None, engine=engine, dtype=object)
    sheet_names = set(sheets.keys())
    missing = EXPECTED_SHEETS - sheet_names
    if missing:
        raise ValueError(
            f"exam_omr parser: {path} missing sheets {sorted(missing)}; "
            f"found {sorted(sheet_names)}."
        )

    # Items metadata from 문항분석 sheet
    items = sheets["문항분석"].copy()
    items_records: list[dict] = []
    for _, row in items.iterrows():
        items_records.append(
            {
                "item_no": int(row["item_no"]),
                "chapter": (str(row["chapter"]) if pd.notna(row["chapter"]) else None),
                "source": (str(row["source"]) if pd.notna(row["source"]) else None),
                "expected_difficulty": (
                    str(row["expected_difficulty"])
                    if pd.notna(row["expected_difficulty"])
                    else None
                ),
                "bloom": (str(row["bloom"]) if pd.notna(row["bloom"]) else None),
                "answer_key": str(row["answer_key"]),
                "points": float(row["points"]),
                "text": (str(row["text"]) if pd.notna(row["text"]) else None),
            }
        )
    items_df = (
        pd.DataFrame.from_records(items_records)
        .sort_values("item_no")
        .reset_index(drop=True)
    )

    # Detect duplicate item_no
    if items_df["item_no"].duplicated().any():
        dup = items_df.loc[items_df["item_no"].duplicated(), "item_no"].tolist()
        raise ValueError(
            f"exam_omr parser: duplicate item_no in 문항분석 sheet of {path}: {dup}."
        )

    # 결과 sheet → long-form responses + score summary
    results = sheets["결과"].copy()
    item_columns = [c for c in results.columns if isinstance(c, str) and c.startswith("item_")]
    score_column = "점수"

    response_records: list[dict] = []
    summary_records: list[dict] = []
    seen_student_ids: list[str] = []

    for _, row in results.iterrows():
        student_id = normalize_student_id(str(row["학번"]))
        if student_id in seen_student_ids:
            raise DuplicateStudentIdError(
                f"exam_omr parser: duplicate student_id {student_id!r} in 결과 sheet of {path}."
            )
        seen_student_ids.append(student_id)
        for col in item_columns:
            item_no = int(col.removeprefix("item_"))
            value = row[col]
            response_str: str | None
            if value is None or (isinstance(value, float) and pd.isna(value)):
                response_str = None
            else:
                response_str = str(value)
                if response_str == "":
                    response_str = None
            response_records.append(
                {
                    "student_id": student_id,
                    "section": section,
                    "item_no": item_no,
                    "response": response_str,
                }
            )
        score = row[score_column]
        max_score = sum(items_df["points"])
        summary_records.append(
            {
                "student_id": student_id,
                "section": section,
                "exam_taken": True,
                "exam_total_score": (float(score) if pd.notna(score) else None),
                "exam_max_score": float(max_score),
            }
        )

    # 결시 sheet → exam_taken=False rows merged into summary
    absent_df = sheets["결시"]
    for _, row in absent_df.iterrows():
        if pd.isna(row.get("학번")):
            continue
        student_id = normalize_student_id(str(row["학번"]))
        if student_id in seen_student_ids:
            raise DuplicateStudentIdError(
                f"exam_omr parser: student_id {student_id!r} listed in both "
                f"결과 and 결시 sheets of {path}."
            )
        seen_student_ids.append(student_id)
        max_score = sum(items_df["points"])
        summary_records.append(
            {
                "student_id": student_id,
                "section": section,
                "exam_taken": False,
                "exam_total_score": None,
                "exam_max_score": float(max_score),
            }
        )

    response_columns = ["student_id", "section", "item_no", "response"]
    responses_df = pd.DataFrame.from_records(response_records, columns=response_columns)
    if not responses_df.empty:
        responses_df = responses_df.sort_values(["student_id", "item_no"]).reset_index(drop=True)

    summary_columns = [
        "student_id",
        "section",
        "exam_taken",
        "exam_total_score",
        "exam_max_score",
    ]
    summary_df = pd.DataFrame.from_records(summary_records, columns=summary_columns)
    if not summary_df.empty:
        summary_df = summary_df.sort_values("student_id").reset_index(drop=True)

    return OMRSectionResult(
        section=section, responses_long=responses_df, summary=summary_df, items=items_df
    )


def parse_exam_omr_xls(
    dir_path: Path,
    *,
    exam_result_pattern: str | None = None,
    exam_absent_pattern: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse all per-section OMR workbooks in a directory.

    Args:
        dir_path: Directory holding ``인체구조와기능_*반_결과.xls`` (or .xlsx) files.
        exam_result_pattern: Optional override glob for the per-section main
            result workbook (FR-029). When set, ``DEFAULT_RESULT_EXCLUDE_TOKENS``
            no longer applies — operator is responsible for the glob being
            specific enough. When ``None`` (default) the underscore/space/no-
            separator variants are tried in order and ``(OX)``/``(문항분석)``/
            ``결시`` files are excluded automatically.
        exam_absent_pattern: Reserved for symmetry with ``exam_result_pattern``;
            currently unused because absent rows live inside each main result
            workbook's ``결시`` sheet (see ``_parse_one_section``). Kept here
            so the CLI can pass it through without diverging signatures.

    Returns:
        Tuple of three DataFrames:
            - responses_long: (student_id, section, item_no, response)
            - summary:        (student_id, section, exam_taken, exam_total_score, exam_max_score)
            - items:          (item_no, chapter, source, expected_difficulty, bloom,
                               answer_key, points, text) — deduplicated across sections

    Raises:
        TypeError: If dir_path is not a pathlib.Path.
        FileNotFoundError: If dir_path does not exist or no per-section file
            matched any glob variant.
        ValueError: For schema, sheet, or duplicate-student violations.
    """
    _ = exam_absent_pattern  # accepted for CLI passthrough; behaviour reserved
    if not isinstance(dir_path, Path):
        raise TypeError(f"parse_exam_omr_xls: expected Path, got {type(dir_path).__name__}.")
    if not dir_path.is_dir():
        raise FileNotFoundError(f"parse_exam_omr_xls: directory missing: {dir_path}.")

    section_files: list[Path] = []
    for section_letter in ("A", "B", "C", "D"):
        section_files.extend(
            discover_section_files(
                dir_path,
                section=section_letter,
                result_pattern_override=exam_result_pattern,
                on_empty="empty",
            )
        )
    section_files = sorted(set(section_files))
    if not section_files:
        raise FileNotFoundError(
            f"parse_exam_omr_xls: no per-section files matched under {dir_path}; "
            f"tried underscore/space/no-separator glob variants for A/B/C/D반 "
            f"with default exclude tokens {sorted(DEFAULT_RESULT_EXCLUDE_TOKENS)}."
        )

    parsed = [_parse_one_section(path) for path in section_files]

    responses_df = pd.concat([r.responses_long for r in parsed], ignore_index=True)
    summary_df = pd.concat([r.summary for r in parsed], ignore_index=True)

    cross_section_dupes = summary_df["student_id"].duplicated()
    if cross_section_dupes.any():
        offenders = summary_df.loc[cross_section_dupes, "student_id"].tolist()
        raise DuplicateStudentIdError(
            f"parse_exam_omr_xls: student_id values appearing in multiple sections "
            f"under {dir_path}: {sorted(set(offenders))}."
        )

    # Items: assert agreement across sections
    canonical_items = parsed[0].items
    for other in parsed[1:]:
        if not canonical_items.equals(other.items):
            raise ValueError(
                f"parse_exam_omr_xls: 문항분석 metadata diverges between section "
                f"{parsed[0].section} and {other.section} under {dir_path}."
            )

    if not responses_df.empty:
        responses_df = responses_df.sort_values(["student_id", "item_no"]).reset_index(drop=True)
    if not summary_df.empty:
        summary_df = summary_df.sort_values("student_id").reset_index(drop=True)
    return responses_df, summary_df, canonical_items.copy()
