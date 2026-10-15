# 워커 프로세스 진입점
import asyncio
import logging
from contextlib import AsyncExitStack

from agents import set_default_openai_client
from coday_core.config import get_settings
from coday_core.github import GitHub
from openai import AsyncOpenAI

from coday_worker.runner import worker_loop


async def main():
    settings = get_settings()
    settings.validate_auth()
    async with AsyncExitStack() as stack:
        github = GitHub(settings)
        stack.push_async_callback(github.close)
        if settings.openai_api_key.get_secret_value():
            client = await stack.enter_async_context(
                AsyncOpenAI(
                    api_key=settings.openai_api_key.get_secret_value(),
                    max_retries=0,
                    timeout=180,
                )
            )
            set_default_openai_client(client, use_for_tracing=True)
        async with asyncio.TaskGroup() as workers:
            for _ in range(settings.worker_concurrency):
                workers.create_task(worker_loop(github))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
