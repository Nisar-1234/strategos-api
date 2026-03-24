"""
Seed database with initial conflicts and signal sources.

Usage:
    docker compose up -d db
    python scripts/seed_data.py

Requires DATABASE_URL_SYNC in .env or defaults to local Docker Compose DB.
"""

import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.services.bias_registry import SEED_SOURCES, SEED_CONFLICTS

settings = get_settings()
engine = create_engine(settings.DATABASE_URL_SYNC)


def seed_conflicts(session: Session) -> None:
    existing = session.execute(text("SELECT COUNT(*) FROM conflicts")).scalar()
    if existing > 0:
        print(f"  Conflicts table already has {existing} rows, skipping")
        return

    for c in SEED_CONFLICTS:
        session.execute(
            text("""
                INSERT INTO conflicts (id, name, region, status, description, created_at, updated_at)
                VALUES (:id, :name, :region, :status, :description, :now, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "name": c["name"],
                "region": c["region"],
                "status": c["status"],
                "description": c["description"],
                "now": datetime.now(timezone.utc),
            },
        )
    print(f"  Seeded {len(SEED_CONFLICTS)} conflicts")


def seed_sources(session: Session) -> None:
    existing = session.execute(text("SELECT COUNT(*) FROM signal_sources")).scalar()
    if existing > 0:
        print(f"  Signal sources table already has {existing} rows, skipping")
        return

    for s in SEED_SOURCES:
        session.execute(
            text("""
                INSERT INTO signal_sources (id, name, layer, ownership_type, bias_score, credibility_score, political_lean, agenda_flags, last_checked)
                VALUES (:id, :name, :layer, :ownership_type, :bias_score, :credibility_score, :political_lean, :agenda_flags::jsonb, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "name": s["name"],
                "layer": s["layer"],
                "ownership_type": s["ownership_type"],
                "bias_score": 10.0 - s["credibility_score"],
                "credibility_score": s["credibility_score"],
                "political_lean": s["political_lean"],
                "agenda_flags": str(s["agenda_flags"]).replace("'", '"'),
                "now": datetime.now(timezone.utc),
            },
        )
    print(f"  Seeded {len(SEED_SOURCES)} signal sources")


def main():
    print("STRATEGOS Database Seeder")
    print("=" * 40)

    with Session(engine) as session:
        try:
            print("\n[1/2] Seeding conflicts...")
            seed_conflicts(session)

            print("[2/2] Seeding signal sources...")
            seed_sources(session)

            session.commit()
            print("\nSeed complete.")
        except Exception as e:
            session.rollback()
            print(f"\nError: {e}")
            print("Make sure the database tables exist (run Alembic migrations first).")
            sys.exit(1)


if __name__ == "__main__":
    main()
