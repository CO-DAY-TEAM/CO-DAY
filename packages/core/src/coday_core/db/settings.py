import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


def get_database_url(env_file: str | Path = ".env") -> URL:
    raw_url = os.environ.get("DATABASE_URL")

    if raw_url is None:
        raw_url = dotenv_values(env_file).get("DATABASE_URL")

    if not raw_url:
        raise ValueError("DATABASE_URL 설정이 필요합니다.")

    try:
        url = make_url(raw_url)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL 형식을 확인해 주세요.") from None

    if url.drivername != "postgresql+asyncpg" or not url.database:
        raise ValueError(
            "DATABASE_URL은 postgresql+asyncpg 드라이버와 DB 이름이 필요합니다."
        )

    return url