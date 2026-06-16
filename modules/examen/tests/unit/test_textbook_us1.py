"""Unit tests for T021–T023 — textbook clean + evidence index + section chunking.

TDD: failing tests written BEFORE implementation.

Covers:
- T021 textbook_clean: spaced-letter headers, page numbers, figure/table captions,
  연습문제 block, 참고문헌, 각주 removal + removed_spans audit logging.
- T022 textbook loader: original 1-based line numbers preserved; evidence_index
  search; verify_chapter_files fail-fast (exit 2).
- T023 chunk: section-anchored chunks, deterministic chunk_id, line ranges
  pointing at ORIGINAL lines, removed_spans propagated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Shared fixture text (mimics real PDF-extracted textbook noise)
# ---------------------------------------------------------------------------

# 각 줄을 1-based 줄 번호로 매핑:
#  1: H U M A N  A N A T O M Y  &  P H Y S I O L O G Y  (spaced-letter header)
#  2: 제10장 내분비계통  (running header)
#  3: C H A P T E R  10  (spaced-letter header)
#  4: 257  (standalone page number)
#  5: (blank)
#  6: 1. 뇌하수체  (TOC entry)
#  7: 2. 갑상샘  (TOC entry)
#  8: 3. 부갑상샘  (TOC entry)
#  9: (blank)
# 10: 제10장 내분비계통  (running header repeated — keep body headings but drop pure header repeats)
# 11: (blank)
# 12: 1. 뇌하수체  (section heading in body)
# 13: (blank)
# 14: 뇌하수체는 터키안장에 위치한다.  (body text)
# 15: 전엽과 후엽으로 구성된다.  (body text)
# 16: 그림 10-3 뇌하수체의 구조와 기능  (figure caption — remove)
# 17: 뇌하수체 전엽에서는 여러 호르몬이 분비된다.  (body text)
# 18: (blank)
# 19: 258  (standalone page number)
# 20: (blank)
# 21: 2. 갑상샘  (section heading)
# 22: (blank)
# 23: 갑상샘은 목 앞쪽에 위치한다.  (body text)
# 24: 표 9-1 갑상샘 호르몬 목록  (table caption — remove)
# 25: 갑상샘호르몬은 대사를 조절한다.  (body text)
# 26: 티록신과 트리요오드티로닌이 주요 호르몬이다.  (body text)
# 27: (blank)
# 28: 3. 부갑상샘  (section heading)
# 29: (blank)
# 30: 부갑상샘은 갑상샘 뒤에 위치한다.  (body text)
# 31: 부갑상샘호르몬(PTH)은 혈중 칼슘 농도를 조절한다.  (body text)
# 32: (blank)
# 33: 259  (standalone page number)
# 34: (blank)
# 35: 연습문제  (exercise block start — remove from here to end)
# 36: (blank)
# 37: 1. 뇌하수체에서 분비되는 호르몬을 기술하시오.  (exercise)
# 38: 2. 갑상샘호르몬의 기능을 설명하시오.  (exercise)
# 39: 3. 부갑상샘의 위치와 기능을 서술하시오.  (exercise)

FIXTURE_LINES: list[str] = [
    "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y",  # 1
    "제10장 내분비계통",  # 2
    "C H A P T E R  10",  # 3
    "257",  # 4
    "",  # 5
    "1. 뇌하수체",  # 6
    "2. 갑상샘",  # 7
    "3. 부갑상샘",  # 8
    "",  # 9
    "제10장 내분비계통",  # 10  running header repeat
    "",  # 11
    "1. 뇌하수체",  # 12 section heading
    "",  # 13
    "뇌하수체는 터키안장에 위치한다.",  # 14
    "전엽과 후엽으로 구성된다.",  # 15
    "그림 10-3 뇌하수체의 구조와 기능",  # 16 figure caption
    "뇌하수체 전엽에서는 여러 호르몬이 분비된다.",  # 17
    "",  # 18
    "258",  # 19
    "",  # 20
    "2. 갑상샘",  # 21 section heading
    "",  # 22
    "갑상샘은 목 앞쪽에 위치한다.",  # 23
    "표 9-1 갑상샘 호르몬 목록",  # 24 table caption
    "갑상샘호르몬은 대사를 조절한다.",  # 25
    "티록신과 트리요오드티로닌이 주요 호르몬이다.",  # 26
    "",  # 27
    "3. 부갑상샘",  # 28 section heading
    "",  # 29
    "부갑상샘은 갑상샘 뒤에 위치한다.",  # 30
    "부갑상샘호르몬(PTH)은 혈중 칼슘 농도를 조절한다.",  # 31
    "",  # 32
    "259",  # 33
    "",  # 34
    "연습문제",  # 35 exercise block start
    "",  # 36
    "1. 뇌하수체에서 분비되는 호르몬을 기술하시오.",  # 37
    "2. 갑상샘호르몬의 기능을 설명하시오.",  # 38
    "3. 부갑상샘의 위치와 기능을 서술하시오.",  # 39
]


# ============================================================================
# T021: textbook_clean
# ============================================================================


class TestTextbookClean:
    """Tests for examen.ingest.textbook_clean.clean_textbook."""

    def _clean(self, lines: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
        """Helper: import and run clean_textbook, return (kept, removed_spans)."""
        from examen.ingest.textbook_clean import clean_textbook

        return clean_textbook(lines)

    def test_spaced_letter_header_removed(self) -> None:
        """Lines like 'H U M A N  A N A T O M Y' (all-caps single chars) are removed."""
        kept, removed = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y" not in kept_texts
        assert "C H A P T E R  10" not in kept_texts

    def test_spaced_letter_header_logged_in_removed_spans(self) -> None:
        """Removed spaced-letter headers appear in removed_spans."""
        _, removed = self._clean(FIXTURE_LINES)
        # At least one removed_spans entry should mention 'spaced_header' or similar
        assert any("spaced" in r.lower() or "header" in r.lower() for r in removed)

    def test_standalone_page_number_removed(self) -> None:
        """Lines that are purely a number (e.g. '257') are removed."""
        kept, _ = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "257" not in kept_texts
        assert "258" not in kept_texts
        assert "259" not in kept_texts

    def test_standalone_page_number_logged(self) -> None:
        """Removed page numbers appear in removed_spans."""
        _, removed = self._clean(FIXTURE_LINES)
        assert any("page" in r.lower() or "number" in r.lower() for r in removed)

    def test_figure_caption_removed(self) -> None:
        """Lines starting with '그림 NN-N' are removed."""
        kept, _ = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "그림 10-3 뇌하수체의 구조와 기능" not in kept_texts

    def test_table_caption_removed(self) -> None:
        """Lines starting with '표 NN-N' are removed."""
        kept, _ = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "표 9-1 갑상샘 호르몬 목록" not in kept_texts

    def test_figure_table_caption_logged(self) -> None:
        """Removed figure/table captions appear in removed_spans."""
        _, removed = self._clean(FIXTURE_LINES)
        assert any(
            "caption" in r.lower()
            or "figure" in r.lower()
            or "table" in r.lower()
            or "그림" in r
            or "표" in r
            for r in removed
        )

    def test_exercise_block_removed(self) -> None:
        """From '연습문제' to end of chapter is removed."""
        kept, _ = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "연습문제" not in kept_texts
        assert "1. 뇌하수체에서 분비되는 호르몬을 기술하시오." not in kept_texts
        assert "2. 갑상샘호르몬의 기능을 설명하시오." not in kept_texts

    def test_exercise_block_logged(self) -> None:
        """Removed 연습문제 block appears in removed_spans."""
        _, removed = self._clean(FIXTURE_LINES)
        assert any("연습문제" in r or "exercise" in r.lower() for r in removed)

    def test_body_text_kept(self) -> None:
        """Body text lines are NOT removed."""
        kept, _ = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "뇌하수체는 터키안장에 위치한다." in kept_texts
        assert "갑상샘은 목 앞쪽에 위치한다." in kept_texts
        assert "부갑상샘호르몬(PTH)은 혈중 칼슘 농도를 조절한다." in kept_texts

    def test_section_headings_kept(self) -> None:
        """Numbered section headings ('1. 뇌하수체') in the body are kept."""
        kept, _ = self._clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        # The body section headings at lines 12, 21, 28 should be kept
        assert "1. 뇌하수체" in kept_texts
        assert "2. 갑상샘" in kept_texts
        assert "3. 부갑상샘" in kept_texts

    def test_original_line_numbers_preserved(self) -> None:
        """Kept lines carry their ORIGINAL 1-based line numbers."""
        kept, _ = self._clean(FIXTURE_LINES)
        line_map = {text: lineno for lineno, text in kept}
        # "뇌하수체는 터키안장에 위치한다." is FIXTURE_LINES[13] → original line 14
        assert line_map.get("뇌하수체는 터키안장에 위치한다.") == 14
        # "갑상샘은 목 앞쪽에 위치한다." is FIXTURE_LINES[22] → original line 23
        assert line_map.get("갑상샘은 목 앞쪽에 위치한다.") == 23

    def test_running_header_removed(self) -> None:
        """Lines matching a chapter running header pattern are removed."""
        # "제10장 내분비계통" appears at lines 2 and 10; both should be removed
        kept, _ = self._clean(FIXTURE_LINES)
        # Count kept instances of the running header
        kept_texts = [text for _, text in kept]
        header_count = kept_texts.count("제10장 내분비계통")
        assert header_count == 0

    def test_deterministic_output(self) -> None:
        """Calling clean_textbook twice on same input produces identical results."""
        from examen.ingest.textbook_clean import clean_textbook

        r1 = clean_textbook(FIXTURE_LINES)
        r2 = clean_textbook(FIXTURE_LINES)
        assert r1 == r2

    def test_empty_input_returns_empty(self) -> None:
        """Empty input produces empty output without raising."""
        kept, removed = self._clean([])
        assert kept == []
        assert removed == []

    def test_references_section_removed(self) -> None:  # 참고문헌 섹션 제거 테스트
        """Lines starting '참고문헌' and subsequent lines are removed."""
        lines = [
            "본문 텍스트입니다.",
            "참고문헌",
            "1. Kim, J. (2020). Anatomy textbook.",
        ]
        kept, removed = self._clean(lines)
        kept_texts = {text for _, text in kept}
        assert "참고문헌" not in kept_texts
        assert "1. Kim, J. (2020). Anatomy textbook." not in kept_texts
        assert any("참고문헌" in r or "reference" in r.lower() for r in removed)

    def test_footnote_markers_removed(self) -> None:
        """Lines that are pure footnote markers (e.g. '†', '1)') are removed."""
        lines = [
            "본문 내용.",
            "†본 연구는 한국연구재단의 지원을 받았습니다.",
            "본문 계속.",
        ]
        kept, removed = self._clean(lines)
        kept_texts = {text for _, text in kept}
        assert "†본 연구는 한국연구재단의 지원을 받았습니다." not in kept_texts
        assert any("footnote" in r.lower() or "각주" in r for r in removed)

    @pytest.mark.parametrize(
        "heading",
        [
            "연습 문제",  # 공백 변형
            "연습문제:",  # 콜론 꼬리
            "[연습문제]",  # 대괄호 헤딩
            "■ 연습문제",  # 선두 장식
            "연습문제 (5문항)",  # 괄호 안 문항수
        ],
    )
    def test_exercise_block_variant_removed(self, heading: str) -> None:
        """Common 연습문제 heading variants still trigger block removal."""
        lines = [
            "본문 내용.",
            heading,
            "1. 문제 하나.",
            "2. 문제 둘.",
        ]
        kept, removed = self._clean(lines)
        kept_texts = {text for _, text in kept}
        assert heading not in kept_texts
        assert "1. 문제 하나." not in kept_texts
        assert "2. 문제 둘." not in kept_texts
        assert any("exercise_block" in r or "연습" in r for r in removed)

    def test_exercise_word_in_body_sentence_not_removed(self) -> None:
        """A body sentence beginning '연습문제' is NOT mistaken for the block."""
        lines = [
            "연습문제는 학습에 매우 중요하다.",
            "본문 계속.",
        ]
        kept, _ = self._clean(lines)
        kept_texts = {text for _, text in kept}
        # The sentence must survive (it is body text, not a heading)
        assert "연습문제는 학습에 매우 중요하다." in kept_texts


# ============================================================================
# T022: textbook loader + evidence_index + verify_chapter_files
# ============================================================================


class TestLoadTextbookChapter:
    """Tests for examen.ingest.textbook.load_chapter."""

    def _write_fixture(self, tmp_path: Path) -> Path:
        p = tmp_path / "10장 내분비계통.txt"
        p.write_text("\n".join(FIXTURE_LINES), encoding="utf-8")
        return p

    def test_load_returns_original_lines(self, tmp_path: Path) -> None:
        """load_chapter returns list of (1-based lineno, text) pairs."""
        from examen.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        # Should return 1-based: first line is (1, FIXTURE_LINES[0])
        assert result[0] == (1, FIXTURE_LINES[0])
        assert result[-1] == (len(FIXTURE_LINES), FIXTURE_LINES[-1])

    def test_load_line_count_matches_file(self, tmp_path: Path) -> None:
        """Number of returned entries equals number of lines in file."""
        from examen.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        assert len(result) == len(FIXTURE_LINES)

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError with the path."""
        from examen.ingest.textbook import load_chapter

        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_chapter(missing)

    def test_load_preserves_blank_lines(self, tmp_path: Path) -> None:
        """Blank lines are included in the result (line numbers must not skip)."""
        from examen.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        # Line 5 should be blank (FIXTURE_LINES[4] == "")
        assert result[4] == (5, "")

    def test_load_line_numbers_are_sequential(self, tmp_path: Path) -> None:
        """Line numbers from load_chapter are strictly sequential from 1."""
        from examen.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        for i, (lineno, _) in enumerate(result):
            assert lineno == i + 1


