from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # sender | approver | admin


class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    message: Mapped[str] = mapped_column(Text, default="")
    recipients: Mapped[str] = mapped_column(Text, default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_downloads: Mapped[int] = mapped_column(Integer, default=1)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    # uploading | scanning | pending_approval | ready | rejected
    status: Mapped[str] = mapped_column(String(20), default="uploading")
    release_variant: Mapped[str | None] = mapped_column(String(10), nullable=True)  # original | redacted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    sender: Mapped[User] = relationship(lazy="joined")
    files: Mapped[list["File"]] = relationship(back_populates="transfer", order_by="File.id", lazy="selectin")


class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfers.id"))
    filename: Mapped[str] = mapped_column(String(255))
    s3_key: Mapped[str] = mapped_column(String(512))
    redacted_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(127))
    # pending | queued | clean | findings | unscannable
    scan_status: Mapped[str] = mapped_column(String(20), default="pending")
    scan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    transfer: Mapped[Transfer] = relationship(back_populates="files")
    findings: Mapped[list["Finding"]] = relationship(order_by="Finding.id", lazy="selectin")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("file_id", "type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    type: Mapped[str] = mapped_column(String(20))
    count: Mapped[int] = mapped_column(Integer)
    samples: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"))


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfers.id"))
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))  # original | redacted | reject
    reason: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50))
    transfer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    ua: Mapped[str] = mapped_column(String(255), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
