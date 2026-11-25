import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import aws
from app.config import get_settings
from app.observability import add_request_logging, setup_logging, setup_metrics, setup_tracing
from app.routers import api, pages, recipient
from app.security import LoginRequired
from app.seed import seed_users

log = logging.getLogger("app")


async def _bootstrap_aws() -> None:
    for attempt in range(30):
        try:
            await asyncio.to_thread(aws.bootstrap)
            return
        except Exception as exc:  # moto may still be starting
            log.warning("aws bootstrap retry", extra={"attempt": attempt, "err": str(exc)[:200]})
            await asyncio.sleep(2)
    raise RuntimeError("aws bootstrap failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.bootstrap_aws:
        await _bootstrap_aws()
    if s.seed_on_start:
        await seed_users()
    log.info("api started")
    yield


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="DLP Secure Transfer",
        version="0.1.0",
        description="Expiring, password-protected file transfers with DLP scanning and approval.",
        lifespan=lifespan,
    )
    add_request_logging(app)
    setup_metrics(app)
    setup_tracing(app)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(recipient.router)
    app.include_router(api.router)

    @app.exception_handler(LoginRequired)
    async def _login_required(_: Request, __: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.get("/healthz", tags=["ops"])
    async def healthz():
        return {"status": "ok"}

    return app


app = create_app()
