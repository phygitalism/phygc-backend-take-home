import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    ALL = (QUEUED, PROCESSING, SUCCEEDED, FAILED)


class TransactionKind:
    TOPUP = "topup"
    CHARGE = "charge"
    REFUND = "refund"


class Workspace(Base):
    """A tenant. Credits are the prepaid balance generations are charged against."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    credits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)

    model: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    num_outputs: Mapped[int] = mapped_column(Integer, default=1)

    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED, index=True)
    # Price of the job in credits, fixed at submission time
    cost: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    provider_generation_id: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    output_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    transactions: Mapped[list["CreditTransaction"]] = relationship(back_populates="job")


class CreditTransaction(Base):
    """Append-only ledger of balance changes. Charges are negative, refunds positive."""

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job | None] = relationship(back_populates="transactions")
