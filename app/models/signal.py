import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Signal(Base):
    """Standard signal schema — every signal from every layer normalized to this structure."""
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    layer: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    conflict_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conflicts.id"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    raw_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_score: Mapped[float] = mapped_column(Float, default=0.0)
    alert_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class SignalSource(Base):
    __tablename__ = "signal_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    layer: Mapped[str] = mapped_column(String(5), nullable=False)
    ownership_type: Mapped[str] = mapped_column(String(50), default="independent")
    bias_score: Mapped[float] = mapped_column(Float, default=0.0)
    credibility_score: Mapped[float] = mapped_column(Float, default=5.0)
    political_lean: Mapped[float] = mapped_column(Float, default=0.0)
    agenda_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conflict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conflicts.id"), index=True)
    escalation_prob: Mapped[float] = mapped_column(Float, default=0.0)
    negotiation_prob: Mapped[float] = mapped_column(Float, default=0.0)
    stalemate_prob: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_prob: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[str] = mapped_column(String(10), default="LOW")
    convergence_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ConvergenceScore(Base):
    __tablename__ = "convergence_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conflict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conflicts.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    layer_contributions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class LLMResponseCache(Base):
    __tablename__ = "llm_response_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    org_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="analyst")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auth0_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
