"""Persistence-only SQLAlchemy tables shared by outbox adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Metadata root for kernel infrastructure tables."""


class OutboxRecord(Base):
    """A durable integration-event envelope and its delivery state."""

    __tablename__ = "kernel_outbox"
    __table_args__ = (
        Index("ix_kernel_outbox_pending", "status", "next_attempt_at", "id"),
        Index("ix_kernel_outbox_lease", "status", "lease_expires_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(255))
    schema_version: Mapped[int] = mapped_column(Integer)
    aggregate_type: Mapped[str] = mapped_column(String(255))
    aggregate_id: Mapped[str] = mapped_column(String(255))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InboxRecord(Base):
    """A consumer's receipt of one integration event, for idempotent handling."""

    __tablename__ = "kernel_inbox"
    __table_args__ = (
        UniqueConstraint("consumer", "event_id", name="uq_kernel_inbox_consumer_event"),
        Index("ix_kernel_inbox_processed", "processed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumer: Mapped[str] = mapped_column(String(255), index=True)
    event_id: Mapped[str] = mapped_column(String(36))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