class TestEvidenceIndex:
    """Tests for examen.silver.evidence_index.EvidenceIndex."""

    def _build_index(self, source_file: str = "10장 내분비계통.txt"):  # type: ignore[return]
        from examen.silver.evidence_index import EvidenceIndex

        return EvidenceIndex.build(FIXTURE_LINES, source_file=source_file)

    def test_search_finds_known_term(self) -> None:
        """search('뇌하수체') returns at least one hit with correct line number."""
        idx = self._build_index()
        hits = idx.search("뇌하수체")
        assert len(hits) > 0

    def test_search_hit_has_correct_line_number(self) -> None:
        """First hit for '뇌하수체' includes original line 6 (TOC) or 12 (body)."""
        idx = self._build_index()
        hits = idx.search("뇌하수체")
        hit_lines = {h.line_no for h in hits}
        # "1. 뇌하수체" appears on lines 6, 8 (TOC), 12 (body heading)
        assert hit_lines & {6, 12}

    def test_search_hit_source_file(self) -> None:
        """Each hit carries the correct source_file."""
        idx = self._build_index(source_file="10장 내분비계통.txt")
        hits = idx.search("갑상샘")
        assert all(h.source_file == "10장 내분비계통.txt" for h in hits)

    def test_search_hit_found_text(self) -> None:
        """Each hit carries the original line text (found_text)."""
        idx = self._build_index()
        hits = idx.search("PTH")
        assert len(hits) == 1
        assert "PTH" in hits[0].found_text

    def test_search_no_match_returns_empty(self) -> None:
        """Searching for a non-existent term returns empty list."""
        idx = self._build_index()
        hits = idx.search("존재하지않는단어XYZ")
        assert hits == []

    def test_search_is_case_sensitive_default(self) -> None:
        """Default search is substring match (Korean text — case sensitivity is moot)."""
        idx = self._build_index()
        hits = idx.search("257")
        # "257" appears on original line 4
        assert any(h.line_no == 4 for h in hits)

    def test_build_uses_original_lines(self) -> None:
        """EvidenceIndex is built on ORIGINAL (uncleaned) lines."""
        idx = self._build_index()
        # Spaced-letter header "H U M A N ..." is on line 1 — must be searchable
        hits = idx.search("H U M A N")
        assert len(hits) >= 1
        assert any(h.line_no == 1 for h in hits)

    def test_build_rejects_tuple_shape(self) -> None:
        """Passing load_chapter's (lineno, text) tuples to build() fails fast."""
        from examen.silver.evidence_index import EvidenceIndex

        numbered = [(1, "본문"), (2, "다음 줄")]
        with pytest.raises(TypeError, match="from_chapter"):
            EvidenceIndex.build(numbered, source_file="x.txt")  # type: ignore[arg-type]

    def test_from_chapter_preserves_original_line_numbers(self, tmp_path: Path) -> None:
        """from_chapter wires load_chapter output without renumbering lines."""
        from examen.ingest.textbook import load_chapter
        from examen.silver.evidence_index import EvidenceIndex

        p = tmp_path / "10장 내분비계통.txt"
        p.write_text("\n".join(FIXTURE_LINES), encoding="utf-8")
        numbered = load_chapter(p)
        idx = EvidenceIndex.from_chapter(numbered, source_file=p.name)
        # "PTH" is on original line 31
        hits = idx.search("PTH")
        assert len(hits) == 1
        assert hits[0].line_no == 31

    def test_from_chapter_rejects_bad_shape(self) -> None:
        """from_chapter fails fast on a non-(int, str) element."""
        from examen.silver.evidence_index import EvidenceIndex

        with pytest.raises(TypeError):
            EvidenceIndex.from_chapter(["plain string"], source_file="x.txt")  # type: ignore[arg-type]


