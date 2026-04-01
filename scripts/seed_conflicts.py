"""
Seed the conflicts table with known geopolitical conflicts.
Run: python -m scripts.seed_conflicts
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import os
DATABASE_URL = os.environ.get("DATABASE_URL_SYNC", "postgresql://strategos:strategos@localhost:5433/strategos")

CONFLICTS = [
    {
        "id": "10000000-0000-0000-0000-000000000001",
        "name": "Russia-Ukraine War",
        "region": "Eastern Europe",
        "status": "active",
        "description": "Full-scale armed conflict between Russia and Ukraine. Involves NATO indirect support, sanctions, and nuclear posturing.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000002",
        "name": "Gaza Conflict",
        "region": "Middle East",
        "status": "active",
        "description": "Israeli-Palestinian armed conflict centered on Gaza. Involves Hamas, Hezbollah, Iran proxies, and humanitarian crisis.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000003",
        "name": "Taiwan Strait Tensions",
        "region": "East Asia",
        "status": "monitoring",
        "description": "Escalating tensions between China and Taiwan with US involvement. Military exercises, trade pressure, and diplomatic posturing.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000004",
        "name": "Sudan Civil War",
        "region": "East Africa",
        "status": "active",
        "description": "Armed conflict between SAF and RSF factions. Massive humanitarian displacement and regional instability.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000005",
        "name": "Iran Nuclear Program",
        "region": "Middle East",
        "status": "monitoring",
        "description": "Iran's nuclear enrichment program and international negotiations. Sanctions regime and proxy network involvement.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000006",
        "name": "Sahel Instability",
        "region": "West Africa",
        "status": "active",
        "description": "Military coups and insurgencies across Mali, Burkina Faso, Niger. Wagner/Africa Corps involvement.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000007",
        "name": "Myanmar Civil War",
        "region": "Southeast Asia",
        "status": "active",
        "description": "Military junta vs resistance forces. Ethnic armed organizations, humanitarian crisis, and ASEAN mediation attempts.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000008",
        "name": "South China Sea Dispute",
        "region": "East Asia",
        "status": "monitoring",
        "description": "Territorial disputes involving China, Philippines, Vietnam, and other ASEAN claimants. US freedom of navigation operations.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000009",
        "name": "Yemen/Houthi Conflict",
        "region": "Middle East",
        "status": "active",
        "description": "Houthi movement disrupting Red Sea shipping, Iranian backing, Saudi coalition involvement, and global trade impact.",
    },
    {
        "id": "10000000-0000-0000-0000-000000000010",
        "name": "Venezuela Political Crisis",
        "region": "South America",
        "status": "monitoring",
        "description": "Disputed elections, opposition movement, economic crisis, and migration waves affecting regional stability.",
    },
]


def seed():
    engine = create_engine(DATABASE_URL)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        for c in CONFLICTS:
            existing = session.execute(
                text("SELECT id FROM conflicts WHERE id = :id"),
                {"id": c["id"]},
            ).fetchone()

            if existing:
                print(f"  [skip] {c['name']} (already exists)")
                continue

            session.execute(
                text("""
                    INSERT INTO conflicts (id, name, region, status, description, created_at, updated_at)
                    VALUES (:id, :name, :region, :status, :description, :now, :now)
                """),
                {**c, "now": now},
            )
            print(f"  [seed] {c['name']}")

        session.commit()
    print(f"\nSeeded {len(CONFLICTS)} conflicts.")


if __name__ == "__main__":
    seed()
