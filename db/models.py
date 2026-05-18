from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fra1.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class RescuePost(Base):
    __tablename__ = "rescue_posts"

    id = Column(String, primary_key=True, default=_uuid)
    idempotency_key = Column(String, unique=True, nullable=False)
    source_platform = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)
    detected_at = Column(DateTime(timezone=True), default=_now)
    is_food_rescue = Column(Boolean, nullable=True)
    urgency_hint = Column(String, nullable=True)
    rescue_signals = Column(Text, nullable=True)  # JSON array as text

    analyses = relationship("RescueAnalysis", back_populates="post")


class RescueAnalysis(Base):
    __tablename__ = "rescue_analyses"

    id = Column(String, primary_key=True, default=_uuid)
    post_id = Column(String, ForeignKey("rescue_posts.id"), nullable=False)
    ingredients = Column(Text, nullable=True)   # JSON
    risk_scores = Column(Text, nullable=True)   # JSON
    rescue_plan = Column(Text, nullable=True)   # JSON
    model_used = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    post = relationship("RescuePost", back_populates="analyses")
    drafts = relationship("RescueDraft", back_populates="analysis")


class RescueDraft(Base):
    __tablename__ = "rescue_drafts"

    id = Column(String, primary_key=True, default=_uuid)
    analysis_id = Column(String, ForeignKey("rescue_analyses.id"), nullable=False)
    platform = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    hitl_status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), default=_now)

    analysis = relationship("RescueAnalysis", back_populates="drafts")
    reviews = relationship("HitlReview", back_populates="draft")
    sends = relationship("ChannelSend", back_populates="draft")


class HitlReview(Base):
    __tablename__ = "hitl_reviews"

    id = Column(String, primary_key=True, default=_uuid)
    draft_id = Column(String, ForeignKey("rescue_drafts.id"), nullable=False)
    action = Column(String, nullable=False)   # approved | edited | rejected | flagged
    editor_note = Column(Text, nullable=True)
    final_content = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), default=_now)

    draft = relationship("RescueDraft", back_populates="reviews")


class ChannelSend(Base):
    __tablename__ = "channel_sends"

    id = Column(String, primary_key=True, default=_uuid)
    draft_id = Column(String, ForeignKey("rescue_drafts.id"), nullable=False)
    platform = Column(String, nullable=False)
    external_id = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), default=_now)
    status = Column(String, default="sent")   # sent | failed

    draft = relationship("RescueDraft", back_populates="sends")


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return Session(engine)
