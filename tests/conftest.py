import os

import pytest
from alembic import command
from alembic.config import Config
from coday_core.config import get_settings
from coday_core.db import engine
from coday_core.db.models import Base
from sqlalchemy import text
from sqlalchemy.engine import make_url


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL을 별도 PostgreSQL 테스트 DB로 설정하세요.")
    assert make_url(url).database.endswith("_test"), "검증 DB 이름은 _test로 끝나야 합니다."
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine().dispose()


@pytest.fixture
def db(database):
    with engine().begin() as connection:
        tables = ", ".join(f'"{table}"' for table in Base.metadata.tables)
        connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield
