import csv
import hmac
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import services
from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, Transfer, User
from app.schemas import CreatedTransfer, CreateTransfer, Decision, ScanResult
from app.security import require_role

router = APIRouter()


async def _own_transfer(db: AsyncSession, user: User, transfer_id: int) -> Transfer:
    t = await db.get(Transfer, transfer_id)
    if t is None or (t.sender_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Transfer not found")
    return t


@router.post("/api/transfers", response_model=CreatedTransfer, status_code=201, tags=["transfers"])
async def create_transfer(
    body: CreateTransfer,
    request: Request,
    user: User = Depends(require_role("sender", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a transfer and return presigned PUT URLs (files go straight to S3)."""
    return await services.create_transfer(db, request, user, body)


@router.post("/api/transfers/{transfer_id}/finalize", tags=["transfers"])
async def finalize_transfer(
    transfer_id: int,
    request: Request,
    user: User = Depends(require_role("sender", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Verify the uploads and enqueue one SQS scan message per file."""
    t = await services.finalize_transfer(db, request, user, await _own_transfer(db, user, transfer_id))
    return {"id": t.id, "status": t.status}


@router.get("/api/transfers/{transfer_id}", tags=["transfers"])
async def get_transfer(
    transfer_id: int, user: User = Depends(require_role("sender", "admin")), db: AsyncSession = Depends(get_db)
):
    t = await _own_transfer(db, user, transfer_id)
    return {
        "id": t.id,
        "status": t.status,
        "release_variant": t.release_variant,
        "download_count": t.download_count,
        "max_downloads": t.max_downloads,
        "files": [{"id": f.id, "filename": f.filename, "scan_status": f.scan_status} for f in t.files],
    }


@router.post("/api/approvals/{transfer_id}", tags=["approvals"])
async def decide(
    transfer_id: int,
    body: Decision,
    request: Request,
    user: User = Depends(require_role("approver", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Approve the original or the redacted copy, or reject with a reason."""
    t = await db.get(Transfer, transfer_id)
    if t is None:
        raise HTTPException(404, "Transfer not found")
    t = await services.decide(db, request, user, t, body)
    return {"id": t.id, "status": t.status, "release_variant": t.release_variant}


@router.post("/internal/scan-results", tags=["internal"])
async def scan_results(request: Request, db: AsyncSession = Depends(get_db)):
    """Worker callback, authenticated by an HMAC of the body. Idempotent by scan_id."""
    raw = await request.body()
    expected = hmac.new(get_settings().scan_hmac_secret.encode(), raw, "sha256").hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("x-signature", "")):
        raise HTTPException(401, "Bad signature")
    result = await services.apply_scan_result(db, request, ScanResult.model_validate_json(raw))
    return JSONResponse({"result": result})


async def audit_rows(db: AsyncSession, action: str | None, transfer_id: int | None, limit: int = 500):
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if action:
        q = q.where(AuditEvent.action.like(f"{action}%"))
    if transfer_id:
        q = q.where(AuditEvent.transfer_id == transfer_id)
    return (await db.execute(q)).scalars().all()


def _dt(v: datetime) -> str:
    return v.isoformat(timespec="seconds")


@router.get("/api/audit", tags=["audit"])
async def audit_log(
    format: str = Query("json", pattern="^(json|csv)$"),
    action: str | None = None,
    transfer_id: int | None = None,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    rows = await audit_rows(db, action, transfer_id)
    if format == "json":
        return [
            {"id": r.id, "actor": r.actor, "action": r.action, "transfer_id": r.transfer_id, "ip": r.ip,
             "ua": r.ua, "at": _dt(r.at)}
            for r in rows
        ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "at", "actor", "action", "transfer_id", "ip", "user_agent"])
    for r in rows:
        w.writerow([r.id, _dt(r.at), r.actor, r.action, r.transfer_id or "", r.ip, r.ua])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )

