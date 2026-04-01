"""
Settings API — key-value configuration store.

Manages API keys, LLM config, user preferences, and skills.
Stores in a simple key-value table; secrets are masked on read.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from sqlalchemy import text

from app.core.database import get_db

router = APIRouter()


class SettingValue(BaseModel):
    key: str
    value: str
    category: str = "general"


class SettingResponse(BaseModel):
    key: str
    value: str
    category: str
    updated_at: str


SECRET_KEYS = {"api_key", "token", "secret", "password"}


def _mask_value(key: str, value: str) -> str:
    """Mask sensitive values — show only last 4 chars."""
    lower_key = key.lower()
    if any(s in lower_key for s in SECRET_KEYS) and len(value) > 8:
        return "*" * (len(value) - 4) + value[-4:]
    return value


@router.get("/settings", response_model=list[SettingResponse])
async def list_settings(category: str | None = None):
    """List all stored settings, with secrets masked."""
    async for db in get_db():
        await _ensure_table(db)
        query = "SELECT key, value, category, updated_at FROM app_settings"
        params: dict = {}
        if category:
            query += " WHERE category = :category"
            params["category"] = category
        query += " ORDER BY category, key"

        result = await db.execute(text(query), params)
        rows = result.fetchall()
        return [
            SettingResponse(
                key=r.key,
                value=_mask_value(r.key, r.value),
                category=r.category,
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
            )
            for r in rows
        ]
    return []


@router.put("/settings/{key}")
async def upsert_setting(key: str, body: SettingValue):
    """Create or update a setting."""
    now = datetime.now(timezone.utc)
    async for db in get_db():
        await _ensure_table(db)
        await db.execute(
            text("""
                INSERT INTO app_settings (key, value, category, updated_at)
                VALUES (:key, :value, :category, :now)
                ON CONFLICT (key) DO UPDATE
                SET value = :value, category = :category, updated_at = :now
            """),
            {"key": key, "value": body.value, "category": body.category, "now": now},
        )
        await db.commit()
        return {"status": "ok", "key": key}
    raise HTTPException(status_code=500, detail="Database unavailable")


@router.delete("/settings/{key}")
async def delete_setting(key: str):
    """Remove a setting."""
    async for db in get_db():
        await _ensure_table(db)
        result = await db.execute(
            text("DELETE FROM app_settings WHERE key = :key"),
            {"key": key},
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Setting not found")
        return {"status": "deleted", "key": key}
    raise HTTPException(status_code=500, detail="Database unavailable")


@router.get("/settings/api-keys")
async def list_api_keys():
    """Get all API key settings (masked)."""
    async for db in get_db():
        await _ensure_table(db)
        result = await db.execute(
            text("SELECT key, value, category, updated_at FROM app_settings WHERE category = 'api_keys' ORDER BY key")
        )
        rows = result.fetchall()
        return [
            SettingResponse(
                key=r.key, value=_mask_value(r.key, r.value),
                category=r.category,
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
            )
            for r in rows
        ]
    return []


@router.get("/settings/llm")
async def get_llm_settings():
    """Get LLM configuration."""
    async for db in get_db():
        await _ensure_table(db)
        result = await db.execute(
            text("SELECT key, value, category, updated_at FROM app_settings WHERE category = 'llm' ORDER BY key")
        )
        rows = result.fetchall()
        return [
            SettingResponse(
                key=r.key, value=r.value,
                category=r.category,
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
            )
            for r in rows
        ]
    return []


@router.get("/settings/preferences")
async def get_preferences():
    """Get user preferences."""
    async for db in get_db():
        await _ensure_table(db)
        result = await db.execute(
            text("SELECT key, value, category, updated_at FROM app_settings WHERE category = 'preferences' ORDER BY key")
        )
        rows = result.fetchall()
        return [
            SettingResponse(
                key=r.key, value=r.value,
                category=r.category,
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
            )
            for r in rows
        ]
    return []


async def _ensure_table(db):
    """Create the app_settings table if it doesn't exist yet."""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            category VARCHAR(50) NOT NULL DEFAULT 'general',
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await db.commit()
