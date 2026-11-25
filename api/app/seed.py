"""Seed the three demo users. Idempotent; run with `python -m app.seed`."""

import asyncio
import os

from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import User
from app.security import hash_password

USERS = [("sam@corp.test", "sender"), ("ava@corp.test", "approver"), ("admin@corp.test", "admin")]


async def seed_users() -> None:
    password = os.environ.get("SEED_PASSWORD", "demo-password")
    async with get_sessionmaker()() as db:
        existing = set((await db.execute(select(User.email))).scalars())
        for email, role in USERS:
            if email not in existing:
                db.add(User(email=email, role=role, password_hash=hash_password(password)))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_users())
    print("seeded", [e for e, _ in USERS])
