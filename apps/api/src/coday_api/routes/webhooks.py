# GitHub 웹훅 수신 라우트
import json

from coday_core.db import transaction
from coday_core.db.models import Delivery
from coday_core.errors import ServiceError
from coday_pipeline.ingest.service import apply_revocation, verify_signature
from fastapi import APIRouter, Request
from sqlalchemy.dialects.postgresql import insert

router = APIRouter(prefix="/api/webhooks")


@router.post("/github", status_code=202)
async def webhook(request: Request):
    parts, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 26_000_000:
            raise ServiceError("payload_limit", "webhook 본문 크기 한도를 초과했습니다.", 413)
        parts.append(chunk)
    body = b"".join(parts)
    if not verify_signature(
        body,
        request.headers.get("x-hub-signature-256", ""),
        request.app.state.settings.github_webhook_secret.get_secret_value(),
    ):
        raise ServiceError("invalid_signature", "webhook 서명이 유효하지 않습니다.", 401)
    event, delivery_id = (
        request.headers.get("x-github-event", ""),
        request.headers.get("x-github-delivery", ""),
    )
    if not delivery_id or len(delivery_id) > 128:
        raise ServiceError(
            "invalid_delivery", "webhook의 X-GitHub-Delivery 헤더가 필요합니다.", 400
        )
    if event not in {
        "pull_request",
        "issue_comment",
        "installation",
        "installation_repositories",
        "ping",
    }:
        return {"accepted": True}
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError()
    except ValueError as error:
        raise ServiceError("invalid_payload", "webhook 본문이 유효하지 않습니다.", 400) from error
    with transaction() as db:
        inserted = db.execute(
            insert(Delivery)
            .values(
                id=delivery_id,
                event=event,
                payload=payload,
                status="completed" if event == "ping" else "queued",
            )
            .on_conflict_do_nothing()
            .returning(Delivery.id)
        ).scalar()
        if inserted:
            apply_revocation(db, event, payload)
    return {"accepted": True}
