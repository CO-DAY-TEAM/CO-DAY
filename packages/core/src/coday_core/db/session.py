from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine, 
)

from coday_core.db.settings import get_database_url


def build_engine() -> AsyncEngine:
    return create_async_engine(
        get_database_url(),
        pool_pre_ping=True,
        echo=False,
        hide_parameters=True,
    )


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )