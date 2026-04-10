"""TimescaleDB hypertables + badge columns + coordinates

Revision ID: 002_timescaledb
Revises: 001_initial
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "002_timescaledb"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # ── signals: new columns ────────────────────────────────────────────────
    op.add_column("signals", sa.Column("deviation_pct", sa.Float, nullable=True))
    op.add_column("signals", sa.Column("latitude", sa.Float, nullable=True))
    op.add_column("signals", sa.Column("longitude", sa.Float, nullable=True))

    # Convert alert_severity values to new ALERT/WATCH/NORMAL vocabulary
    op.execute("""
        UPDATE signals SET alert_severity = CASE
            WHEN alert_severity = 'CRITICAL' THEN 'ALERT'
            WHEN alert_severity = 'WARNING'  THEN 'WATCH'
            ELSE 'NORMAL'
        END
        WHERE alert_severity IS NOT NULL
    """)
    op.execute("UPDATE signals SET alert_severity = 'NORMAL' WHERE alert_severity IS NULL")

    # ── conflicts: add region centroid coordinates ──────────────────────────
    op.add_column("conflicts", sa.Column("latitude", sa.Float, nullable=True))
    op.add_column("conflicts", sa.Column("longitude", sa.Float, nullable=True))

    # Seed known centroids for existing conflicts
    op.execute("""
        UPDATE conflicts SET latitude = CASE name
            WHEN 'Russia-Ukraine War'       THEN 49.4
            WHEN 'Gaza Conflict'            THEN 31.5
            WHEN 'Taiwan Strait Tensions'   THEN 24.0
            WHEN 'Sudan Civil War'          THEN 15.6
            WHEN 'Iran Nuclear Program'     THEN 32.4
            WHEN 'Sahel Instability'        THEN 14.0
            WHEN 'Myanmar Civil War'        THEN 21.9
            WHEN 'South China Sea Dispute'  THEN 12.0
            WHEN 'Yemen/Houthi Conflict'    THEN 15.6
            WHEN 'Venezuela Political Crisis' THEN 8.0
            ELSE NULL
        END,
        longitude = CASE name
            WHEN 'Russia-Ukraine War'       THEN 31.2
            WHEN 'Gaza Conflict'            THEN 34.4
            WHEN 'Taiwan Strait Tensions'   THEN 120.9
            WHEN 'Sudan Civil War'          THEN 32.5
            WHEN 'Iran Nuclear Program'     THEN 53.7
            WHEN 'Sahel Instability'        THEN -2.0
            WHEN 'Myanmar Civil War'        THEN 95.9
            WHEN 'South China Sea Dispute'  THEN 114.0
            WHEN 'Yemen/Houthi Conflict'    THEN 48.5
            WHEN 'Venezuela Political Crisis' THEN -66.0
            ELSE NULL
        END
    """)

    # ── signals: composite PK required by TimescaleDB ──────────────────────
    # TimescaleDB requires the partition column (timestamp) to be part of any
    # unique constraint. Drop the id-only PK and replace with (id, timestamp).
    op.execute("ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_pkey")
    op.execute("ALTER TABLE signals ADD PRIMARY KEY (id, timestamp)")

    # ── convergence_scores: same composite PK requirement ──────────────────
    op.execute("ALTER TABLE convergence_scores DROP CONSTRAINT IF EXISTS convergence_scores_pkey")
    op.execute("ALTER TABLE convergence_scores ADD PRIMARY KEY (id, timestamp)")

    # ── Create TimescaleDB hypertables ──────────────────────────────────────
    op.execute("""
        SELECT create_hypertable(
            'signals', 'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            migrate_data => true,
            if_not_exists => true
        )
    """)
    op.execute("""
        SELECT create_hypertable(
            'convergence_scores', 'timestamp',
            chunk_time_interval => INTERVAL '7 days',
            migrate_data => true,
            if_not_exists => true
        )
    """)

    # ── Performance indexes ─────────────────────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS signals_conflict_layer_ts ON signals (conflict_id, layer, timestamp DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS signals_layer_ts ON signals (layer, timestamp DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS signals_alert_ts ON signals (alert_severity, timestamp DESC) WHERE alert_severity IN ('ALERT', 'WATCH')")
    op.execute("CREATE INDEX IF NOT EXISTS convergence_conflict_ts ON convergence_scores (conflict_id, timestamp DESC)")

    # ── llm_response_cache: retention policy placeholder ───────────────────
    # Rows expire via expires_at column; a Celery beat task cleans up daily.
    # (TimescaleDB retention policies require hypertable; cache table stays plain.)


def downgrade() -> None:
    op.drop_column("signals", "deviation_pct")
    op.drop_column("signals", "latitude")
    op.drop_column("signals", "longitude")
    op.drop_column("conflicts", "latitude")
    op.drop_column("conflicts", "longitude")
    # Hypertable and extension cleanup not automated to avoid data loss.
