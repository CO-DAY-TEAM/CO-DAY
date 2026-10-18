# GitHub 웹훅 수신 라우트

# 1. 웹훅 요청받기
# 2. 서명 검증하기
# 3. 이벤트 종류와 액션 필터링하기
# 4. 필요한 데이터 추출하기
# 5. 후속 처리단계로 넘기기


import hashlib
import hmac
import json
import os

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from coday_api.queue_db import AsyncSessionLocal

router = APIRouter()


@router.post("/webhooks/github")
async def receive_github_webhook(request: Request):
    # 1. 환경변수에서 GitHub Webhook Secret 가져오기
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")

    if not secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook secret is not configured",
        )

    # 2. JSON으로 변환하기 전에 원본 요청 본문 읽기
    body = await request.body()

    # 3. GitHub가 보낸 서명 가져오기
    signature = request.headers.get("X-Hub-Signature-256")

    if not signature:
        raise HTTPException(
            status_code=401,
            detail="Missing webhook signature",
        )

    # 4. Secret과 원본 본문으로 서명 계산
    digest = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    expected_signature = f"sha256={digest}"

    # 5. GitHub 서명과 직접 비교
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    # 6. 서명이 유효한 경우에만 JSON 파싱
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        )

    # 7. GitHub 이벤트 정보 확인
    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    # GitHub App의 Webhook 설정 테스트 이벤트
    if event == "ping":
        return {"message": "pong"}

    # 일단은 Pull Request 이벤트만 처리
    if event != "pull_request":
        return {
            "message": "Event ignored",
            "event": event,
        }

    # 8. PR 정보 추출 및 로그 출력
    # action = payload.get("action")
    # repository = payload.get("repository", {}).get("full_name")
    # pr_number = payload.get("number")

    # print(
    #     "PR event received: "
    #     f"delivery={delivery_id}, "
    #     f"action={action}, "
    #     f"repository={repository}, "
    #     f"pr_number={pr_number}"
    # )

    # return {"message": "Webhook received"}
    if not delivery_id:
        raise HTTPException(
            status_code=400,
            detail="Missing GitHub delivery ID",
        )

    action = payload.get("action")
    repository = payload.get("repository", {}).get("full_name")
    pr_number = payload.get("number")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    INSERT INTO webhook_deliveries (
                        delivery_id,
                        event_type,
                        action,
                        repository,
                        pr_number,
                        payload
                    )
                    VALUES (
                        :delivery_id,
                        :event_type,
                        :action,
                        :repository,
                        :pr_number,
                        CAST(:payload AS JSONB)
                    )
                    ON CONFLICT (delivery_id) DO NOTHING
                    RETURNING delivery_id
                """),
                {
                    "delivery_id": delivery_id,
                    "event_type": event,
                    "action": action,
                    "repository": repository,
                    "pr_number": pr_number,
                    "payload": json.dumps(payload),
                },
            )

            inserted_id = result.scalar_one_or_none()

    if inserted_id is None:
        return {
            "message": "Duplicate delivery ignored",
            "delivery_id": delivery_id,
        }

    print(
        "PR event stored: "
        f"delivery={delivery_id}, "
        f"action={action}, "
        f"repository={repository}, "
        f"pr_number={pr_number}"
    )

    return {"message": "Webhook received"}
