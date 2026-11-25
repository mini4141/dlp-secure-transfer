from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import aws, services
from app.db import get_db
from app.models import File, Transfer, now
from app.observability import DOWNLOADS
from app.security import make_token, read_token, verify_password
from app.templating import render

router = APIRouter()


def _cookie(token: str) -> str:
    return f"dl_{token}"


async def _load(db: AsyncSession, token: str) -> Transfer | None:
    return (await db.execute(select(Transfer).where(Transfer.token == token))).scalar_one_or_none()


def _unavailable(t: Transfer | None) -> str | None:
    if t is None:
        return "This link does not exist."
    if t.expires_at <= now():
        return "Expired"
    if t.status == "rejected":
        return "This transfer was rejected by the approver."
    if t.status != "ready":
        return "This transfer is not available yet. It is still being checked."
    return None


def _unlocked(request: Request, token: str) -> bool:
    data = read_token(request.cookies.get(_cookie(token)))
    return bool(data and data.get("t") == token)


@router.get("/t/{token}")
async def open_link(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    t = await _load(db, token)
    if msg := _unavailable(t):
        return render(request, "recipient.html", None, status_code=410 if msg == "Expired" else 200,
                      state="blocked", message=msg)
    if not _unlocked(request, token):
        return render(request, "recipient.html", None, state="password", token=token)
    return render(request, "recipient.html", None, state="files", token=token, transfer=t,
                  remaining=t.max_downloads - t.download_count)


@router.post("/t/{token}")
async def unlock(token: str, request: Request, password: str = Form(...), db: AsyncSession = Depends(get_db)):
    t = await _load(db, token)
    if msg := _unavailable(t):
        return render(request, "recipient.html", None, state="blocked", message=msg)
    if not verify_password(t.password_hash, password):
        services.audit(db, request, "recipient", "link.password_failed", t.id)
        await db.commit()
        return render(request, "recipient.html", None, status_code=401, state="password", token=token,
                      error="Wrong password.")
    resp = RedirectResponse(f"/t/{token}", status_code=303)
    resp.set_cookie(_cookie(token), make_token({"t": token}, timedelta(minutes=15)), httponly=True,
                    samesite="lax", path=f"/t/{token}")
    services.audit(db, request, "recipient", "link.unlocked", t.id)
    await db.commit()
    return resp


@router.get("/t/{token}/download/{file_id}")
async def download(token: str, file_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    t = await _load(db, token)
    if msg := _unavailable(t):
        DOWNLOADS.labels("denied").inc()
        return render(request, "recipient.html", None, status_code=410, state="blocked", message=msg)
    if not _unlocked(request, token):
        return RedirectResponse(f"/t/{token}", status_code=303)
    f = await db.get(File, file_id)
    if f is None or f.transfer_id != t.id:
        return render(request, "recipient.html", None, status_code=404, state="blocked", message="File not found.")
    # Atomic counter: the UPDATE only succeeds while the limit has not been reached.
    res = await db.execute(
        update(Transfer)
        .where(Transfer.id == t.id, Transfer.download_count < Transfer.max_downloads)
        .values(download_count=Transfer.download_count + 1)
    )
    if res.rowcount == 0:
        services.audit(db, request, "recipient", "download.denied", t.id)
        await db.commit()
        DOWNLOADS.labels("limit").inc()
        return render(request, "recipient.html", None, status_code=410, state="blocked",
                      message="Download limit reached")
    use_redacted = t.release_variant == "redacted" and f.redacted_key
    key = f.redacted_key if use_redacted else f.s3_key
    text_types = (".txt", ".csv", ".md", ".json")
    name = f.filename + (".redacted.txt" if use_redacted and not f.filename.endswith(text_types) else "")
    url = await aws.run(aws.presign_get, key, name)
    services.audit(db, request, "recipient", "download.completed", t.id)
    await db.commit()
    DOWNLOADS.labels("ok").inc()
    return RedirectResponse(url, status_code=302)
