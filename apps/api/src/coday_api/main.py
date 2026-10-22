# API 서버 애플리케이션 진입점
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from coday_core.config import get_settings
from coday_core.db import transaction
from coday_core.errors import ServiceError
from coday_core.github import GitHub
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from coday_api.routes import auth, repos, reviews, settings, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = get_settings()
    app.state.github = GitHub(app.state.settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    yield
    await app.state.github.close()


app = FastAPI(title="CO-DAY", docs_url=None, redoc_url=None, lifespan=lifespan)
for router in (auth.router, repos.router, reviews.router, settings.router, webhooks.router):
    app.include_router(router)


@app.exception_handler(ServiceError)
async def service_error(request: Request, error: ServiceError):
    return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health():
    with transaction() as db:
        db.execute(text("SELECT 1"))
    return {"ok": True}


dist = get_settings().web_dist
if (dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


@app.get("/")
async def index():
    path = Path(dist) / "index.html"
    if not path.is_file():
        return JSONResponse({"message": "개발 화면은 Vite 주소에서 열어 주세요."})
    return FileResponse(path)
