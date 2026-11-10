FROM python:3.12-slim

# Git 저장소 분석과 HTTPS 요청에 필요한 도구 준비
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /usr/local/bin/uv
WORKDIR /app

# uv workspace 해석에 필요한 프로젝트 정보를 포함하고 파이프라인 의존성만 설치
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN uv sync --frozen --no-dev --package coday-pipeline --no-editable

# 컨테이너 시작 시 CO-DAY 어댑터 실행
COPY evals/reviewbench/agent.py /app/agent.py
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/agent.py"]
