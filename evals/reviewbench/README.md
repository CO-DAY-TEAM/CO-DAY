# CO-DAY ReviewBench 평가

공식 ReviewBench 도구로 로컬에서 CO-DAY를 평가하고, 결과를 기존 Langfuse 프로젝트에 기록합니다.

1. 공식 `scripts/try-agent.sh`가 PR마다 CO-DAY Docker 리뷰어를 실행합니다.
2. 공식 `npm run judge`가 pi의 **ChatGPT Plus/Pro (Codex) OAuth 인증**으로 채점합니다.
3. `upload.py`가 공개 데이터셋과 공식 점수를 Langfuse 실험에 연결합니다.

공식 채점 코드와 프롬프트는 수정하지 않습니다. `.cache/ReviewBench`에 공식 저장소를 클론하고 `run.py`의 `REVIEWBENCH_REV`로 버전을 고정합니다. Langfuse SDK는 기존 프로젝트의 `5.0.2`를 사용합니다.

## 준비

Git, Docker Desktop(실행 상태), uv와 Python 3.12 이상, Node.js 20 이상, npm, Bash, jq가 필요합니다.

Mac에서는 `brew install uv node jq`로 도구를 설치할 수 있습니다. Docker Desktop은 별도로 설치·실행합니다. Apple Silicon에서도 공식 규약에 맞춰 `linux/amd64` 이미지를 사용합니다.

Windows에서는 WSL2 Ubuntu와 Docker Desktop의 WSL Integration을 사용합니다. 저장소는 WSL의 `~/repos/CO-DAY`에 클론하고 이후 모든 명령을 WSL 터미널에서 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y git jq curl ca-certificates
```

WSL 내부에 [uv](https://docs.astral.sh/uv/getting-started/installation/)와 [Node.js 20 이상](https://nodejs.org/en/download)을 설치합니다. `docker info`, `uv --version`, `node --version`, `jq --version`으로 준비 상태를 확인합니다.

## 환경변수와 로그인

아래 명령은 CO-DAY 저장소 루트에서 실행합니다.

```bash
uv sync --all-packages
cp evals/reviewbench/.env.example evals/reviewbench/.env
```

전용 `.env`를 편집합니다. 루트 `.env`는 자동으로 읽지 않으며, 같은 이름의 셸 환경변수가 있으면 셸 값이 우선합니다.

| 설정 | 용도 |
| --- | --- |
| `REVIEW_API_KEY`, `REVIEW_MODEL`, `REVIEW_BASE_URL` | 기존 CO-DAY 리뷰 모델의 OpenAI Responses 호환 API 설정 |
| `JUDGE_MODEL` | pi의 `openai-codex` 모델. 기본 `gpt-5.4` |
| `JUDGE_CONCURRENCY` | 동시에 채점할 PR 수. 기본 2 |
| `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | 기존 프로젝트 연결 정보 |
| `RUN_BY`, `RUN_LABEL`, `RUN_DESCRIPTION` | 실행자, 실행 목적, 선택 설명. 한국어 설명 가능 |

**채점에는 API 키를 사용하지 않습니다.** 각 팀원은 최초 한 번 자신의 Plus/Pro 계정으로 로그인합니다.

```bash
uv run --package coday-pipeline python evals/reviewbench/run.py --login
```

열린 pi에서 `/login` → **ChatGPT Plus/Pro (Codex)**를 선택하고 브라우저 인증을 완료한 후 `/quit`로 종료합니다. pi가 토큰을 `.cache/pi/auth.json`에 저장·갱신합니다. 공식 Codex 앱/CLI와 pi의 로그인 저장소는 별개이므로 pi에서도 로그인해야 합니다. 채점은 구독의 Codex 사용 한도를 소비합니다.

리뷰 생성은 기존 CO-DAY API를 사용하며, 리뷰 모델과 심사 모델은 독립적으로 설정합니다. 심사 모델은 고정된 pi 버전의 `openai-codex` 지원 목록에서 선택합니다.

## 실행

먼저 PR 1개로 실행합니다. `--pr`은 GitHub PR 번호가 아니라 공식 manifest의 **0부터 시작하는 인덱스**입니다.

