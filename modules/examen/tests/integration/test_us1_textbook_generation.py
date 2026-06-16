"""T019 — Integration test: textbook-only build pipeline (US1 MVP).

Tests the full build_exam() function with:
- A 2-chapter textbook-only blueprint (total_items=4, 2 items per chapter)
- A 2-chapter curriculum_map
- Synthetic textbook .txt fixtures in a temp Bronze dir
- FakeBackend returning canned valid items (no network)

Assertions:
- item count == total_items (4)
- chapter-even distribution (max diff ≤ 1)
- every item has 5 options (format-checked)
- every item has groundedness status explicitly set (확인 or 미확인)
- xlsx + yaml + manifest written to run dir
- re-run byte-identical (xlsx + yaml)
- no real data/ directory touched
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import openpyxl
import yaml
from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    LLMBackend,
)
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    ExamenBlueprint,
    ExamItemDraft,
)

# ---------------------------------------------------------------------------
# Canned LLM response (valid ExamItemDraft shape)
# ---------------------------------------------------------------------------

_CANNED_ITEM_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "1_쉬움",
    "stem_polarity": "부정형",
    "text": "다음 중 폐포에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① " + "가" * 28,
        "② " + "나" * 28,
        "③ " + "다" * 28,
        "④ " + "라" * 28,
        "⑤ " + "마" * 28,
    ],
    "answer_no": 3,
    "distractor_rationale": [
        "옳은 진술: 폐포에서 가스 교환이 일어난다.",
        "옳은 진술: 폐포막은 매우 얇다.",
        "틀린 진술: 폐포에는 섬모가 있다.",
        "옳은 진술: 폐포는 포상 구조이다.",
        "옳은 진술: 산소가 혈액으로 이동한다.",
    ],
    "wrong_explanation": "폐포 관련 오답 설명 텍스트." * 20,
    "leap_explanation": "폐포 관련 도약 설명 텍스트." * 20,
    "intent": "폐포의 기본 구조와 기능을 확인한다.",
    "key_concept": "폐포",
}


class FakeBackend(LLMBackend):
    """Returns canned JSON for all requests; counts calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        import json as _json

        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=_json.dumps(_CANNED_ITEM_JSON, ensure_ascii=False),
            model="fake-model",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Fixtures builders
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
# Must be >= 40 (ExamenBlueprint schema invariant V1).
# Use 40 (minimum valid value) with 2 chapters → 20 items each.
_TOTAL_ITEMS = 40


def _make_blueprint() -> ExamenBlueprint:
    return ExamenBlueprint(
        semester=_SEMESTER,
        course_slug=_COURSE,
        exam_name="2026-1학기 기말고사",
        total_items=_TOTAL_ITEMS,
        chapters=["8장 호흡계통", "9장 근육계통"],
        difficulty_targets={"easy": 0.50, "medium": 0.50, "hard": 0.0},
        source_mix={"textbook": _TOTAL_ITEMS, "formative": 0, "quiz": 0},
    )


def _make_curriculum_map() -> CurriculumMap:
    return CurriculumMap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        entries=[
            CurriculumEntry(
                week=1,
                chapter="8장 호흡계통",
                chapter_no=8,
                subtopic=None,
                sections=["1. 기도", "2. 폐"],
            ),
            CurriculumEntry(
                week=2,
                chapter="9장 근육계통",
                chapter_no=9,
                subtopic=None,
                sections=["1. 골격근", "2. 평활근"],
            ),
        ],
    )


def _write_chapter_fixture(bronze_dir: Path, chapter_no: int, chapter_name: str) -> None:
    """Write a minimal synthetic textbook .txt fixture to bronze_dir."""
    fname = f"{chapter_no}장 {chapter_name}.txt"
    content = (
        f"{chapter_no}장 {chapter_name}\n"
        "1. 제일 절\n"
        f"{chapter_name}에 관한 주요 내용이 이 단락에 포함된다.\n"
        "폐포에서 가스 교환이 일어난다.\n"
        "산소와 이산화탄소가 교환된다.\n"
        "2. 두 번째 절\n"
        f"{chapter_name}의 추가 내용입니다.\n"
        "기능과 구조에 대한 설명.\n"
    )
    (bronze_dir / fname).write_text(content, encoding="utf-8")