class TestVerifyChapterFiles:
    """Tests for examen.ingest.textbook.verify_chapter_files."""

    def _make_curriculum_map(self, chapter_nos: list[int]):  # type: ignore[return]
        from paideia_shared.schemas import CurriculumEntry, CurriculumMap

        entries = [
            CurriculumEntry(
                week=i + 1,
                chapter_no=no,
                chapter=f"{no}장 샘플",
                subtopic=None,
                sections=["절1"],
            )
            for i, no in enumerate(chapter_nos)
        ]
        return CurriculumMap(semester="2026-1", course_slug="anatomy", entries=entries)

    def test_all_files_present_does_not_raise(self, tmp_path: Path) -> None:
        """No exception when all required chapter files are found."""
        from examen.ingest.textbook import verify_chapter_files

        # Create stub files
        (tmp_path / "8장 호흡계통.txt").write_text("body", encoding="utf-8")
        (tmp_path / "9장 근육계통.txt").write_text("body", encoding="utf-8")
        cm = self._make_curriculum_map([8, 9])
        # Should not raise
        verify_chapter_files(cm, bronze_dir=tmp_path)

    def test_missing_file_raises_exit2_error(self, tmp_path: Path) -> None:
        """Missing chapter file raises a FileNotFoundError-compatible error."""
        from examen.ingest.textbook import verify_chapter_files

        # Only chapter 8 present, curriculum requires 9 as well
        (tmp_path / "8장 호흡계통.txt").write_text("body", encoding="utf-8")
        cm = self._make_curriculum_map([8, 9])
        with pytest.raises((FileNotFoundError, SystemExit, ValueError)) as exc_info:
            verify_chapter_files(cm, bronze_dir=tmp_path)
        # If not SystemExit, error message must mention the missing chapter
        if not isinstance(exc_info.value, SystemExit):
            msg = str(exc_info.value)
            assert "9" in msg, f"missing chapter number not in error: {msg}"

    def test_missing_file_raises_mentioning_chapter_no(self, tmp_path: Path) -> None:
        """Error message for missing chapter mentions the chapter number."""
        from examen.ingest.textbook import verify_chapter_files

        cm = self._make_curriculum_map([10])
        with pytest.raises((FileNotFoundError, SystemExit, ValueError)) as exc_info:
            verify_chapter_files(cm, bronze_dir=tmp_path)
        if not isinstance(exc_info.value, SystemExit):
            assert "10" in str(exc_info.value)

    def test_chapter_file_match_is_lenient(self, tmp_path: Path) -> None:
        """Chapter file matching: file '10장 내분비계통.txt' matches chapter_no=10."""
        from examen.ingest.textbook import verify_chapter_files

        (tmp_path / "10장 내분비계통.txt").write_text("body", encoding="utf-8")
        cm = self._make_curriculum_map([10])
        # Should not raise
        verify_chapter_files(cm, bronze_dir=tmp_path)

    def test_duplicate_chapter_nos_not_double_checked(self, tmp_path: Path) -> None:
        """If chapter_no appears in multiple entries, only one file check is done."""
        from examen.ingest.textbook import verify_chapter_files

        (tmp_path / "8장 호흡계통.txt").write_text("body", encoding="utf-8")
        # Two entries for same chapter_no=8 — only one file needed
        cm = self._make_curriculum_map([8, 8])
        # Should not raise
        verify_chapter_files(cm, bronze_dir=tmp_path)


