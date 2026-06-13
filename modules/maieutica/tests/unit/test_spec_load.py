"""Unit tests for maieutica.ingest.spec_load — T017.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- load_generation_spec: valid YAML → MaieuticaGenerationSpec; missing file,
  malformed YAML, schema violation all raise with file path in message.
- load_curriculum_map: valid YAML → CurriculumMap; missing file, bad YAML raise.
- validate_week_in_map: week absent from CurriculumMap → raises (exit 2);
  error message names the week AND the curriculum_map path.
- resolve_chapter_txt: chapter .txt file missing from bronze_dir → raises
  (exit 2); error message names the path.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture YAML helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


_VALID_SPEC = """\
    semester: "2026-1"
    course_slug: "anatomy"
    week: 9
    chapter_no: 8
    chapter: "8장. 호흡계통"
    quiz_count: 20
    formative_count: 3
"""

_VALID_MAP = """\
    semester: "2026-1"
    course_slug: "anatomy"
    entries:
      - week: 9
        chapter_no: 8
        chapter: "8장. 호흡계통"
        subtopic: null
        sections:
          - "호흡기의 구조와 기능"
          - "호흡운동"
      - week: 10
        chapter_no: 9
        chapter: "9장. 근육계통"
        subtopic: null
        sections:
          - "근수축 기전"
