# 데이터베이스 연결 및 세션 관리
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from coday_core.config import get_settings


@lru_cache
def engine():
    return create_engine(
        get_settings().database_url, pool_pre_ping=True, pool_size=20, max_overflow=10
    )


@contextmanager
def transaction():
    with Session(engine(), expire_on_commit=False) as session, session.begin():
        yield session
