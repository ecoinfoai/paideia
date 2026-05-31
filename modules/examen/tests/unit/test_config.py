"""Unit tests for examen.ingest.config — T012.

TDD: tests written BEFORE implementation.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


_VALID_BLUEPRINT = """\
    semester: "2026-1"
    course_slug: "anatomy"
    exam_name: "2026-1학기 기말고사"
    total_items: 48
    chapters:
      - "8장. 호흡계통"
      - "9장. 근육계통"
    difficulty_targets:
      easy: 0.45
      medium: 0.35
      hard: 0.20
    source_mix:
      formative: 12
      quiz: 15
      textbook: 21
    answer_key_balance: true
"""

_VALID_CURRICULUM_MAP = """\
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
        subtopic: "근육 생리"
        sections:
          - "근수축 기전"
"""


# ---------------------------------------------------------------------------
# T012 — load_blueprint
# ---------------------------------------------------------------------------

class TestLoadBlueprint:
    def test_valid_blueprint_returns_model(self, tmp_path: Path) -> None:
        """Valid blueprint.yaml is parsed and returns ExamenBlueprint."""
        from examen.ingest.config import load_blueprint

        p = _write(tmp_path, "blueprint.yaml", _VALID_BLUEPRINT)
        bp = load_blueprint(p)
        assert bp.semester == "2026-1"
        assert bp.course_slug == "anatomy"
        assert bp.total_items == 48
        assert bp.source_mix["formative"] == 12

    def test_missing_file_raises_with_path(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError with the path in the message."""
        from examen.ingest.config import load_blueprint

        missing = tmp_path / "blueprint.yaml"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_blueprint(missing)

    def test_total_items_out_of_range_raises_with_location(self, tmp_path: Path) -> None:
        """total_items < 40 raises ValueError that includes the file path."""
        from examen.ingest.config import load_blueprint

        bad = _VALID_BLUEPRINT.replace("total_items: 48", "total_items: 10")
        # source_mix sum must still equal total_items=10 for V2 not to fire first
        bad = bad.replace("formative: 12\n      quiz: 15\n      textbook: 21",
                          "formative: 3\n      quiz: 4\n      textbook: 3")
        p = _write(tmp_path, "blueprint.yaml", bad)
        with pytest.raises(ValueError) as exc_info:
            load_blueprint(p)
        msg = str(exc_info.value)
        assert str(p) in msg, f"file path not in error: {msg}"

    def test_source_mix_sum_mismatch_raises_with_location(self, tmp_path: Path) -> None:
        """sum(source_mix) != total_items raises ValueError with file path."""
        from examen.ingest.config import load_blueprint

        # source_mix sum = 40, total_items = 48 → V2 fires
        bad = _VALID_BLUEPRINT.replace("formative: 12", "formative: 5")
        p = _write(tmp_path, "blueprint.yaml", bad)
        with pytest.raises(ValueError) as exc_info:
            load_blueprint(p)
        assert str(p) in str(exc_info.value)

    def test_invalid_yaml_raises_with_location(self, tmp_path: Path) -> None:
        """Malformed YAML raises ValueError with the file path."""
        from examen.ingest.config import load_blueprint

        p = tmp_path / "blueprint.yaml"
        p.write_bytes(b":\t bad: [yaml\n")
        with pytest.raises(ValueError, match=str(p)):
            load_blueprint(p)

    def test_extra_field_forbidden(self, tmp_path: Path) -> None:
        """Unknown field in YAML is rejected (extra='forbid')."""
        from examen.ingest.config import load_blueprint

        bad = _VALID_BLUEPRINT + "unknown_field: 999\n"
        p = _write(tmp_path, "blueprint.yaml", bad)
        with pytest.raises(ValueError):
            load_blueprint(p)


# ---------------------------------------------------------------------------
# T012 — load_curriculum_map
# ---------------------------------------------------------------------------

class TestLoadCurriculumMap:
    def test_valid_map_returns_model(self, tmp_path: Path) -> None:
        """Valid curriculum_map.yaml returns CurriculumMap."""
        from examen.ingest.config import load_curriculum_map

        p = _write(tmp_path, "curriculum_map.yaml", _VALID_CURRICULUM_MAP)
        cm = load_curriculum_map(p)
        assert cm.semester == "2026-1"
        assert len(cm.entries) == 2

    def test_missing_file_raises_with_path(self, tmp_path: Path) -> None:
        from examen.ingest.config import load_curriculum_map

        missing = tmp_path / "curriculum_map.yaml"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_curriculum_map(missing)

    def test_invalid_yaml_raises_with_location(self, tmp_path: Path) -> None:
        from examen.ingest.config import load_curriculum_map

        p = tmp_path / "curriculum_map.yaml"
        p.write_bytes(b"bad:\t[yaml\n")
        with pytest.raises(ValueError, match=str(p)):
            load_curriculum_map(p)

    def test_missing_required_field_raises_with_location(self, tmp_path: Path) -> None:
        """Missing 'entries' raises ValidationError with file path."""
        from examen.ingest.config import load_curriculum_map

        p = _write(tmp_path, "curriculum_map.yaml",
                   "semester: '2026-1'\ncourse_slug: 'anatomy'\n")
        with pytest.raises(ValueError, match=str(p)):
            load_curriculum_map(p)


# ---------------------------------------------------------------------------
# T012 — bronze_dir helper
# ---------------------------------------------------------------------------

class TestBronzeDir:
    def test_returns_expected_path(self, tmp_path: Path) -> None:
        from examen.ingest.config import bronze_dir

        result = bronze_dir("2026-1", "anatomy", data_root=tmp_path)
        expected = tmp_path / "bronze" / "examen" / "2026-1-anatomy"
        assert result == expected

    def test_default_data_root(self) -> None:
        """Without data_root, returns a relative path under data/."""
        from examen.ingest.config import bronze_dir

        result = bronze_dir("2026-1", "anatomy")
        # Should follow convention data/bronze/examen/{semester}-{course_slug}/
        assert result.parts[-1] == "2026-1-anatomy"
        assert "bronze" in result.parts
        assert "examen" in result.parts
