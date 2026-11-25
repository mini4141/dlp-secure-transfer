"""Domain operations shared by the JSON API and the HTML views. Every state change writes an audit row."""

import re
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import aws
from app.config import get_settings
from app.models import Approval, AuditEvent, File, Finding, Transfer, User, now
from app.observability import SCAN_RESULTS
from app.schemas import CreatedTransfer, CreateTransfer, Decision, ScanResult, UploadTarget
from app.security import hash_password


def audit(db: AsyncSession, request: Request | None, actor: str, action: str, transfer_id: int | None = None):
    ip = ua = ""
    if request is not None:
        fwd = request.headers.get("x-forwarded-for")
        ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
        ua = request.headers.get("user-agent", "")[:255]
    db.add(AuditEvent(actor=actor, action=action, transfer_id=transfer_id, ip=ip, ua=ua))


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name.rsplit("/", 1)[-1])[:100] or "file"


async def create_transfer(
    db: AsyncSession, request: Request, user: User, body: CreateTransfer
) -> CreatedTransfer:
    s = get_settings()
    for f in body.files:
        if f.size > s.max_file_bytes:
            raise HTTPException(400, f"{f.filename} exceeds {s.max_file_bytes // (1024 * 1024)} MB")
    t = Transfer(
        sender_id=user.id,
        token=secrets.token_urlsafe(24),
        message=body.message,
        recipients=", ".join(body.recipients),
        password_hash=hash_password(body.password),
        expires_at=now() + timedelta(days=body.expires_days),
        max_downloads=body.max_downloads,
        status="uploading",
    )
    db.add(t)
    await db.flush()
    uploads = []
    for spec in body.files:
        f = File(
            transfer_id=t.id, filename=spec.filename, s3_key="", size=spec.size, content_type=spec.content_type
        )
        db.add(f)
        await db.flush()
        f.s3_key = f"uploads/{t.id}/{f.id}-{_safe(spec.filename)}"
        url = await aws.run(aws.presign_put, f.s3_key, spec.content_type, spec.size)
        uploads.append(
            UploadTarget(file_id=f.id, filename=spec.filename, upload_url=url, content_type=spec.content_type)
        )
    audit(db, request, user.email, "transfer.created", t.id)
    await db.commit()
    return CreatedTransfer(id=t.id, token=t.token, status=t.status, uploads=uploads)


async def finalize_transfer(db: AsyncSession, request: Request, user: User, t: Transfer) -> Transfer:
    if t.status != "uploading":
        return t
    for f in t.files:
        size = await aws.run(aws.head_size, f.s3_key)
        if size != f.size:
            raise HTTPException(400, f"{f.filename} was not uploaded completely")
    for f in t.files:
        f.scan_id = uuid.uuid4().hex
        f.scan_status = "queued"
    t.status = "scanning"
    audit(db, request, user.email, "transfer.uploaded", t.id)
    await db.commit()
    for f in t.files:
        await aws.run(
            aws.send_scan, {"scan_id": f.scan_id, "file_id": f.id, "key": f.s3_key, "filename": f.filename}
        )
    return t


async def apply_scan_result(db: AsyncSession, request: Request, r: ScanResult) -> str:
    """Idempotent by scan_id: a redelivered message cannot create a second set of findings."""
    probe = await db.get(File, r.file_id)
    if probe is None or probe.scan_id != r.scan_id:
        raise HTTPException(404, "Unknown scan")
    t = (
        await db.execute(select(Transfer).where(Transfer.id == probe.transfer_id).with_for_update(of=Transfer))
    ).scalar_one()
    await db.refresh(probe)
    if probe.scan_status != "queued":
        await db.rollback()
        SCAN_RESULTS.labels("duplicate").inc()
        return "duplicate"
    probe.scan_status = r.status
    probe.redacted_key = r.redacted_key
    for fi in r.findings:
        db.add(
            Finding(file_id=probe.id, type=fi.type, count=fi.count, samples=[s.model_dump() for s in fi.samples])
        )
    audit(db, request, "dlp-worker", "scan.completed", t.id)
    await db.flush()
    await db.refresh(t, attribute_names=["files"])
    if all(f.scan_status not in ("pending", "queued") for f in t.files):
        if any(f.scan_status in ("findings", "unscannable") for f in t.files):
            t.status = "pending_approval"
        else:
            t.status = "ready"
            t.release_variant = "original"
            audit(db, request, "system", "transfer.released", t.id)
    await db.commit()
    SCAN_RESULTS.labels(r.status).inc()
    return "ok"


async def decide(db: AsyncSession, request: Request, user: User, t: Transfer, d: Decision) -> Transfer:
    if t.status != "pending_approval":
        raise HTTPException(409, "Transfer is not awaiting approval")
    if d.decision == "reject" and not d.reason.strip():
        raise HTTPException(400, "A reason is required to reject")
    db.add(Approval(transfer_id=t.id, approver_id=user.id, decision=d.decision, reason=d.reason))
    if d.decision == "reject":
        t.status = "rejected"
        audit(db, request, user.email, "transfer.rejected", t.id)
    else:
        t.status = "ready"
        t.release_variant = d.decision
        audit(db, request, user.email, f"transfer.approved.{d.decision}", t.id)
    await db.commit()
    return t
