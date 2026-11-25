from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import Finding
from tests.conftest import login
from tests.helpers import make_transfer, post_findings, scan_message


async def _findings_rows() -> int:
    async with get_sessionmaker()() as db:
        return (await db.execute(select(func.count()).select_from(Finding))).scalar_one()


async def test_scan_callback_is_idempotent_and_needs_approval(client):
    """F3 (API side): findings -> pending_approval; a redelivered result creates no second row."""
    t = await make_transfer(client)
    scan = await scan_message()
    bad = await client.post("/internal/scan-results", json={}, headers={"X-Signature": "nope"})
    assert bad.status_code == 401
    r1 = await post_findings(client, scan, redacted_key="redacted/x")
    assert r1.json()["result"] == "ok"
    r2 = await post_findings(client, scan, redacted_key="redacted/x")
    assert r2.json()["result"] == "duplicate"
    assert await _findings_rows() == 1
    assert (await client.get(f"/api/transfers/{t['id']}")).json()["status"] == "pending_approval"


async def test_clean_file_is_released(client):
    t = await make_transfer(client)
    await post_findings(client, await scan_message(), status="clean")
    body = (await client.get(f"/api/transfers/{t['id']}")).json()
    assert body["status"] == "ready" and body["release_variant"] == "original"


async def test_approver_approves_redacted(client):
    """F4: sender cannot decide; the approver's `redacted` decision releases the redacted variant."""
    t = await make_transfer(client)
    await post_findings(client, await scan_message(), redacted_key="redacted/x")
    assert (await client.post(f"/api/approvals/{t['id']}", json={"decision": "redacted"})).status_code == 403
    await login(client, "ava@corp.test")
    page = await client.get(f"/approvals/{t['id']}", follow_redirects=False)
    assert page.status_code == 200
    assert "4111 **** **** 1111" in page.text and "4111 1111" not in page.text  # obfuscated only
    r = await client.post(f"/api/approvals/{t['id']}", json={"decision": "redacted"})
    assert r.json() == {"id": t["id"], "status": "ready", "release_variant": "redacted"}
