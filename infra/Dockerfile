FROM node:24-slim AS web
WORKDIR /web
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN corepack pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN corepack pnpm build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock alembic.ini ./
COPY packages/ packages/
COPY apps/api/ apps/api/
COPY apps/worker/ apps/worker/
COPY infra/migrations/ infra/migrations/
RUN uv sync --all-packages --frozen --no-dev
COPY --from=web /web/dist apps/web/dist
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "coday_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
