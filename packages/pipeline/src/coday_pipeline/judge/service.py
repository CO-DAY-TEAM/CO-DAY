# LLM으로 전체 PR의 변경 내용을 평가해 리뷰 의견 생성
import json
from collections.abc import Awaitable, Callable

from agents import (
    Agent,
    ModelRetrySettings,
    ModelSettings,
    RunConfig,
    Runner,
    retry_policies,
)
from agents.retry import RetryPolicyContext
from coday_contracts import ReviewInput, ReviewResult
from coday_core.config import Settings
from coday_core.errors import ServiceError

from coday_pipeline.judge.prompts import INSTRUCTIONS


def validate_findings(result: ReviewResult, inputs: ReviewInput) -> ReviewResult:
    lines_by_path = {
        file.file_path: [line for hunk in file.hunks for line in hunk.lines]
        for file in inputs.files
    }
    valid = []
    for finding in result.findings:
        lines = lines_by_path.get(finding.path, [])
        changed = {
            line.new_line if finding.side == "RIGHT" else line.old_line
            for line in lines
            if line.kind == ("added" if finding.side == "RIGHT" else "removed")
        }
        if finding.line not in changed:
            raise ServiceError(
                "invalid_finding",
                "AI 응답의 지적 위치가 분석한 변경 줄과 일치하지 않습니다.",
            )
        start = finding.start_line or finding.line
        available = {line.new_line if finding.side == "RIGHT" else line.old_line for line in lines}
        if start > finding.line or any(
            number not in available for number in range(start, finding.line + 1)
        ):
            raise ServiceError(
                "invalid_finding",
                "AI 응답의 수정 범위가 분석한 코드 범위를 벗어났습니다.",
            )
        if finding.suggestion is not None and (
            finding.side != "RIGHT" or "```" in finding.suggestion
        ):
            finding = finding.model_copy(update={"suggestion": None})
        valid.append(finding)
    return ReviewResult(findings=valid)


async def judge(
    inputs: ReviewInput,
    instructions: str,
    settings: Settings,
    reserve_attempt: Callable[[], Awaitable[None]],
) -> ReviewResult:
    if not settings.openai_api_key.get_secret_value():
        raise ServiceError(
            "ai_not_configured",
            "서비스 AI 연결이 설정되지 않았습니다. 운영자에게 문의해 주세요.",
        )

    async def reserve_retry(context: RetryPolicyContext) -> bool:
        # SDK가 재시도를 예약하기 전에 호출 한도를 확보한다.
        await reserve_attempt()
        return True

    agent = Agent(
        name="review-agent",
        instructions=INSTRUCTIONS,
        model=settings.openai_model,
        model_settings=ModelSettings(
            store=False,
            max_tokens=12000,
            retry=ModelRetrySettings(
                max_retries=settings.internal_retries,
                policy=retry_policies.all(
                    retry_policies.any(
                        retry_policies.provider_suggested(),
                        retry_policies.network_error(),
                        retry_policies.http_status([408, 409, 429, *range(500, 600)]),
                    ),
                    reserve_retry,
                ),
            ),
        ),
        output_type=ReviewResult,
    )
    payload = {
        "review_instructions": instructions,
        "files": [file.model_dump() for file in inputs.files],
        "related_files": inputs.related_files,
    }
    if inputs.function_context:
        payload["function_context"] = [
            item.model_dump(exclude_none=True) for item in inputs.function_context
        ]
    await reserve_attempt()
    result = await Runner.run(
        agent,
        input=json.dumps(payload, ensure_ascii=False),
        max_turns=1,
        run_config=RunConfig(workflow_name="review-pr"),
    )
    return validate_findings(result.final_output, inputs)
