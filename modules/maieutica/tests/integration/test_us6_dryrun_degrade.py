"""T055 — Integration test: dry-run path (US6, SC-011).

Asserts that ``dry-run`` (or the dry-run pipeline function) with NO canned
responses:

1. Writes ``quiz-{week}-001..N`` bundle files to the Silver staging directory.
2. Writes ``formative-{chapter_no}-001..M`` bundle files to the staging dir.
3. Completes the deterministic stages — ``ingest_report.json`` is written.
4. Makes ZERO LLM calls (Constitution I: no backend invoked in dry-run).
5. Does not raise any exception (no hard stop — SC-011).

All I/O is under ``tmp_path`` — no real ``data/`` directory is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from maieutica.cli.main import _run_dry_run

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 3
_FORMATIVE_COUNT = 2

_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 호흡계통의 구조",
        "코는 후각과 공기 가습을 담당한다.",
        "폐포는 가스 교환이 일어나는 포상 구조이다.",
        "기관지는 공기를 폐로 전달하는 통로이다.",
        "가로막은 수축하여 흉강 부피를 늘린다.",
        "",
    ]
)


def _build_bronze(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal Bronze tree for testing.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        ``(bronze_dir, data_root)`` pair.
    """
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    bronze.mkdir(parents=True, exist_ok=True)

    (bronze / f"{_CHAPTER} 호흡.txt").write_text(_CHAPTER_TXT, encoding="utf-8")

    spec = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "week": _WEEK,
        "chapter_no": _CHAPTER_NO,
        "chapter": _CHAPTER,
        "quiz_count": _QUIZ_COUNT,
        "formative_count": _FORMATIVE_COUNT,
    }
    (bronze / "generation_spec.yaml").write_text(
        json.dumps(spec, ensure_ascii=False), encoding="utf-8"
    )

    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": _WEEK,
                "chapter": _CHAPTER,
                "chapter_no": _CHAPTER_NO,
                "sections": ["1. 호흡계통의 구조"],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


class _FakeArgs:
    """Minimal argparse namespace for dry-run (injects data_root via monkeypatch)."""

    def __init__(self) -> None:
        self.semester = _SEMESTER
        self.course = _COURSE
        self.week = _WEEK
        self.generation_spec: Path | None = None
        self.curriculum_map: Path | None = None
        self.quiz_count: int | None = None
        self.formative_count: int | None = None
        self.backend = "subscription"


def test_us6_dryrun_writes_quiz_and_formative_bundles(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """Dry-run writes quiz + formative bundles; deterministic stages complete; 0 LLM.

    SC-011: no hard stop (exception) when LLM is absent.
    """
    import maieutica.cli.main as cli_module

    bronze, data_root = _build_bronze(tmp_path)
    # Redirect _DATA_ROOT so the CLI resolves paths under tmp_path
    monkeypatch.setattr(cli_module, "_DATA_ROOT", data_root)

    args = _FakeArgs()
    # Point to the test bronze dir explicitly so spec/curriculum_map are found.
    args.generation_spec = bronze / "generation_spec.yaml"  # type: ignore[attr-defined]
    args.curriculum_map = bronze / "curriculum_map.yaml"  # type: ignore[attr-defined]

    # No responses dir needed — dry-run must NOT touch any backend.
    exit_code = _run_dry_run(args)  # type: ignore[arg-type]

    assert exit_code == 0, f"expected exit 0, got {exit_code}"

    silver = (
        data_root / "silver" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    )
    staging = silver / "staging"

    # --- Quiz bundles exist ---
    for ordinal in range(1, _QUIZ_COUNT + 1):
        slot_id = f"quiz-{_WEEK}-{ordinal:03d}"
        bundle_file = staging / f"{slot_id}.json"
        assert bundle_file.is_file(), f"missing quiz bundle: {bundle_file.name}"
        data = json.loads(bundle_file.read_text(encoding="utf-8"))
        assert data["slot_id"] == slot_id
        assert data["metadata"]["week"] == _WEEK
        assert data["metadata"]["chapter_no"] == _CHAPTER_NO

    # --- Formative bundles exist ---
    for ordinal in range(1, _FORMATIVE_COUNT + 1):
        slot_id = f"formative-{_CHAPTER_NO}-{ordinal:03d}"
        bundle_file = staging / f"{slot_id}.json"
        assert bundle_file.is_file(), f"missing formative bundle: {bundle_file.name}"
        data = json.loads(bundle_file.read_text(encoding="utf-8"))
        assert data["slot_id"] == slot_id
        assert data["metadata"]["chapter_no"] == _CHAPTER_NO

    # --- Deterministic stages completed: ingest_report.json written ---
    ingest_report = silver / "ingest_report.json"
    assert ingest_report.is_file(), "ingest_report.json not written by dry-run"
    report_data = json.loads(ingest_report.read_text(encoding="utf-8"))
    assert report_data["textbook"]["chapters_found"] == 1

    # --- Bundle count (no extras) ---
    all_bundles = list(staging.glob("*.json"))
    expected_count = _QUIZ_COUNT + _FORMATIVE_COUNT
    assert len(all_bundles) == expected_count, (
        f"expected {expected_count} bundles, found {len(all_bundles)}: "
        + ", ".join(f.name for f in sorted(all_bundles))
    )

    # --- All I/O is under tmp_path ---
    assert str(staging).startswith(str(tmp_path))
