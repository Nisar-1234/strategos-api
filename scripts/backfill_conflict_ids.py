"""
One-time script: backfill conflict_id on existing signals using conflict_router.

Run once after deploy:
  docker exec strategos-worker python scripts/backfill_conflict_ids.py

Updates signals in batches of 500. Skips signals that already have a conflict_id.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.workers.conflict_router import resolve

settings = get_settings()
engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=2, max_overflow=0)

BATCH = 500

def main():
    updated = 0
    skipped = 0

    with Session(engine) as session:
        # Get total count
        total = session.execute(
            text("SELECT COUNT(*) FROM signals WHERE conflict_id IS NULL")
        ).scalar()
        print(f"Signals without conflict_id: {total}")

        offset = 0
        while True:
            rows = session.execute(
                text("""
                    SELECT id, layer, source_name, content, latitude, longitude
                    FROM signals
                    WHERE conflict_id IS NULL
                    ORDER BY timestamp DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": BATCH, "offset": offset},
            ).fetchall()

            if not rows:
                break

            updates = []
            for r in rows:
                sig = {
                    "source_name": r.source_name or "",
                    "content": r.content or "",
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                }
                conflict_id = resolve(sig)
                if conflict_id:
                    updates.append({"id": str(r.id), "cid": conflict_id})
                else:
                    skipped += 1

            if updates:
                for u in updates:
                    session.execute(
                        text("UPDATE signals SET conflict_id = :cid WHERE id = :id::uuid"),
                        u,
                    )
                session.commit()
                updated += len(updates)

            offset += BATCH
            print(f"  Processed {offset}/{total} — linked {updated}, unmatched {skipped}")

    print(f"\nDone. Linked: {updated} | Unmatched: {skipped}")

if __name__ == "__main__":
    main()
