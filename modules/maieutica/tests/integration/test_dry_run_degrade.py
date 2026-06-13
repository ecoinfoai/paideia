"""T036 — RED→GREEN regression: dry-run degrade keeps the v0.1.1 deterministic prefix.

After the v0.1.1 pipeline rework (chunk → ``assign_subsections`` → per-subsection
sequential generation), the dry-run path must still complete the DETERMINISTIC
stages WITHOUT any LLM — and those stages now explicitly INCLUDE subsection
assignment (소절 배정). This test extends ``test_us6_dryrun_degrade.py`` for the
new property: every quiz bundle written by ``maieutica dry-run`` must reflect
subsection-scoped context (carry ``subsection_chunk_id`` / ``intra_ordinal`` in
its metadata) with an EMPTY ``avoid_list`` (no generation has happened, so there
is nothing yet to avoid — the allowed degrade).

Asserts (FR-012 / Constitution I):

1. Exit code 0 — no hard stop when the LLM is absent (no responses dir).
2. One non-empty, parseable bundle JSON per ASSIGNED quiz slot + per formative
   slot is written to the Silver staging directory.
3. Quiz bundles reflect subsection assignment: metadata carries a non-empty
   ``subsection_chunk_id`` + a ≥1 ``intra_ordinal``, and ``avoid_list == []``.
   (Before the ``_run_dry_run`` enhancement these were UNASSIGNED — ``""`` /
   ``0`` / whole-chapter fallback — so this assertion is the RED.)
4. ``ingest_report.json`` is written (deterministic stages recorded).

All I/O is under ``tmp_path`` — no real ``data/`` directory is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from maieutica.cli.main import app

# ---------------------------------------------------------------------------
# Fixture content — a chapter with multiple numbered subsections, so the
# deterministic ``assign_subsections`` stage has a real spread to compute.
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 6
_FORMATIVE_COUNT = 2

_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 코의 구조",
        "코는 들이마신 공기를 데우고 가습하는 첫 관문이다.",
        "코털과 점막은 먼지와 이물질을 거른다.",
        "",
        "2. 인두와 후두",
        "인두는 공기와 음식이 함께 지나가는 통로이다.",
        "후두는 발성을 담당하며 기도를 보호한다.",
        "",
        "3. 기관과 기관지",
        "기관은 후두에서 갈라져 좌우 폐로 이어진다.",
        "기관지는 공기를 좌우 폐로 나누어 전달하는 통로이다.",
        "",
        "4. 폐포와 가스 교환",
        "폐포는 모세혈관과 맞닿아 가스를 교환한다.",
        "폐포에서는 산소가 혈액으로 들어가고 이산화탄소가 나온다.",
        "",
    ]
)


def _build_bronze(tmp_path: Path) -> tuple[Path, Path]:
    """Lay out a minimal Bronze tree (no responses dir) → ``(bronze, data_root)``."""
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
                "sections": [
                    "1. 코의 구조",
                    "2. 인두와 후두",
                    "3. 기관과 기관지",
                    "4. 폐포와 가스 교환",
                ],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


def test_dry_run_degrade_writes_subsection_scoped_bundles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run (LLM 0) completes the deterministic prefix incl. 소절 배정.

    FR-012 / Constitution I: no hard stop, no silent omission; quiz bundles are
    subsection-scoped (proving ``assign_subsections`` ran) with an empty
    ``avoid_list`` (the allowed degrade — nothing generated yet to avoid).
    """
    import maieutica.cli.main as cli_module

    bronze, data_root = _build_bronze(tmp_path)
    # Redirect the module-level _DATA_ROOT (silver/staging resolution).
    monkeypatch.setattr(cli_module, "_DATA_ROOT", data_root)

    exit_code = app(
        [
            "dry-run",
            "--semester",
            _SEMESTER,
            "--course",
            _COURSE,
            "--week",
            str(_WEEK),
            "--generation-spec",
            str(bronze / "generation_spec.yaml"),
            "--curriculum-map",
            str(bronze / "curriculum_map.yaml"),
            "--backend",
            "subscription",
        ]
    )

    # 1. No hard stop without LLM (Constitution I).
    assert exit_code == 0, f"expected exit 0, got {exit_code}"

    silver = data_root / "silver" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    staging = silver / "staging"

    # 4. Deterministic stages recorded.
    ingest_report = silver / "ingest_report.json"
    assert ingest_report.is_file(), "ingest_report.json not written by dry-run"

    # 2. Quiz bundles exist, are parseable + non-empty.
    quiz_bundles = sorted(staging.glob("quiz-*.json"))
    assert quiz_bundles, "no quiz bundles written"

    # The chapter has 4 subsections → capacity = min(6, 3*4) = 6, so all N quiz
    # slots are assignable here.
    assert len(quiz_bundles) == _QUIZ_COUNT, (
        f"expected {_QUIZ_COUNT} quiz bundles, found {len(quiz_bundles)}: "
        + ", ".join(f.name for f in quiz_bundles)
    )

    # 3. Every quiz bundle reflects SUBSECTION assignment (the v0.1.1 property).
    seen_subsections: set[str] = set()
    for bundle_file in quiz_bundles:
        data = json.loads(bundle_file.read_text(encoding="utf-8"))
        assert data["slot_id"] == bundle_file.stem
        meta = data["metadata"]
        # Subsection-scoped: assign_subsections ran (RED before enhancement).
        assert meta["subsection_chunk_id"], (
            f"{bundle_file.name}: empty subsection_chunk_id — "
            "assign_subsections did not run (dry-run degrade regressed)"
        )
        assert meta["intra_ordinal"] >= 1, (
            f"{bundle_file.name}: intra_ordinal {meta['intra_ordinal']} < 1 — "
            "slot not subsection-assigned"
        )
        # Allowed degrade: nothing generated yet → avoid_list empty.
        assert meta["avoid_list"] == [], (
            f"{bundle_file.name}: avoid_list must be empty in dry-run, "
            f"got {meta['avoid_list']!r}"
        )
        # Bundle is non-empty / has a rendered prompt.
        assert data["prompt"].strip(), f"{bundle_file.name}: empty prompt"
        seen_subsections.add(meta["subsection_chunk_id"])

    # Spread proof: the assigned bundles cover ≥2 distinct subsections.
    assert len(seen_subsections) >= 2, (
        f"quiz bundles cover only {len(seen_subsections)} subsection(s) — "
        "assignment did not spread"
    )

    # Formative bundles exist too (one per formative slot).
    formative_bundles = sorted(staging.glob("formative-*.json"))
    assert len(formative_bundles) == _FORMATIVE_COUNT, (
        f"expected {_FORMATIVE_COUNT} formative bundles, "
        f"found {len(formative_bundles)}"
    )
    for bundle_file in formative_bundles:
        data = json.loads(bundle_file.read_text(encoding="utf-8"))
        assert data["prompt"].strip(), f"{bundle_file.name}: empty prompt"

    # All I/O is under tmp_path (no real data/ touched).
    assert str(staging).startswith(str(tmp_path))