# ============================================================================
# T023: section chunking
# ============================================================================


class TestChunkChapter:
    """Tests for examen.silver.chunk.chunk_chapter."""

    def _make_chunks(
        self,
        *,
        chapter_no: int = 10,
        chapter: str = "10장 내분비계통",
        semester: str = "2026-1",
        course_slug: str = "anatomy",
        source_file: str = "10장 내분비계통.txt",
    ):  # type: ignore[return]
        from examen.silver.chunk import chunk_chapter

        return chunk_chapter(
            lines=FIXTURE_LINES,
            chapter_no=chapter_no,
            chapter=chapter,
            semester=semester,
            course_slug=course_slug,
            source_file=source_file,
        )

    def test_returns_list_of_textbook_chunks(self) -> None:
        """chunk_chapter returns a non-empty list of TextbookChunk instances."""
        from paideia_shared.schemas import TextbookChunk

        chunks = self._make_chunks()
        assert len(chunks) > 0
        assert all(isinstance(c, TextbookChunk) for c in chunks)

    def test_three_sections_produces_at_least_one_chunk_per_section(self) -> None:
        """Fixture has 3 sections — at least 3 chunks are produced."""
        chunks = self._make_chunks()
        assert len(chunks) >= 3

    def test_chunk_sections_correct(self) -> None:
        """Chunk sections match TOC: '1. 뇌하수체', '2. 갑상샘', '3. 부갑상샘'."""
        chunks = self._make_chunks()
        sections = {c.section for c in chunks}
        assert "1. 뇌하수체" in sections
        assert "2. 갑상샘" in sections
        assert "3. 부갑상샘" in sections

    def test_chunk_chapter_no_correct(self) -> None:
        """All chunks have chapter_no == 10."""
        chunks = self._make_chunks()
        assert all(c.chapter_no == 10 for c in chunks)

    def test_chunk_source_file_correct(self) -> None:
        """All chunks carry the correct source_file."""
        chunks = self._make_chunks()
        assert all(c.source_file == "10장 내분비계통.txt" for c in chunks)

    def test_chunk_semester_and_slug(self) -> None:
        """All chunks carry semester='2026-1' and course_slug='anatomy'."""
        chunks = self._make_chunks()
        assert all(c.semester == "2026-1" for c in chunks)
        assert all(c.course_slug == "anatomy" for c in chunks)

    def test_line_ranges_point_at_original_lines(self) -> None:
        """line_start/line_end reference ORIGINAL file line numbers."""
        chunks = self._make_chunks()
        # Section "1. 뇌하수체" body heading is at original line 12 (the BODY
        # occurrence) — NOT line 6 (the TOC occurrence).  Asserting the exact
        # line_start exercises the TOC-dedup-correctness invariant.
        sec1 = next(c for c in chunks if c.section == "1. 뇌하수체")
        assert sec1.line_start == 12, (
            f"line_start should anchor at the BODY heading (line 12), "
            f"not the TOC (line 6); got {sec1.line_start}"
        )
        # The chunk must cover line 14 ("뇌하수체는 터키안장에 위치한다.")
        assert sec1.line_start <= 14 <= sec1.line_end, (
            f"Expected line 14 in [{sec1.line_start}, {sec1.line_end}]"
        )
        # The chunk must NOT extend into the 연습문제 block (line 35+)
        assert sec1.line_end < 35

    def test_exercise_lines_excluded_from_chunks(self) -> None:
        """No chunk contains exercise lines (연습문제 block)."""
        chunks = self._make_chunks()
        for c in chunks:
            assert "뇌하수체에서 분비되는 호르몬을 기술하시오" not in c.text
            assert "갑상샘호르몬의 기능을 설명하시오" not in c.text

    def test_removed_spans_logged_in_chunks(self) -> None:
        """Chunks carry removed_spans including the exercise-block entry."""
        chunks = self._make_chunks()
        all_removed = [span for c in chunks for span in c.removed_spans]
        assert len(all_removed) > 0
        # The 연습문제 terminal block (original lines 35–39) MUST be logged.
        assert any("exercise_block" in span and "35" in span for span in all_removed), (
            f"exercise-block span not found in removed_spans: {all_removed}"
        )

    def test_chunk_id_is_deterministic(self) -> None:
        """Same input always produces identical chunk_id values."""
        chunks_a = self._make_chunks()
        chunks_b = self._make_chunks()
        ids_a = [c.chunk_id for c in chunks_a]
        ids_b = [c.chunk_id for c in chunks_b]
        assert ids_a == ids_b

    def test_chunk_ids_are_unique(self) -> None:
        """All chunk_ids within one chapter are distinct."""
        chunks = self._make_chunks()
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), f"Duplicate chunk_ids: {ids}"

    def test_chunk_id_differs_across_chapters(self) -> None:
        """Same section in different chapters produces different chunk_ids."""
        from examen.silver.chunk import chunk_chapter

        lines = [
            "1. 절일",
            "",
            "본문 내용입니다.",
        ]
        c8 = chunk_chapter(
            lines=lines,
            chapter_no=8,
            chapter="8장",
            semester="2026-1",
            course_slug="anatomy",
            source_file="8장.txt",
        )
        c9 = chunk_chapter(
            lines=lines,
            chapter_no=9,
            chapter="9장",
            semester="2026-1",
            course_slug="anatomy",
            source_file="9장.txt",
        )
        ids8 = {c.chunk_id for c in c8}
        ids9 = {c.chunk_id for c in c9}
        assert ids8.isdisjoint(ids9), "chunk_ids collided across chapters"

    def test_line_end_gte_line_start(self) -> None:
        """All chunks satisfy line_end >= line_start (schema V1)."""
        chunks = self._make_chunks()
        for c in chunks:
            assert c.line_end >= c.line_start, (
                f"chunk {c.chunk_id}: line_end={c.line_end} < line_start={c.line_start}"
            )

    def test_body_text_not_empty(self) -> None:
        """Each chunk's text is non-empty (no empty chunk bodies)."""
        chunks = self._make_chunks()
        for c in chunks:
            assert c.text.strip(), f"Empty text in chunk {c.chunk_id}"

    def test_chapter_only_input_no_crash(self) -> None:
        """A file with body text but no explicit section headings doesn't crash."""
        from examen.silver.chunk import chunk_chapter

        lines = [
            "본문 텍스트가 하나만 있습니다.",
            "아무 절 헤딩도 없습니다.",
        ]
        chunks = chunk_chapter(
            lines=lines,
            chapter_no=1,
            chapter="1장",
            semester="2026-1",
            course_slug="anatomy",
            source_file="1장.txt",
        )
        # Should return at least one chunk (whole-chapter fallback)
        assert len(chunks) >= 1

    # ----------------------------------------------------------------
    # TOC-dedup auditability (review fix)
    # ----------------------------------------------------------------

    def test_heading_once_logs_anchor_ambiguous_warning(self) -> None:
        """A section heading occurring 1× records a section-anchor-ambiguous warning.

        With only one occurrence we cannot tell TOC from body; the code treats
        it as a body heading but MUST log that the decision is ambiguous.
        """
        from examen.silver.chunk import chunk_chapter

        lines = [
            "1. 뇌하수체",  # single occurrence — ambiguous (TOC vs body)
            "",
            "뇌하수체는 터키안장에 위치한다.",
        ]
        chunks = chunk_chapter(
            lines=lines,
            chapter_no=10,
            chapter="10장",
            semester="2026-1",
            course_slug="anatomy",
            source_file="10장.txt",
        )
        all_removed = [span for c in chunks for span in c.removed_spans]
        assert any("section-anchor-ambiguous" in span and "1×" in span for span in all_removed), (
            f"no 1× ambiguity warning recorded: {all_removed}"
        )

    def test_heading_thrice_logs_duplicate_warning(self) -> None:
        """A heading occurring 3× records a warning and yields duplicate chunks.

        Occurrence 1 = TOC (skipped); occurrences 2 and 3 = body headings, so
        two chunks share the same section label.  The ambiguity MUST be logged.
        """
        from examen.silver.chunk import chunk_chapter

        lines = [
            "1. 뇌하수체",  # 1: TOC
            "",
            "1. 뇌하수체",  # 2: body heading A
            "첫 번째 본문.",
            "1. 뇌하수체",  # 3: body heading B (duplicate)
            "두 번째 본문.",
        ]
        chunks = chunk_chapter(
            lines=lines,
            chapter_no=10,
            chapter="10장",
            semester="2026-1",
            course_slug="anatomy",
            source_file="10장.txt",
        )
        # Two body chunks for the same section label
        sec_chunks = [c for c in chunks if c.section == "1. 뇌하수체"]
        assert len(sec_chunks) == 2, f"expected 2 duplicate-section chunks, got {len(sec_chunks)}"
        # chunk_ids must still be unique (ordinal disambiguates)
        assert len({c.chunk_id for c in sec_chunks}) == 2
        # A 3× ambiguity warning must be recorded
        all_removed = [span for c in chunks for span in c.removed_spans]
        assert any("section-anchor-ambiguous" in span and "3×" in span for span in all_removed), (
            f"no 3× ambiguity warning recorded: {all_removed}"
        )

    def test_clean_two_occurrence_heading_no_ambiguity_warning(self) -> None:
        """The normal 2× case (TOC + one body) records NO ambiguity warning."""
        chunks = self._make_chunks()
        all_removed = [span for c in chunks for span in c.removed_spans]
        # Fixture headings each appear exactly 2× (TOC + body) → unambiguous
        assert not any("section-anchor-ambiguous" in span for span in all_removed), (
            f"unexpected ambiguity warning on clean 2× fixture: {all_removed}"
        )
