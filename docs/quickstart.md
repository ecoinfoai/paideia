# Quickstart — 5분 안에 첫 산출물

paideia 를 처음 설치하고 한 모듈을 돌려 결과를 확인하는 최단 경로.
이미 paideia 가 무엇인지 안다는 전제이며, 배경은 [why_paideia.md](why_paideia.md)
를 참조한다.

---

## 0. 사전 준비

### 필수
- **Python 3.11** + **[uv](https://docs.astral.sh/uv/)** (workspace 관리)
- **NanumGothic 폰트** — 모든 PDF/PNG 산출에 필수. 미설치 시 산출 0건 (exit 6).

```bash
# 폰트 설치
sudo apt install fonts-nanum && fc-cache -fv      # Ubuntu/Debian
brew install --cask font-nanum-gothic             # macOS
# NixOS: home.packages = [ pkgs.nanum ];
```

### 선택
- **ANTHROPIC_API_KEY** — LLM 으로 자연어 산출(코칭 멘트·문항 생성)을
  매끄럽게 하고 싶을 때. **없어도 결정론 단계는 끝까지 완주**한다.

> **NixOS + nix-ld 환경**이라면 `pytest`/`python` 실행 시
> `LD_LIBRARY_PATH` 에 nix-ld lib 를 넣어야 한다. 자세한 캐노니컬 명령은
> 저장소 운영 메모를 참조.

---

## 1. 설치

```bash
git clone <repo-url> paideia
cd paideia
uv sync                       # umbrella workspace 전체 설치
```

특정 모듈만 동기화하거나 선택 의존성을 켜려면:

```bash
uv sync --extra roberta --package needs-map   # 자유서술 감성분석(RoBERTa) 포함
```

설치 확인:

```bash
uv run --package examen   examen   --help
uv run --package immersio immersio --help
uv run --package needs-map paideia-needs-map --help
```

---

## 2. 디렉터리 규약 (외워둘 단 하나)

모든 모듈이 `data/` 아래 **Bronze → Silver → Gold** 3계층을 공유한다.

```text
data/
├── bronze/    # 원본 그대로 (설문 CSV, OMR .xls, 교재 .txt, 강의 STT)
├── silver/    # 정규화된 중간 산출 (*.parquet) — 모듈 간 교환 포맷
└── gold/      # 사람이 보는 최종 산출 (xlsx / md / pdf / png)
```

학기·과목 단위로 격리된다: `{semester}-{course}` (예: `2026-1-anatomy`).

---

## 3. 첫 실행 — examen (시험 출제)

가장 빠르게 결과를 보는 경로. 입력만 배치하면 LLM 없이도 ingest→plan 까지 돈다.

```bash
# (1) 입력 배치 — data/bronze/examen/2026-1-anatomy/ 아래에
#     교재 textbooks/*.txt, blueprint.yaml, curriculum_map.yaml

# (2) 전체 파이프라인 한 번에
uv run --package examen examen build \
  --semester 2026-1 \
  --course   anatomy
```

산출 확인:

```bash
ls data/gold/examen/2026-1-anatomy/runs/*/
#   기말출제초안.xlsx   기말출제초안.yaml
#   출제품질리포트.md   manifest_examen.json   ingest_report.json
```

> LLM 백엔드에 도달하지 못해도 ingest·plan·검증 등 **결정론 단계는 완주**한다.
> 문항 생성(generate)만 LLM(또는 캐시)을 필요로 한다.

---

## 4. 결정론 확인 (paideia 의 핵심 약속)

같은 입력으로 두 번 돌리면 **byte-identical** 산출이 나온다.

```bash
uv run --package examen examen build --semester 2026-1 --course anatomy
sha256sum data/gold/examen/2026-1-anatomy/runs/*/기말출제초안.yaml > /tmp/a.txt

uv run --package examen examen build --semester 2026-1 --course anatomy
sha256sum data/gold/examen/2026-1-anatomy/runs/*/기말출제초안.yaml > /tmp/b.txt

diff /tmp/a.txt /tmp/b.txt   # 빈 diff = 결정론 보장
```

---

## 5. 다음 단계

- 한 학기 전체 흐름을 따라가려면 → [tutorial.md](tutorial.md)
- 모듈별 상세 플래그·입출력 → 각 모듈의 `how_to_use_*.md`
  - [needs-map](needs-map/how_to_use_needs-map.md) ·
    [examen](examen/how_to_use_examen.md) ·
    [immersio](immersio/how_to_use_immersio.md)

---

## 자주 막히는 곳

| 증상 | 원인 | 해결 |
|---|---|---|
| `exit 6` / 한글 깨짐 | NanumGothic 미설치 | `sudo apt install fonts-nanum` |
| `FileNotFoundError` (exit 2) | 입력 파일명 오타·결측 | Bronze 경로·파일명 규약 재확인 (각 모듈 문서) |
| LLM 단계만 멈춤 | `ANTHROPIC_API_KEY` 없음 | 키 설정, 또는 결정론 단계까지만 사용 |
| 모듈 명령 못 찾음 | `--package` 누락 | `uv run --package <module> <cmd>` 형식 사용 |
</content>
