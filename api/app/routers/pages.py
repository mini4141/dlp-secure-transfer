from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import aws, services
from app.db import get_db
from app.models import AuditEvent, File, Finding, Transfer, User, now
from app.routers.api import audit_rows
from app.schemas import Decision
from app.security import COOKIE, optional_user, require_role, session_token, verify_password
from app.templating import render

router = APIRouter(include_in_schema=False)

HOME = {"sender": "/transfers", "approver": "/approvals", "admin": "/admin"}


@router.get("/")
async def index(user: User | None = Depends(optional_user)):
    return RedirectResponse(HOME[user.role] if user else "/login", status_code=303)


@router.get("/login")
async def login_form(request: Request, user: User | None = Depends(optional_user)):
    return render(request, "login.html", user)


@router.post("/login")
async def login(
    request: Request, email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)
):
    u = (await db.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
    if u is None or not verify_password(u.password_hash, password):
        services.audit(db, request, email.strip().lower(), "auth.login_failed")
        await db.commit()
        return render(request, "login.html", None, status_code=401, error="Wrong email or password.")
    services.audit(db, request, u.email, "auth.login")
    await db.commit()
    from app.config import get_settings

    resp = RedirectResponse(HOME[u.role], status_code=303)
    resp.set_cookie(COOKIE, session_token(u), httponly=True, samesite="lax",
                    secure=get_settings().cookie_secure, max_age=get_settings().session_hours * 3600)
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


# ---- sender ----

@router.get("/send")
async def send_form(request: Request, user: User = Depends(require_role("sender", "admin"))):
    return render(request, "send.html", user)


async def _visible_transfers(db: AsyncSession, user: User) -> list[Transfer]:
    q = select(Transfer).order_by(Transfer.id.desc()).limit(50)
    if user.role != "admin":
        q = q.where(Transfer.sender_id == user.id)
    return list((await db.execute(q)).scalars().all())


@router.get("/transfers")
async def transfers(request: Request, user: User = Depends(require_role("sender", "admin")),
                    db: AsyncSession = Depends(get_db)):
    return render(request, "transfers.html", user, transfers=await _visible_transfers(db, user))


@router.get("/transfers/rows")
async def transfer_rows(request: Request, user: User = Depends(require_role("sender", "admin")),
                        db: AsyncSession = Depends(get_db)):
    return render(request, "_transfer_rows.html", user, transfers=await _visible_transfers(db, user))


async def _own(db: AsyncSession, user: User, transfer_id: int) -> Transfer:
    t = await db.get(Transfer, transfer_id)
    if t is None or (t.sender_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Transfer not found")
    return t


@router.get("/transfers/{transfer_id}")
async def transfer_detail(transfer_id: int, request: Request, user: User = Depends(require_role("sender", "admin")),
                          db: AsyncSession = Depends(get_db)):
    t = await _own(db, user, transfer_id)
    return render(request, "transfer.html", user, t=t, link=str(request.base_url) + f"t/{t.token}")


@router.get("/transfers/{transfer_id}/panel")
async def transfer_panel(transfer_id: int, request: Request, user: User = Depends(require_role("sender", "admin")),
                         db: AsyncSession = Depends(get_db)):
    t = await _own(db, user, transfer_id)
    return render(request, "_transfer_panel.html", user, t=t, link=str(request.base_url) + f"t/{t.token}")


# ---- approver ----

@router.get("/approvals")
async def approvals(request: Request, user: User = Depends(require_role("approver", "admin")),
                    db: AsyncSession = Depends(get_db)):
    q = select(Transfer).where(Transfer.status == "pending_approval").order_by(Transfer.id)
    return render(request, "approvals.html", user, transfers=(await db.execute(q)).scalars().all())


@router.get("/approvals/{transfer_id}")
async def approval_detail(transfer_id: int, request: Request, user: User = Depends(require_role("approver", "admin")),
                          db: AsyncSession = Depends(get_db)):
    t = await db.get(Transfer, transfer_id)
    if t is None:
        raise HTTPException(404, "Transfer not found")
    previews = {}
    for f in t.files:
        if f.redacted_key:
            previews[f.id] = await aws.run(aws.read_head, f.redacted_key)
    return render(request, "approval.html", user, t=t, previews=previews)


@router.post("/approvals/{transfer_id}/decide")
async def approval_decide(
    transfer_id: int,
    request: Request,
    decision: str = Form(...),
    reason: str = Form(""),
    user: User = Depends(require_role("approver", "admin")),
    db: AsyncSession = Depends(get_db),
):
    t = await db.get(Transfer, transfer_id)
    if t is None:
        raise HTTPException(404, "Transfer not found")
    await services.decide(db, request, user, t, Decision(decision=decision, reason=reason))
    return RedirectResponse("/approvals", status_code=303)


# ---- admin ----

@router.get("/admin")
async def admin(request: Request, action: str = "", transfer_id: str = "",
                user: User = Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    since = now() - timedelta(hours=24)
    by_status = (
        await db.execute(
            select(Transfer.status, func.count()).where(Transfer.created_at >= since).group_by(Transfer.status)
        )
    ).all()
    by_type = (
        await db.execute(
            select(Finding.type, func.sum(Finding.count))
            .join(File, File.id == Finding.file_id)
            .join(Transfer, Transfer.id == File.transfer_id)
            .where(Transfer.created_at >= since)
            .group_by(Finding.type)
        )
    ).all()
    events_24h = (
        await db.execute(select(func.count()).select_from(AuditEvent).where(AuditEvent.at >= since))
    ).scalar_one()
    tid = int(transfer_id) if transfer_id.strip().isdigit() else None
    rows = await audit_rows(db, action.strip() or None, tid, limit=200)
    return render(request, "admin.html", user, by_status=by_status, by_type=by_type, events_24h=events_24h,
                  rows=rows, action=action, transfer_id=transfer_id)
