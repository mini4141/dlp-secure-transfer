"""Integration: upload -> S3 -> SQS -> Go worker -> findings. Needs the compose stack (scripts/dev-up.sh).

Run:  API_URL=http://localhost:18000 uv run pytest tests_integration
"""

import os
import time
from pathlib import Path

import httpx
import pytest

API = os.environ.get("API_URL", "http://localhost:18000")
SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "customers.csv"
PASSWORD = os.environ.get("SEED_PASSWORD", "demo-password")


def _login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=API, timeout=30)
    assert c.post("/login", data={"email": email, "password": PASSWORD}).status_code == 303
    return c


def _wait_for(client: httpx.Client, transfer_id: int, status: str, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/transfers/{transfer_id}").json()
        if body["status"] == status:
            return body
        time.sleep(1)
    pytest.fail(f"transfer {transfer_id} never reached {status}: {body}")


def test_upload_scan_findings_and_redacted_copy():
    data = SAMPLE.read_bytes()
    sam = _login("sam@corp.test")
    t = sam.post(
        "/api/transfers",
        json={
            "recipients": ["partner@example.org"],
            "password": "link-secret",
            "max_downloads": 1,
            "files": [{"filename": "customers.csv", "size": len(data), "content_type": "text/csv"}],
        },
    ).json()
    put = httpx.put(t["uploads"][0]["upload_url"], content=data, headers={"Content-Type": "text/csv"})
    assert put.status_code == 200
    assert sam.post(f"/api/transfers/{t['id']}/finalize").status_code == 200

    _wait_for(sam, t["id"], "pending_approval")

    ava = _login("ava@corp.test")
    page = ava.get(f"/approvals/{t['id']}").text
    for pii_type in ("card", "email", "phone"):
        assert f"<td>{pii_type}</td>" in page
    assert "4111 **** **** 1111" in page
    assert "[REDACTED:card]" in page  # redacted copy written by the worker
    assert "4111 1111 1111 1111" not in page  # raw PII never shown

    ava.post(f"/api/approvals/{t['id']}", json={"decision": "redacted"})
    assert sam.get(f"/api/transfers/{t['id']}").json()["release_variant"] == "redacted"
