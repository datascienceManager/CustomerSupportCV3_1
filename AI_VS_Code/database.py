"""
services/database.py
SQLAlchemy models + CRUD operations.
Uses SQLite (free, zero-config) for demo; switches to MySQL for production.
"""

import logging
from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum

from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    DateTime, Enum, Boolean, Index, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from config.settings import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


# ── Enums ────────────────────────────────────────────────────────────────────

class QueryCategory(str, PyEnum):
    PRODUCT = "product"
    PAYMENT = "payment"
    UNKNOWN = "unknown"

class QueryChannel(str, PyEnum):
    VOICE = "voice"
    CHAT = "chat"

class QueryStatus(str, PyEnum):
    NEW = "new"
    SUMMARISED = "summarised"
    EMAILED = "emailed"


# ── Models ───────────────────────────────────────────────────────────────────

class CustomerQuery(Base):
    """Stores every customer interaction."""
    __tablename__ = "customer_queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    customer_name = Column(String(128), nullable=True)
    customer_email = Column(String(256), nullable=True)
    channel = Column(Enum(QueryChannel), nullable=False, default=QueryChannel.CHAT)
    category = Column(Enum(QueryCategory), nullable=False, default=QueryCategory.UNKNOWN)
    raw_query = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=True)
    sentiment = Column(String(32), nullable=True)   # positive / neutral / negative
    status = Column(Enum(QueryStatus), nullable=False, default=QueryStatus.NEW)
    google_sheet_row = Column(Integer, nullable=True)   # row number written to GSheet
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_category_status", "category", "status"),
        Index("ix_created_at", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "customer_name": self.customer_name or "Anonymous",
            "customer_email": self.customer_email or "",
            "channel": self.channel.value if self.channel else "chat",
            "category": self.category.value if self.category else "unknown",
            "raw_query": self.raw_query,
            "ai_response": self.ai_response or "",
            "sentiment": self.sentiment or "neutral",
            "status": self.status.value if self.status else "new",
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class EmailLog(Base):
    """Tracks every summary email sent to departments."""
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department = Column(String(64), nullable=False)
    recipient_email = Column(String(256), nullable=False)
    query_count = Column(Integer, nullable=False, default=0)
    summary_text = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)


# ── Engine & Session factory ─────────────────────────────────────────────────

def _build_engine():
    url = settings.db.connection_url
    logger.info("Connecting to database: %s", url.split("@")[-1] if "@" in url else url)

    kwargs = {}
    if settings.db.db_type == "sqlite":
        # SQLite needs special pool config for multi-thread (Streamlit uses threads)
        kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    engine = create_engine(url, echo=False, **kwargs)
    Base.metadata.create_all(engine)
    logger.info("Database tables initialised ✓")
    return engine


_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session() -> Session:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


# ── CRUD helpers ─────────────────────────────────────────────────────────────

def save_query(
    session_id: str,
    raw_query: str,
    ai_response: str,
    category: str,
    channel: str = "chat",
    customer_name: Optional[str] = None,
    customer_email: Optional[str] = None,
    sentiment: Optional[str] = "neutral",
) -> CustomerQuery:
    """Persist a single customer interaction and return the saved row."""
    db = get_session()
    try:
        record = CustomerQuery(
            session_id=session_id,
            customer_name=customer_name,
            customer_email=customer_email,
            channel=QueryChannel(channel),
            category=QueryCategory(category) if category in QueryCategory._value2member_map_ else QueryCategory.UNKNOWN,
            raw_query=raw_query,
            ai_response=ai_response,
            sentiment=sentiment,
            status=QueryStatus.NEW,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.debug("Saved query id=%s category=%s", record.id, record.category)
        return record
    except Exception as exc:
        db.rollback()
        logger.error("DB save_query failed: %s", exc)
        raise
    finally:
        db.close()


def get_unsummarised_queries(category: Optional[str] = None) -> List[CustomerQuery]:
    """Fetch all NEW queries, optionally filtered by category."""
    db = get_session()
    try:
        q = db.query(CustomerQuery).filter(CustomerQuery.status == QueryStatus.NEW)
        if category:
            q = q.filter(CustomerQuery.category == QueryCategory(category))
        return q.order_by(CustomerQuery.created_at).all()
    finally:
        db.close()


def mark_queries_emailed(query_ids: List[int]):
    db = get_session()
    try:
        db.query(CustomerQuery).filter(
            CustomerQuery.id.in_(query_ids)
        ).update({"status": QueryStatus.EMAILED}, synchronize_session=False)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("mark_queries_emailed failed: %s", exc)
    finally:
        db.close()


def log_email(
    department: str,
    recipient: str,
    query_count: int,
    summary: str,
    success: bool,
    error: Optional[str] = None,
):
    db = get_session()
    try:
        entry = EmailLog(
            department=department,
            recipient_email=recipient,
            query_count=query_count,
            summary_text=summary,
            success=success,
            error_message=error,
        )
        db.add(entry)
        db.commit()
    finally:
        db.close()


def get_all_queries(limit: int = 500) -> List[dict]:
    db = get_session()
    try:
        rows = (
            db.query(CustomerQuery)
            .order_by(CustomerQuery.created_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        db.close()
