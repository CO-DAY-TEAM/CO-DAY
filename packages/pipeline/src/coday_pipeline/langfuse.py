from agents import set_tracing_disabled
from coday_core.config import Settings
from langfuse import Langfuse
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor


def setup_langfuse(settings: Settings) -> None:
    """워커 시작 시 프롬프트 조회와 선택적인 트레이싱을 준비한다."""
    set_tracing_disabled(not settings.langfuse_tracing_enabled)
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        tracing_enabled=settings.langfuse_tracing_enabled,
        environment="development",
    )
    if settings.langfuse_tracing_enabled:
        OpenAIAgentsInstrumentor().instrument()
    # 리뷰 처리를 시작하기 전에 SDK 프롬프트 캐시를 채운다.
    langfuse.get_prompt("prompt")
