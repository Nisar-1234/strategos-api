"""Initial schema - all tables for STRATEGOS Phase 1

Revision ID: 001_initial
Revises: 
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conflicts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("layer", sa.String(5), nullable=False, index=True),
        sa.Column("conflict_id", UUID(as_uuid=True), sa.ForeignKey("conflicts.id"), nullable=True, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
        sa.Column("raw_value", sa.Float, nullable=True),
        sa.Column("normalized_score", sa.Float, server_default="0.0"),
        sa.Column("alert_flag", sa.Boolean, server_default="false"),
        sa.Column("alert_severity", sa.String(10), nullable=True),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
    )

    op.create_table(
        "signal_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("layer", sa.String(5), nullable=False),
        sa.Column("ownership_type", sa.String(50), server_default="independent"),
        sa.Column("bias_score", sa.Float, server_default="0.0"),
        sa.Column("credibility_score", sa.Float, server_default="5.0"),
        sa.Column("political_lean", sa.Float, server_default="0.0"),
        sa.Column("agenda_flags", JSONB, nullable=True),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "predictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("conflict_id", UUID(as_uuid=True), sa.ForeignKey("conflicts.id"), index=True),
        sa.Column("escalation_prob", sa.Float, server_default="0.0"),
        sa.Column("negotiation_prob", sa.Float, server_default="0.0"),
        sa.Column("stalemate_prob", sa.Float, server_default="0.0"),
        sa.Column("resolution_prob", sa.Float, server_default="0.0"),
        sa.Column("confidence", sa.String(10), server_default="'LOW'"),
        sa.Column("convergence_score", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_outcome", sa.String(50), nullable=True),
    )

    op.create_table(
        "convergence_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("conflict_id", UUID(as_uuid=True), sa.ForeignKey("conflicts.id"), index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("layer_contributions", JSONB, nullable=True),
    )

    op.create_table(
        "llm_response_cache",
        sa.Column("cache_key", sa.String(64), primary_key=True),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("model_used", sa.String(50), nullable=False),
        sa.Column("input_tokens", sa.Integer, server_default="0"),
        sa.Column("output_tokens", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("org_id", sa.String(100), nullable=True),
        sa.Column("role", sa.String(50), server_default="'analyst'"),
        sa.Column("mfa_enabled", sa.Boolean, server_default="false"),
        sa.Column("auth0_sub", sa.String(255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("llm_response_cache")
    op.drop_table("convergence_scores")
    op.drop_table("predictions")
    op.drop_table("signal_sources")
    op.drop_table("signals")
    op.drop_table("conflicts")