def _setup_bronze(bronze_dir: Path) -> None:
    """Write blueprint.yaml, curriculum_map.yaml, and chapter .txt files."""
    import yaml as _yaml

    bronze_dir.mkdir(parents=True, exist_ok=True)

    # blueprint.yaml
    blueprint_data = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "exam_name": "2026-1학기 기말고사",
        "total_items": _TOTAL_ITEMS,  # 40 (minimum valid per schema)
        "chapters": ["8장 호흡계통", "9장 근육계통"],
        "difficulty_targets": {"easy": 0.50, "medium": 0.50, "hard": 0.0},
        "source_mix": {"textbook": _TOTAL_ITEMS, "formative": 0, "quiz": 0},
    }
    (bronze_dir / "blueprint.yaml").write_text(
        _yaml.dump(blueprint_data, allow_unicode=True), encoding="utf-8"
    )

    # curriculum_map.yaml
    curriculum_data = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": 1,
                "chapter": "8장 호흡계통",
                "chapter_no": 8,
                "subtopic": None,
                "sections": ["1. 기도", "2. 폐"],
            },
            {
                "week": 2,
                "chapter": "9장 근육계통",
                "chapter_no": 9,
                "subtopic": None,
                "sections": ["1. 골격근", "2. 평활근"],
            },
        ],
    }
    (bronze_dir / "curriculum_map.yaml").write_text(
        _yaml.dump(curriculum_data, allow_unicode=True), encoding="utf-8"
    )

    # Chapter .txt files
    _write_chapter_fixture(bronze_dir, 8, "호흡계통")
    _write_chapter_fixture(bronze_dir, 9, "근육계통")


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestUS1TextbookBuild:
    """Integration tests for build_exam() with textbook-only blueprint."""

    def _run_build(
        self,
        tmp_path: Path,
        *,
        backend: LLMBackend | None = None,
    ) -> tuple[list[ExamItemDraft], Path]:
        """Set up fixtures and run build_exam; return (items, run_dir)."""
        from examen.pipeline import build_exam

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        if backend is None:
            backend = FakeBackend()

        blueprint = _make_blueprint()
        curriculum_map = _make_curriculum_map()

        items, run_dir = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=backend,
        )
        return items, run_dir

    # --- Item count ---

    def test_item_count_equals_total_items(self, tmp_path: Path) -> None:
        """build_exam returns exactly total_items items."""
        items, _ = self._run_build(tmp_path)
        assert len(items) == _TOTAL_ITEMS, f"Expected {_TOTAL_ITEMS} items, got {len(items)}"

    # --- Chapter-even distribution ---

    def test_chapter_even_distribution(self, tmp_path: Path) -> None:
        """Chapter distribution differs by at most 1 (chapter-even)."""
        from collections import Counter

        items, _ = self._run_build(tmp_path)
        counts = Counter(item.chapter for item in items)
        assert len(counts) == 2, f"Expected 2 chapters, got {counts}"
        max_c = max(counts.values())
        min_c = min(counts.values())
        assert max_c - min_c <= 1, f"Chapter distribution not even: {dict(counts)}"

    # --- Format ---

    def test_every_item_has_five_options(self, tmp_path: Path) -> None:
        """Every generated item has exactly 5 options."""
        items, _ = self._run_build(tmp_path)
        for item in items:
            assert len(item.options) == 5, f"item {item.item_no} has {len(item.options)} options"

    def test_every_item_has_option_length_ok_set(self, tmp_path: Path) -> None:
        """option_length_ok is set (True or False) on every item."""
        items, _ = self._run_build(tmp_path)
        for item in items:
            assert item.option_length_ok is not None, (
                f"item {item.item_no}: option_length_ok is None"
            )

    # --- Groundedness ---

    def test_every_item_groundedness_status_set(self, tmp_path: Path) -> None:
        """Every item has textbook_evidence with status explicitly '확인' or '미확인'."""
        items, _ = self._run_build(tmp_path)
        for item in items:
            assert item.textbook_evidence is not None, (
                f"item {item.item_no}: textbook_evidence is None"
            )
            assert item.textbook_evidence.status in ("확인", "미확인"), (
                f"item {item.item_no}: unexpected status {item.textbook_evidence.status!r}"
            )

    # --- Gold output files ---

    def test_xlsx_written_to_run_dir(self, tmp_path: Path) -> None:
        """xlsx file written to the run-isolated Gold dir."""
        _, run_dir = self._run_build(tmp_path)
        xlsx_files = list(run_dir.glob("*.xlsx"))
        assert len(xlsx_files) >= 1, f"No xlsx in {run_dir}: {list(run_dir.iterdir())}"

    def test_yaml_written_to_run_dir(self, tmp_path: Path) -> None:
        """yaml file written to the run-isolated Gold dir."""
        _, run_dir = self._run_build(tmp_path)
        yaml_files = list(run_dir.glob("*.yaml"))
        assert len(yaml_files) >= 1, f"No yaml in {run_dir}: {list(run_dir.iterdir())}"

    def test_manifest_written_to_run_dir(self, tmp_path: Path) -> None:
        """manifest_examen.json written to the run-isolated Gold dir."""
        _, run_dir = self._run_build(tmp_path)
        manifest_path = run_dir / "manifest_examen.json"
        assert manifest_path.exists(), f"No manifest_examen.json in {run_dir}"

    def test_ingest_report_written_to_run_dir(self, tmp_path: Path) -> None:
        """ingest_report.json written to the run-isolated Gold dir."""
        _, run_dir = self._run_build(tmp_path)
        report_path = run_dir / "ingest_report.json"
        assert report_path.exists(), f"No ingest_report.json in {run_dir}"

    def test_manifest_item_count_matches(self, tmp_path: Path) -> None:
        """manifest_examen.json item_count == total_items."""
        _, run_dir = self._run_build(tmp_path)
        manifest_path = run_dir / "manifest_examen.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["item_count"] == _TOTAL_ITEMS, (
            f"manifest item_count={manifest['item_count']}, expected {_TOTAL_ITEMS}"
        )

    def test_manifest_chapter_breakdown_present(self, tmp_path: Path) -> None:
        """manifest chapter_breakdown contains all blueprint chapters."""
        _, run_dir = self._run_build(tmp_path)
        manifest_path = run_dir / "manifest_examen.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        breakdown = manifest["chapter_breakdown"]
        assert "8장 호흡계통" in breakdown
        assert "9장 근육계통" in breakdown

    def test_manifest_backend_label_for_fake_backend(self, tmp_path: Path) -> None:
        """FakeBackend (no real LLM) → manifest llm_backend == 'none(dry-run)'."""
        _, run_dir = self._run_build(tmp_path)
        manifest_path = run_dir / "manifest_examen.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["llm_backend"] == "none(dry-run)", (
            f"FakeBackend should map to 'none(dry-run)', got {manifest['llm_backend']!r}"
        )

    def test_manifest_backend_label_reflects_subscription(self, tmp_path: Path) -> None:
        """A SubscriptionBackend → manifest llm_backend == 'subscription'.

        Locks the backend-label inference: the manifest reflects the ACTUAL
        backend used.  We pre-fill the responses dir so the SubscriptionBackend
        resolves every slot without raising.
        """
        import json as _json

        from examen.generate.backend import SubscriptionBackend
        from examen.pipeline import build_exam

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        blueprint = _make_blueprint()
        curriculum_map = _make_curriculum_map()

        # Pre-fill responses for every slot the solver will produce.
        from examen.plan.blueprint import solve

        slots = solve(blueprint, curriculum_map)
        staging_dir = tmp_path / "staging"
        responses_dir = tmp_path / "responses"
        responses_dir.mkdir(parents=True, exist_ok=True)
        for slot in slots:
            resp = {
                "slot_id": slot.slot_id,
                "raw_text": _json.dumps(_CANNED_ITEM_JSON, ensure_ascii=False),
                "model": "claude-subscription",
            }
            (responses_dir / f"{slot.slot_id}.json").write_text(
                _json.dumps(resp, ensure_ascii=False), encoding="utf-8"
            )

        backend = SubscriptionBackend(staging_dir=staging_dir, responses_dir=responses_dir)
        _, run_dir = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=backend,
        )
        manifest = json.loads((run_dir / "manifest_examen.json").read_text(encoding="utf-8"))
        assert manifest["llm_backend"] == "subscription", (
            f"SubscriptionBackend should map to 'subscription', got {manifest['llm_backend']!r}"
        )

    # --- Run isolation ---

    def test_run_dir_is_under_gold_runs(self, tmp_path: Path) -> None:
        """run_dir is under data/gold/examen/{semester}-{course}/runs/."""
        _, run_dir = self._run_build(tmp_path)
        assert "runs" in str(run_dir), f"run_dir not under 'runs': {run_dir}"

    def test_no_data_dir_touched(self, tmp_path: Path) -> None:
        """No files created outside of tmp_path (real data/ untouched)."""
        real_data = Path("data")
        before_exists = real_data.exists()
        self._run_build(tmp_path)
        # If data/ didn't exist before, it shouldn't now
        if not before_exists:
            assert not real_data.exists(), "build_exam created real data/ directory"

    # --- Re-run byte-identical ---

    def test_rerun_xlsx_byte_identical(self, tmp_path: Path) -> None:
        """Two separate build_exam runs with same inputs produce identical xlsx."""
        from examen.pipeline import build_exam

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        blueprint = _make_blueprint()
        curriculum_map = _make_curriculum_map()

        # First run
        be1 = FakeBackend()
        _, run_dir1 = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=be1,
        )
        xlsx_path = list(run_dir1.glob("*.xlsx"))[0]
        bytes_run1 = xlsx_path.read_bytes()

        # Second run (same data_root → same run_id → same dir, overwrites in place)
        be2 = FakeBackend()
        _, run_dir2 = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=be2,
        )
        bytes_run2 = xlsx_path.read_bytes()

        # Same run_id → same run_dir
        assert run_dir1 == run_dir2, f"Different run dirs: {run_dir1} vs {run_dir2}"
        # Real cross-run byte comparison (run 1 bytes vs run 2 bytes)
        assert bytes_run1 == bytes_run2, "xlsx not byte-identical across re-runs"

    def test_rerun_yaml_byte_identical(self, tmp_path: Path) -> None:
        """Two separate build_exam calls produce identical yaml (same run_dir)."""
        from examen.pipeline import build_exam

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        blueprint = _make_blueprint()
        curriculum_map = _make_curriculum_map()

        be1 = FakeBackend()
        _, run_dir = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=be1,
        )
        yaml_path = list(run_dir.glob("*.yaml"))[0]
        bytes_run1 = yaml_path.read_bytes()

        be2 = FakeBackend()
        build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=be2,
        )
        bytes_run2 = yaml_path.read_bytes()

        assert bytes_run1 == bytes_run2, "yaml not byte-identical on re-run"

    # --- Source is textbook-only ---

    def test_all_items_source_textbook(self, tmp_path: Path) -> None:
        """All items have source='textbook' for a textbook-only blueprint."""
        items, _ = self._run_build(tmp_path)
        for item in items:
            assert item.source == "textbook", f"item {item.item_no} has source={item.source!r}"

    # --- xlsx 28-col contract satisfied ---

    def test_xlsx_has_28_columns(self, tmp_path: Path) -> None:
        """Integration: the emitted xlsx has exactly 28 columns."""
        _, run_dir = self._run_build(tmp_path)
        xlsx_path = list(run_dir.glob("*.xlsx"))[0]
        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        assert len(headers) == 28, f"Expected 28 columns, got {len(headers)}"

    # --- yaml has nested textbook_evidence ---

    def test_yaml_has_nested_evidence(self, tmp_path: Path) -> None:
        """Integration: yaml contains nested textbook_evidence dict."""
        _, run_dir = self._run_build(tmp_path)
        yaml_path = list(run_dir.glob("*.yaml"))[0]
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        for d in data:
            if d.get("textbook_evidence") is not None:
                ev = d["textbook_evidence"]
                assert isinstance(ev, dict), "textbook_evidence must be nested dict"
                assert "status" in ev
                assert ev["status"] in ("확인", "미확인")