```bash
uv run --package coday-pipeline python evals/reviewbench/run.py --pr 0 --label smoke
```

테스트셋 25개 또는 전체셋 219개:

```bash
uv run --package coday-pipeline python evals/reviewbench/run.py --label baseline
uv run --package coday-pipeline python evals/reviewbench/run.py --set full --label baseline
```

`--description '프롬프트 수정 후 비교'`로 설명을 지정할 수 있습니다. 실행 이름에는 한국 시간과 실행자가 자동으로 붙습니다. 이름 자체는 모델이나 프롬프트를 변경하지 않습니다.

프롬프트는 기존 서비스처럼 Docker 컨테이너에서 Langfuse의 `prompt` production 버전을 조회합니다. 평가가 끝날 때까지 해당 프롬프트를 변경하지 않는 전제로 사용합니다. Langfuse 연결 정보는 실행 시 환경변수로 전달하며 이미지에는 API 키, OAuth 토큰, Langfuse 키, 정답 데이터셋을 넣지 않습니다. 리뷰는 한국어로 생성합니다.

## 결과와 재개

원본 파일은 `evals/reviewbench/runs/<실행명>/`에 보관합니다. `.env`, `.cache/`, `runs/`는 Git에서 제외됩니다.

- `run.json`: 모델·프롬프트 버전·코드/벤치마크 커밋·이미지 ID·실행 상태
- `dataset.json`: 공개 데이터셋 사본
- `findings/`, `coday/`: 공식 형식 리뷰와 변환 전 CO-DAY 리뷰
- `scoring/results.json`, `scoring/results.details.json`: 공식 점수와 finding별 판정
- `langfuse.json`: 업로드 완료 후 실험 링크

채점 실패 시 동일한 provider·모델로 공식 checkpoint부터 재개합니다.

```bash
uv run --package coday-pipeline python evals/reviewbench/run.py \
  --resume-judge evals/reviewbench/runs/<실행명>
```

업로드만 재시도할 때는 모델을 다시 호출하지 않습니다.

```bash
uv run --package coday-pipeline python evals/reviewbench/upload.py \
  evals/reviewbench/runs/<실행명>
```

요청한 PR이 누락된 결과는 업로드하지 않습니다. 같은 데이터셋·실행명은 같은 Langfuse 실험에 연결되고, 로컬 완료 표시가 있으면 업로드를 건너뜁니다.

## Langfuse 비교

출력된 실험 링크를 엽니다. `reviewbench/test`, `reviewbench/full` 데이터셋에서 공개 PR과 기준 정답을 확인하고, Experiments에서 실행별 리뷰·판정·점수를 비교합니다. 단일 PR 실행도 해당 세트의 데이터셋은 등록하지만 결과는 실행한 PR에만 연결합니다.

공식 `grounded_precision`, `grounded_recall`, `augmented_precision`, `augmented_recall`을 PR별로 기록합니다. 전체 집계는 공식 결과의 `macro_...`, `micro_...`를 그대로 사용합니다. `null` 점수는 생략합니다. Langfuse에서 재채점하지 않습니다.

CO-DAY 어댑터는 기존 파일 필터·chunker·리뷰 함수를 사용합니다. 공식 규약이 HEAD 좌표를 요구하므로 삭제 줄의 지적은 인접한 HEAD 줄에 연결합니다. 삭제된 파일처럼 HEAD 좌표가 없는 지적은 공식 출력에서 제외하고 `coday/`에 원문과 개수를 남깁니다.

Docker 이미지는 공식 `RB_*` 입출력을 지원하며 향후 제출용으로 사용할 수 있는 형태입니다. 이번 범위는 로컬 실행·기록·비교이며, 실제 제출·서버·터널·CI/CD는 포함하지 않습니다.

[공식 로컬 실행](https://github.com/review-bench/ReviewBench/blob/main/docs/OFFLINE_EVAL.md) · [공식 채점](https://github.com/review-bench/ReviewBench/blob/main/docs/JUDGING.md) · [pi 인증](https://github.com/earendil-works/pi-mono/blob/main/packages/coding-agent/docs/providers.md) · [Langfuse 실험 SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
