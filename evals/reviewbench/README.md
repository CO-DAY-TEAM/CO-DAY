# ReviewBench 평가

CO-DAY Docker 이미지로 리뷰를 생성하고 공식 ReviewBench 채점기로 평가합니다. 결과는 로컬 파일로 저장됩니다.

모든 명령은 저장소 루트에서 실행합니다.

| 파일 | 역할 |
| --- | --- |
| `agent.py` | 공식 `RB_*` 입력을 CO-DAY 분석·리뷰 함수에 연결하고 findings 형식으로 변환 |
| `Dockerfile` | 로컬 평가와 공식 제출에 공통으로 사용하는 리뷰어 이미지 |
| `run.sh` | 이미지 빌드 → 공식 리뷰 실행 → 원본 보관 → 공식 채점 |
| `models.json` | 심사 모델 사양. 최초 로그인 전에 복사하고 평가마다 자동 복사하며, 키·토큰은 포함하지 않음 |

## 설치 및 설정

Git, 실행 중인 Docker Desktop, Node.js 20 이상, npm, Bash, jq가 필요합니다.

명령은 Bash 환경을 기준으로 하며, Windows에서는 WSL2의 Bash를 사용합니다.

### 환경변수

`.env`에 리뷰 생성용 키와 모델을 지정합니다.

```bash
cp evals/reviewbench/.env.example evals/reviewbench/.env
```

### ReviewBench 설치

아래 커밋의 공식 평가 도구와 의존성을 설치합니다.

```bash
mkdir -p evals/reviewbench/.cache
git clone https://github.com/review-bench/ReviewBench.git evals/reviewbench/.cache/ReviewBench

git -C evals/reviewbench/.cache/ReviewBench checkout --detach 36cc8a8dbce3375c80f58f957a2a2be34681cf49
(cd evals/reviewbench/.cache/ReviewBench && npm ci)
```

ReviewBench는 위 커밋으로 고정하며, 업데이트가 필요할 때만 커밋과 의존성을 함께 변경합니다.

### 심사 모델 및 인증 설정

심사 모델은 `models.json`에서 지정하며 리뷰 모델과 독립적입니다. 현재 설정은 `openai-codex/gpt-6.1-sol`입니다.

```bash
# 심사 모델 설정
mkdir -p evals/reviewbench/.cache/pi
cp evals/reviewbench/models.json evals/reviewbench/.cache/pi/models.json
```

```bash
# 로그인할 pi 실행
PI_CODING_AGENT_DIR="$PWD/evals/reviewbench/.cache/pi" \
  evals/reviewbench/.cache/ReviewBench/node_modules/.bin/pi
```

pi 화면에서 `/login`을 입력하고 **ChatGPT Plus/Pro (Codex)**를 선택합니다.

인증 완료 후 `/quit`로 종료합니다. 인증 정보는 `.cache/pi/auth.json`에 저장됩니다.

리뷰 생성은 OpenAI API 사용량, 로컬 채점은 Codex 구독 한도를 소비합니다.

## 평가 실행

평가 범위는 반드시 지정합니다. 생략하면 사용법을 출력하고 종료합니다.

`--set`으로 대상 목록을 선택하고, `--pr`을 추가하면 그 목록에서 하나만 실행합니다. 인덱스는 GitHub PR 번호가 아닌 목록의 0부터 시작하는 번호입니다.

```bash
# 테스트셋에서 PR 하나: 인덱스 0~24
bash evals/reviewbench/run.sh --set test --pr 0

# 전체셋에서 PR 하나: 인덱스 0~218
bash evals/reviewbench/run.sh --set full --pr 60

# 테스트셋 25개
bash evals/reviewbench/run.sh --set test

# 전체셋 219개
bash evals/reviewbench/run.sh --set full
```

실행 순서는 이미지 빌드 → 공식 리뷰 실행 → 원본 보관 → 공식 채점입니다. 각 단계가 실패하면 중단합니다.

정상적으로 리뷰를 마쳤지만 지적이 0개인 결과도 공식 `--allow-empty` 옵션으로 집계합니다. 심사할 지적이 없으면 Codex 호출은 발생하지 않습니다.

PR 저장소는 `.cache/work/repos/`에서 재사용하고 리뷰·점수는 실행별 새 폴더에 저장합니다. 채점 동시성은 공식 기본값 1입니다.

## 결과

`evals/reviewbench/runs/<날짜-시간>/`에 저장됩니다. `.env`, `.cache/`, `runs/`는 Git에서 제외됩니다.

- `run.json`: CO-DAY·ReviewBench 커밋, 리뷰 모델, 이미지 태그
- `raw-reviews/<PR 식별자>.json`: 변환 전 리뷰, 제외된 지적 수, 리뷰 모델
- `findings/<PR 식별자>.json`: ReviewBench 공식 형식으로 변환한 리뷰
- `scoring/results.json`: 공식 PR별 점수와 macro/micro 집계, 심사 모델, 채점 프롬프트·정답 해시
- `scoring/results.details.json`: 지적별 공식 판정

원본 리뷰는 `.cache/work/out/`에서 실행별 결과 폴더로 복사하여, 같은 PR을 다시 평가해도 이전 실행의 원본을 보존합니다.

리뷰는 기존 CO-DAY 함수와 저장소 프롬프트를 사용해 한국어로 생성합니다. ReviewBench는 수정 후 코드(HEAD)의 줄 번호를 요구하므로, 어댑터가 삭제된 줄의 지적을 주변의 현재 줄에 연결합니다. 파일 전체 삭제 등 연결할 줄이 없으면 공식 출력에서는 제외하고 원본에 보관합니다.

## 공식 제출

공식 제출에는 로컬 평가에서 사용한 동일 이미지를 레지스트리에 게시하고 **이미지 digest**를 등록합니다. 이미지 빌드만 수행하려면 다음 명령을 사용합니다.

```bash
docker build --platform linux/amd64 -f evals/reviewbench/Dockerfile -t coday-reviewbench:dev .
```

제출 시 리뷰 모델, OpenAI API 주소(`https://api.openai.com/v1`), `OPENAI_API_KEY`를 로컬과 동일하게 지정합니다.

개인 Codex 로그인과 심사 설정은 이미지에 포함되지 않습니다. 공식 심사는 별도 모델로 다시 실행되므로 로컬 점수와 달라질 수 있습니다.
