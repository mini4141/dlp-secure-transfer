import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_sessionmaker
from tests.conftest import login
from tests.test_download import approved_redacted


async def test_audit_trail_and_append_only(client):
    """F6: every step is audited, CSV export works, and the app DB role cannot UPDATE/DELETE audit rows."""
    t = await approved_redacted(client)
    await client.post(f"/t/{t['token']}", data={"password": "link-secret"})
    await client.get(f"/t/{t['token']}/download/{t['uploads'][0]['file_id']}")
    await login(client, "admin@corp.test")
    actions = {e["action"] for e in (await client.get("/api/audit")).json()}
    assert {
        "transfer.created",
        "transfer.uploaded",
        "scan.completed",
        "transfer.approved.redacted",
        "download.completed",
    } <= actions
    csv = await client.get("/api/audit?format=csv")
    assert csv.headers["content-type"].startswith("text/csv") and "transfer.created" in csv.text
    assert "transfer.created" in (await client.get("/admin")).text

    async with get_sessionmaker()() as db:
        with pytest.raises(DBAPIError, match="permission denied"):
            await db.execute(text("UPDATE audit_events SET actor = 'evil'"))
    async with get_sessionmaker()() as db:
        with pytest.raises(DBAPIError, match="permission denied"):
            await db.execute(text("DELETE FROM audit_events"))
