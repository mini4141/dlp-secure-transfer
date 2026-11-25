"""Seed the three demo users. Idempotent and safe when several replicas start at once;
run manually with `python -m app.seed`."""

import asyncio
import os

from sqlalchemy.dialects.postgresql import insert

from app.db import get_sessionmaker
from app.models import User
from app.security import hash_password

USERS = [("sam@corp.test", "sender"), ("ava@corp.test", "approver"), ("admin@corp.test", "admin")]


async def seed_users() -> None:
    password = os.environ.get("SEED_PASSWORD", "demo-password")
    async with get_sessionmaker()() as db:
        for email, role in USERS:
            stmt = insert(User).values(email=email, role=role, password_hash=hash_password(password))
            await db.execute(stmt.on_conflict_do_nothing(index_elements=["email"]))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_users())
    print("seeded", [e for e, _ in USERS])
