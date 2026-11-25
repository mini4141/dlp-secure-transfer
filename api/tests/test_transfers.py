from tests.helpers import make_transfer, scan_message


async def test_create_upload_finalize_enqueues_scan(client):
    """F2: transfer appears as `scanning` and one SQS message per file is queued."""
    t = await make_transfer(client)
    r = await client.get(f"/api/transfers/{t['id']}")
    assert r.json()["status"] == "scanning"
    assert r.json()["files"][0]["scan_status"] == "queued"
    msg = await scan_message()
    assert msg["file_id"] == t["uploads"][0]["file_id"] and msg["key"].startswith("uploads/")
