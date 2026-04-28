"""Unit tests for OMR glob expansion + per-section priority (T017).

Spec 004 research §R-08b/c — parse_exam_omr_xls 가
- 분반 토큰 뒤에 _ / 공백 / 구분자 없음 모두 매칭
- 분반당 다중 파일 (`결과.xls`, `결과(OX).xls`, `결과(문항분석).xls`, `결시.xls`)
  중 결과 파일만 default 패턴이 선택
- ``--exam-result-pattern`` override 가능
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Pre-populate ``immersio.ingest`` to break ``io ↔ ingest`` circular import
# during standalone test collection. See test_attendance_roster_only.py for
# rationale.
import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order

from immersio.io.exam_omr import (  # noqa: E402
    DEFAULT_RESULT_EXCLUDE_TOKENS,
    discover_section_files,
)


SECTION_TOKENS = ("A", "B", "C", "D")


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_omr_glob_underscore_separator_matches(tmp_path: Path) -> None:
    """기존 ``*_A반_*.xls`` 형식이 계속 매칭된다."""
    target = _touch(tmp_path / "인체구조_A반_결과.xls")
    matches = discover_section_files(tmp_path, section="A")
    assert target in matches


def test_omr_glob_space_separator_matches(tmp_path: Path) -> None:
    """학과 OMR 실제 출력의 공백 구분자가 매칭된다 (FR-028)."""
    target = _touch(tmp_path / "인체구조 A반 결과.xls")
    matches = discover_section_files(tmp_path, section="A")
    assert target in matches


def test_omr_default_pattern_excludes_ox_and_analysis(tmp_path: Path) -> None:
    """default 패턴은 ``(OX)``/``(문항분석)``/``결시`` 토큰을 제외한다 (FR-029)."""
    result = _touch(tmp_path / "인체구조_A반_결과.xls")
    ox = _touch(tmp_path / "인체구조_A반_결과(OX).xls")
    analysis = _touch(tmp_path / "인체구조_A반_결과(문항분석).xls")
    absent = _touch(tmp_path / "인체구조_A반_결시.xls")
    matches = discover_section_files(tmp_path, section="A")
    assert result in matches
    assert ox not in matches
    assert analysis not in matches
    assert absent not in matches


def test_omr_per_section_picks_only_main_result(tmp_path: Path) -> None:
    """분반당 다중 파일 중 default 패턴은 ``결과.xls`` 만 정확히 1개를 선택한다."""
    main = _touch(tmp_path / "인체구조_A반_결과.xls")
    _touch(tmp_path / "인체구조_A반_결과(OX).xls")
    _touch(tmp_path / "인체구조_A반_결과(문항분석).xls")
    matches = discover_section_files(tmp_path, section="A")
    assert matches == [main]


def test_omr_pattern_override_supports_ox_for_review(tmp_path: Path) -> None:
    """``result_pattern_override`` 로 OX 파일을 강제 선택할 수 있다 (FR-029)."""
    main = _touch(tmp_path / "인체구조_A반_결과.xls")
    ox = _touch(tmp_path / "인체구조_A반_결과(OX).xls")
    matches = discover_section_files(
        tmp_path,
        section="A",
        result_pattern_override="*A반*결과(OX).xls",
        exclude_tokens=frozenset(),
    )
    assert ox in matches
    assert main not in matches


def test_omr_no_match_raises(tmp_path: Path) -> None:
    """매칭 0개면 명확한 에러 (FR-033 exit 3 = 파일 누락 신호)."""
    _touch(tmp_path / "B반_결과.xls")  # B반은 있으나 A반은 없음
    with pytest.raises(FileNotFoundError, match="A"):
        discover_section_files(tmp_path, section="A", on_empty="raise")


def test_omr_default_exclude_tokens_constant() -> None:
    """default exclude tokens 가 ``(OX)``, ``(문항분석)``, ``결시`` 를 포함한다."""
    assert "(OX)" in DEFAULT_RESULT_EXCLUDE_TOKENS
    assert "(문항분석)" in DEFAULT_RESULT_EXCLUDE_TOKENS
    assert "결시" in DEFAULT_RESULT_EXCLUDE_TOKENS
