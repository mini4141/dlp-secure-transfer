from datetime import timedelta

import httpx

from app import aws
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import Transfer, now
from tests.conftest import login
from tests.helpers import make_transfer, post_findings, scan_message


async def approved_redacted(client, **kw):
    t = await make_transfer(client, **kw)
    scan = await scan_message()
    rkey = f"redacted/{t['uploads'][0]['file_id']}.csv"
    aws.s3().put_object(Bucket=get_settings().s3_bucket, Key=rkey, Body=b"id,card\n1,[REDACTED:card]\n")
    await post_findings(client, scan, redacted_key=rkey)
    await login(client, "ava@corp.test")
    await client.post(f"/api/approvals/{t['id']}", json={"decision": "redacted"})
    client.cookies.clear()
    return t


async def test_download_with_password_then_limit(client):
    """F5: wrong password refused; first download is a 60 s presigned GET of the redacted copy;
    the download beyond the limit is refused."""
    t = await approved_redacted(client, max_downloads=1)
    link, fid = f"/t/{t['token']}", t["uploads"][0]["file_id"]
    assert (await client.post(link, data={"password": "wrong"})).status_code == 401
    assert (await client.post(link, data={"password": "link-secret"})).status_code == 303
    files = await client.get(link)
    assert "customers.csv" in files.text
    r = await client.get(f"{link}/download/{fid}")
    assert r.status_code == 302 and "X-Amz-Expires=60" in r.headers["location"]
    async with httpx.AsyncClient() as direct:
        assert "[REDACTED:card]" in (await direct.get(r.headers["location"])).text
    again = await client.get(f"{link}/download/{fid}")
    assert again.status_code == 410 and "Download limit reached" in again.text


async def test_expired_link(client):
    t = await approved_redacted(client)
    async with get_sessionmaker()() as db:
        tr = await db.get(Transfer, t["id"])
        tr.expires_at = now() - timedelta(minutes=1)
        await db.commit()
    r = await client.get(f"/t/{t['token']}")
    assert r.status_code == 410 and "Expired" in r.text
