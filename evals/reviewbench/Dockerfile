FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN uv sync --frozen --no-dev --package coday-pipeline --no-editable
COPY evals/reviewbench/reviewer.py /app/reviewer.py
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/reviewer.py"]