"""


# ============================================================================
# T017 — load_generation_spec
# ============================================================================


class TestLoadGenerationSpec:
    def test_valid_spec_returns_model(self, tmp_path: Path) -> None:
        """Valid generation_spec.yaml returns MaieuticaGenerationSpec."""
        from maieutica.ingest.spec_load import load_generation_spec

        p = _write(tmp_path, "generation_spec.yaml", _VALID_SPEC)
        spec = load_generation_spec(p)

        assert spec.semester == "2026-1"
        assert spec.course_slug == "anatomy"
        assert spec.week == 9
        assert spec.chapter_no == 8
        assert spec.quiz_count == 20
        assert spec.formative_count == 3

    def test_defaults_applied_when_counts_absent(self, tmp_path: Path) -> None:
        """quiz_count and formative_count default to 20 / 3 when omitted."""
        from maieutica.ingest.spec_load import load_generation_spec

        minimal = """\
            semester: "2026-1"
            course_slug: "anatomy"
            week: 9
            chapter_no: 8
            chapter: "8장. 호흡계통"
        """
        p = _write(tmp_path, "generation_spec.yaml", minimal)
        spec = load_generation_spec(p)
        assert spec.quiz_count == 20
        assert spec.formative_count == 3

    def test_missing_file_raises_with_path(self, tmp_path: Path) -> None:
        """Missing file → FileNotFoundError whose message includes the path."""
        from maieutica.ingest.spec_load import load_generation_spec

        missing = tmp_path / "generation_spec.yaml"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_generation_spec(missing)

    def test_malformed_yaml_raises_with_path(self, tmp_path: Path) -> None:
        """Malformed YAML → ValueError whose message includes the file path."""
        from maieutica.ingest.spec_load import load_generation_spec

        p = tmp_path / "generation_spec.yaml"
        p.write_bytes(b":\t bad: [yaml\n")
        with pytest.raises(ValueError, match=str(p)):
            load_generation_spec(p)

    def test_missing_required_field_raises_with_path_and_field(
        self, tmp_path: Path
    ) -> None:
        """Missing required 'week' → ValueError naming both the file and the field."""
        from maieutica.ingest.spec_load import load_generation_spec

        bad = """\
            semester: "2026-1"
            course_slug: "anatomy"
            chapter_no: 8
            chapter: "8장. 호흡계통"
        """
        p = _write(tmp_path, "generation_spec.yaml", bad)
        with pytest.raises(ValueError) as exc_info:
            load_generation_spec(p)
        msg = str(exc_info.value)
        assert str(p) in msg, f"file path not in error: {msg}"
        assert "week" in msg, f"offending field not in error: {msg}"

    def test_extra_field_forbidden(self, tmp_path: Path) -> None:
        """Unknown field → ValueError (extra='forbid')."""
        from maieutica.ingest.spec_load import load_generation_spec

        bad = _VALID_SPEC + "unknown_field: 999\n"
        p = _write(tmp_path, "generation_spec.yaml", bad)
        with pytest.raises(ValueError):
            load_generation_spec(p)

    def test_invalid_week_raises(self, tmp_path: Path) -> None:
        """week < 1 violates schema → ValueError."""
        from maieutica.ingest.spec_load import load_generation_spec

        bad = _VALID_SPEC.replace("week: 9", "week: 0")
        p = _write(tmp_path, "generation_spec.yaml", bad)
        with pytest.raises(ValueError):
            load_generation_spec(p)


# ============================================================================
# T017 — load_curriculum_map
# ============================================================================


class TestLoadCurriculumMap:
    def test_valid_map_returns_model(self, tmp_path: Path) -> None:
        """Valid curriculum_map.yaml returns CurriculumMap."""
        from maieutica.ingest.spec_load import load_curriculum_map

        p = _write(tmp_path, "curriculum_map.yaml", _VALID_MAP)
        cm = load_curriculum_map(p)
        assert cm.semester == "2026-1"
        assert len(cm.entries) == 2

    def test_missing_file_raises_with_path(self, tmp_path: Path) -> None:
        from maieutica.ingest.spec_load import load_curriculum_map

        missing = tmp_path / "curriculum_map.yaml"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_curriculum_map(missing)

    def test_malformed_yaml_raises_with_path(self, tmp_path: Path) -> None:
        from maieutica.ingest.spec_load import load_curriculum_map

        p = tmp_path / "curriculum_map.yaml"
        p.write_bytes(b"bad:\t[yaml\n")
        with pytest.raises(ValueError, match=str(p)):
            load_curriculum_map(p)

    def test_missing_entries_raises_with_path_and_field(
        self, tmp_path: Path
    ) -> None:
        """Missing 'entries' → ValueError with file path + field name."""
        from maieutica.ingest.spec_load import load_curriculum_map

        p = _write(
            tmp_path,
            "curriculum_map.yaml",
            "semester: '2026-1'\ncourse_slug: 'anatomy'\n",
        )
        with pytest.raises(ValueError) as exc_info:
            load_curriculum_map(p)
        msg = str(exc_info.value)
        assert str(p) in msg, f"file path not in error: {msg}"
        assert "entries" in msg, f"offending field not in error: {msg}"


# ============================================================================
# T017 — validate_week_in_map (fail-fast: week absent from curriculum_map)
# ============================================================================


class TestValidateWeekInMap:
    def _make_map(self, tmp_path: Path) -> tuple[Path, object]:
        from maieutica.ingest.spec_load import load_curriculum_map

        p = _write(tmp_path, "curriculum_map.yaml", _VALID_MAP)
        return p, load_curriculum_map(p)

    def test_present_week_does_not_raise(self, tmp_path: Path) -> None:
        """Week 9 is in the curriculum_map → no exception."""
        from maieutica.ingest.spec_load import validate_week_in_map

        map_path, cm = self._make_map(tmp_path)
        validate_week_in_map(cm, week=9, curriculum_map_path=map_path)

    def test_absent_week_raises(self, tmp_path: Path) -> None:
        """Week 99 is NOT in the curriculum_map → raises ValueError."""
        from maieutica.ingest.spec_load import validate_week_in_map

        map_path, cm = self._make_map(tmp_path)
        with pytest.raises(ValueError):
            validate_week_in_map(cm, week=99, curriculum_map_path=map_path)

    def test_absent_week_error_names_week(self, tmp_path: Path) -> None:
        """Error message for absent week includes the week number."""
        from maieutica.ingest.spec_load import validate_week_in_map

        map_path, cm = self._make_map(tmp_path)
        with pytest.raises(ValueError) as exc_info:
            validate_week_in_map(cm, week=99, curriculum_map_path=map_path)
        assert "99" in str(exc_info.value), (
            f"week number not in error: {exc_info.value}"
        )

    def test_absent_week_error_names_file(self, tmp_path: Path) -> None:
        """Error message for absent week includes the curriculum_map file path."""
        from maieutica.ingest.spec_load import validate_week_in_map

        map_path, cm = self._make_map(tmp_path)
        with pytest.raises(ValueError) as exc_info:
            validate_week_in_map(cm, week=99, curriculum_map_path=map_path)
        assert str(map_path) in str(exc_info.value), (
            f"file path not in error: {exc_info.value}"
        )


# ============================================================================
# T017 — resolve_chapter_txt (fail-fast: chapter .txt missing)
# ============================================================================


class TestResolveChapterTxt:
    def test_existing_file_returned(self, tmp_path: Path) -> None:
        """Chapter file '8장 호흡계통.txt' present → returns its Path."""
        from maieutica.ingest.spec_load import resolve_chapter_txt

        txt = tmp_path / "8장 호흡계통.txt"
        txt.write_text("body", encoding="utf-8")
        result = resolve_chapter_txt(bronze_dir=tmp_path, chapter_no=8)
        assert result == txt

    def test_missing_file_raises_with_path(self, tmp_path: Path) -> None:
        """No chapter 8 file present → FileNotFoundError naming the directory."""
        from maieutica.ingest.spec_load import resolve_chapter_txt

        with pytest.raises(FileNotFoundError) as exc_info:
            resolve_chapter_txt(bronze_dir=tmp_path, chapter_no=8)
        msg = str(exc_info.value)
        assert str(tmp_path) in msg, f"bronze_dir not in error: {msg}"
        assert "8" in msg, f"chapter_no not in error: {msg}"

    def test_lenient_match_with_title(self, tmp_path: Path) -> None:
        """File '8장 호흡.txt' (N장 prefix) matches chapter_no=8."""
        from maieutica.ingest.spec_load import resolve_chapter_txt

        txt = tmp_path / "8장 호흡.txt"
        txt.write_text("body", encoding="utf-8")
        result = resolve_chapter_txt(bronze_dir=tmp_path, chapter_no=8)
        assert result == txt

    def test_colliding_chapter_no_not_matched(self, tmp_path: Path) -> None:
        """File '18장.txt' does NOT match chapter_no=8 (digit prefix guard)."""
        from maieutica.ingest.spec_load import resolve_chapter_txt

        (tmp_path / "18장.txt").write_text("body", encoding="utf-8")
        # Chapter 8 is still missing even though 18장.txt exists
        with pytest.raises(FileNotFoundError):
            resolve_chapter_txt(bronze_dir=tmp_path, chapter_no=8)
