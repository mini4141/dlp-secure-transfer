"""Tiny API client for the resilience drill: `create` prints a new transfer id, `wait ID` blocks until scanned."""

import os
import sys
import time
from pathlib import Path

import httpx

API = os.environ.get("API_URL", "http://localhost:18000")
PASSWORD = os.environ.get("SEED_PASSWORD", "demo-password")
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "customers.csv"


def sam() -> httpx.Client:
    c = httpx.Client(base_url=API, timeout=30)
    assert c.post("/login", data={"email": "sam@corp.test", "password": PASSWORD}).status_code == 303
    return c


def create() -> None:
    data = SAMPLE.read_bytes()
    c = sam()
    t = c.post(
        "/api/transfers",
        json={
            "recipients": ["partner@example.org"],
            "password": "drill-secret",
            "files": [{"filename": "customers.csv", "size": len(data), "content_type": "text/csv"}],
        },
    ).json()
    httpx.put(t["uploads"][0]["upload_url"], content=data, headers={"Content-Type": "text/csv"}).raise_for_status()
    c.post(f"/api/transfers/{t['id']}/finalize").raise_for_status()
    print(t["id"])


def wait(transfer_id: str, timeout: int = 90) -> None:
    c = sam()
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = c.get(f"/api/transfers/{transfer_id}").json()["status"]
        if status != "scanning":
            print(status)
            return
        time.sleep(1)
    sys.exit("timeout waiting for scan")


if __name__ == "__main__":
    {"create": lambda: create(), "wait": lambda: wait(sys.argv[2])}[sys.argv[1]]()
