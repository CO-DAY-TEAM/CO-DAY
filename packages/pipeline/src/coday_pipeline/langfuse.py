from agents import set_tracing_disabled
from coday_core.config import Settings
from langfuse import Langfuse
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor


def setup_langfuse(settings: Settings) -> None:
    """프로세스 시작 시 한 번 호출해 Langfuse 추적을 설정한다."""
    # Agents SDK 자체의 추적을 켜거나 끈다.
    set_tracing_disabled(not settings.langfuse_tracing_enabled)
    # 추적이 꺼져 있으면 Langfuse 초기화도 생략한다.
    if not settings.langfuse_tracing_enabled:
        return

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment="development",
    )
    OpenAIAgentsInstrumentor().instrument()
