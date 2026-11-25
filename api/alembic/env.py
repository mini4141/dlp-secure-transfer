import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.models import Base

target_metadata = Base.metadata


def _url() -> str:
    # Migrations run as the DB owner; the app connects as the restricted dlp_app role.
    return os.environ.get("MIGRATION_DATABASE_URL", "postgresql+asyncpg://dlp:dlp@localhost:5432/dlp")


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_main())
