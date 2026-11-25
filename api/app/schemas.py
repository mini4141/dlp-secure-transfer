from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class FileSpec(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size: int = Field(ge=1)
    content_type: str = "application/octet-stream"


class CreateTransfer(BaseModel):
    recipients: list[EmailStr] = Field(min_length=1)
    message: str = Field(default="", max_length=2000)
    expires_days: int = Field(default=3, ge=1, le=7)
    password: str = Field(min_length=6, max_length=128)
    max_downloads: int = Field(default=1, ge=1, le=50)
    files: list[FileSpec] = Field(min_length=1, max_length=5)


class UploadTarget(BaseModel):
    file_id: int
    filename: str
    upload_url: str
    content_type: str


class CreatedTransfer(BaseModel):
    id: int
    token: str
    status: str
    uploads: list[UploadTarget]


class Decision(BaseModel):
    decision: Literal["original", "redacted", "reject"]
    reason: str = Field(default="", max_length=1000)


class SampleIn(BaseModel):
    text: str
    line: int = 0


class FindingIn(BaseModel):
    type: str
    count: int
    samples: list[SampleIn] = []


class ScanResult(BaseModel):
    scan_id: str
    file_id: int
    status: Literal["clean", "findings", "unscannable"]
    redacted_key: str | None = None
    findings: list[FindingIn] = []
