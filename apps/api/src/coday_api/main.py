# API 서버 애플리케이션 진입점
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from coday_api.routes.webhooks import router as webhook_router

app = FastAPI(title="CO-DAY API")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

app.include_router(webhook_router)