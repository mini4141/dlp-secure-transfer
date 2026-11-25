from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATUS_LABEL = {
    "uploading": "uploading",
    "scanning": "scanning",
    "pending_approval": "pending approval",
    "ready": "ready",
    "rejected": "rejected",
}


def render(request: Request, name: str, user, status_code: int = 200, **ctx):
    return templates.TemplateResponse(
        request, name, {"user": user, "labels": STATUS_LABEL, **ctx}, status_code=status_code
    )
