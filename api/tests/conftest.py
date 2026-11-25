"""Test fixtures. Needs Postgres (compose `postgres` service); S3/SQS come from an in-process moto server."""

import asyncio
import os
import socket
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from moto.server import ThreadedMotoServer

PG = os.environ.get("TEST_PG_HOST", "localhost:15432")
TEST_DB = "dlp_test"
PASSWORD = "test-password"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_port = _free_port()
_moto = ThreadedMotoServer(port=_port, verbose=False)
_moto.start()
_endpoint = f"http://127.0.0.1:{_port}"

os.environ.update(
    DATABASE_URL=f"postgresql+asyncpg://dlp_app:dlp_app@{PG}/{TEST_DB}",
    MIGRATION_DATABASE_URL=f"postgresql+asyncpg://dlp:dlp@{PG}/{TEST_DB}",
    APP_DB_PASSWORD="dlp_app",
    DB_NULL_POOL="true",
    AWS_ENDPOINT_URL=_endpoint,
    S3_PUBLIC_ENDPOINT_URL=_endpoint,
    AWS_ACCESS_KEY_ID="test",
    AWS_SECRET_ACCESS_KEY="test",
    AWS_REGION="ap-southeast-2",
    SQS_VISIBILITY_TIMEOUT="5",
    SEED_PASSWORD=PASSWORD,
)


def _prepare_database() -> None:
    async def recreate():
        conn = await asyncpg.connect(f"postgresql://dlp:dlp@{PG}/postgres")
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {TEST_DB}")
        await conn.close()

    asyncio.run(recreate())
    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


_prepare_database()

from app import aws  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_users  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    _moto.stop()


@pytest.fixture(scope="session", autouse=True)
def _aws_resources():
    aws.bootstrap()


@pytest_asyncio.fixture(autouse=True)
async def _clean_state():
    conn = await asyncpg.connect(f"postgresql://dlp:dlp@{PG}/{TEST_DB}")
    await conn.execute(
        "TRUNCATE approvals, findings, files, transfers, audit_events, users RESTART IDENTITY CASCADE"
    )
    await conn.close()
    await seed_users()
    while True:  # drain (PurgeQueue is rate limited)
        out = aws.sqs().receive_message(QueueUrl=aws.queue_url(), MaxNumberOfMessages=10, VisibilityTimeout=0)
        if not out.get("Messages"):
            break
        for m in out["Messages"]:
            aws.sqs().delete_message(QueueUrl=aws.queue_url(), ReceiptHandle=m["ReceiptHandle"])
    yield


@pytest_asyncio.fixture
async def client():
    import httpx

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client, email: str) -> None:
    r = await client.post("/login", data={"email": email, "password": PASSWORD})
    assert r.status_code == 303, r.text
