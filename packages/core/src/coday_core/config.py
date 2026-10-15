# 환경 설정 로딩
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://coday:coday@localhost:5432/coday"
    public_url: str = "http://localhost:5173"
    github_app_id: str = ""
    github_app_slug: str = ""
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    github_private_key_path: Path = Path("github-app.pem")
    github_webhook_secret: SecretStr = SecretStr("")
    token_encryption_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5-mini"
    worker_concurrency: int = Field(default=2, ge=1, le=16)
    job_timeout_seconds: int = Field(default=1800, ge=60)
    max_ai_calls: int = Field(default=100, ge=1)
    max_file_bytes: int = Field(default=2_000_000, ge=1000)
    max_input_bytes: int = Field(default=20_000_000, ge=1000)
    chunk_chars: int = Field(default=18000, ge=500)
    related_file_count: int = Field(default=5, ge=0, le=20)
    internal_retries: int = Field(default=2, ge=0, le=5)
    worker_recoveries: int = Field(default=3, ge=1, le=10)
    web_dist: Path = Path("apps/web/dist")

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def bot_login(self) -> str:
        return f"{self.github_app_slug}[bot]"

    def validate_auth(self) -> None:
        required = [
            self.github_app_id,
            self.github_app_slug,
            self.github_client_id,
            self.github_client_secret.get_secret_value(),
            self.github_webhook_secret.get_secret_value(),
            self.token_encryption_key.get_secret_value(),
        ]
        if not all(required) or not self.github_private_key_path.is_file():
            raise RuntimeError("GitHub App 인증 환경 변수를 먼저 설정하세요.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
