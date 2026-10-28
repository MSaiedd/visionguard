"""Durable workspace inspections and optimistic human-review history."""

import time
import uuid
from contextlib import contextmanager

from sqlalchemy import JSON, Float, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (UniqueConstraint("tenant", "content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    filename: Mapped[str] = mapped_column(String(240))
    batch: Mapped[str] = mapped_column(String(120), default="Manual upload")
    content_hash: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    regions: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    review: Mapped[str] = mapped_column(String(20), default="pending")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    user: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(80))
    inspection_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Database:
    def __init__(self, url):
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 20}
            if url.startswith("sqlite")
            else {},
            pool_pre_ping=True,
        )
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def configure(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
