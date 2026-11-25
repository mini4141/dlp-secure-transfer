import hashlib
import hmac
import json

import httpx

from app import aws
from app.config import get_settings
from tests.conftest import login

CSV = b"id,card\n1,4111 1111 1111 1111\n"


async def make_transfer(client, *, max_downloads=1, content=CSV, filename="customers.csv", finalize=True):
    """Sam creates a transfer, uploads straight to (moto) S3 with the presigned PUT, and finalizes."""
    await login(client, "sam@corp.test")
    r = await client.post(
        "/api/transfers",
        json={
            "recipients": ["partner@example.org"],
            "message": "hello",
            "expires_days": 2,
            "password": "link-secret",
            "max_downloads": max_downloads,
            "files": [{"filename": filename, "size": len(content), "content_type": "text/csv"}],
        },
    )
    assert r.status_code == 201, r.text
    t = r.json()
    up = t["uploads"][0]
    async with httpx.AsyncClient() as direct:  # not through the API
        put = await direct.put(up["upload_url"], content=content, headers={"Content-Type": "text/csv"})
    assert put.status_code == 200, put.text
    if finalize:
        f = await client.post(f"/api/transfers/{t['id']}/finalize")
        assert f.status_code == 200, f.text
    return t


def signed(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    sig = hmac.new(get_settings().scan_hmac_secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Signature": sig, "Content-Type": "application/json"}


async def scan_message() -> dict:
    """Read the scan message the API enqueued."""
    out = aws.sqs().receive_message(QueueUrl=aws.queue_url(), MaxNumberOfMessages=1)
    msg = out["Messages"][0]
    aws.sqs().delete_message(QueueUrl=aws.queue_url(), ReceiptHandle=msg["ReceiptHandle"])
    return json.loads(msg["Body"])


async def post_findings(client, scan: dict, status="findings", redacted_key=None):
    findings = (
        [{"type": "card", "count": 1, "samples": [{"text": "4111 **** **** 1111", "line": 2}]}]
        if status == "findings"
        else []
    )
    body = {
        "scan_id": scan["scan_id"],
        "file_id": scan["file_id"],
        "status": status,
        "redacted_key": redacted_key,
        "findings": findings,
    }
    raw, headers = signed(body)
    return await client.post("/internal/scan-results", content=raw, headers=headers)
