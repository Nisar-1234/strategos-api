"""
AI Chat endpoint — natural language geopolitical analysis.

POST /api/v1/chat        — full response (JSON)
POST /api/v1/chat/stream — Server-Sent Events streaming response
"""

import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import get_settings
from app.services.llm_gateway import call_llm, stream_llm

router = APIRouter()
settings = get_settings()
logger = logging.getLogger("strategos.chat")


class ChatRequest(BaseModel):
    message: str
    conflict_id: UUID | None = None
    session_id: str | None = None


class SourceCitation(BaseModel):
    name: str
    layer: str
    bias_score: float | None = None


class ChatResponse(BaseModel):
    analysis: str
    probabilities: dict[str, float] | None = None
    convergence_score: float | None = None
    sources: list[SourceCitation]
    confidence: str
    session_id: str


async def _gather_signal_context(conflict_id: str | None = None, limit: int = 100) -> tuple[list[dict], list[SourceCitation]]:
    signals = []
    sources_seen: dict[str, SourceCitation] = {}

    async for db in get_db():
        params: dict = {"limit": limit}
        where = "WHERE timestamp >= NOW() - INTERVAL '48 hours'"
        if conflict_id:
            where += " AND conflict_id = :cid"
            params["cid"] = conflict_id

        result = await db.execute(
            text(f"""
                SELECT source_name, layer, normalized_score, confidence, alert_flag,
                       alert_severity, deviation_pct, raw_value, timestamp
                FROM signals
                {where}
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            params,
        )
        for r in result.fetchall():
            signals.append({
                "source": r.source_name,
                "layer": r.layer,
                "score": round(r.normalized_score, 2),
                "confidence": round(r.confidence, 2),
                "alert": r.alert_flag,
                "severity": r.alert_severity,
                "deviation_pct": round(r.deviation_pct, 1) if r.deviation_pct else None,
                "value": str(r.raw_value)[:200],
                "time": r.timestamp.isoformat(),
            })
            key = f"{r.source_name}:{r.layer}"
            if key not in sources_seen:
                sources_seen[key] = SourceCitation(
                    name=r.source_name,
                    layer=r.layer,
                    bias_score=round(r.confidence, 1),
                )
    return signals, list(sources_seen.values())[:10]


async def _get_convergence(conflict_id: str | None) -> float | None:
    if not conflict_id:
        return None
    async for db in get_db():
        result = await db.execute(
            text("SELECT score FROM convergence_scores WHERE conflict_id = :cid ORDER BY timestamp DESC LIMIT 1"),
            {"cid": conflict_id},
        )
        row = result.fetchone()
        return round(row.score, 1) if row else None
    return None


async def _get_conflict_name(conflict_id: str | None) -> str | None:
    if not conflict_id:
        return None
    async for db in get_db():
        result = await db.execute(
            text("SELECT name FROM conflicts WHERE id = :cid"),
            {"cid": conflict_id},
        )
        row = result.fetchone()
        return row.name if row else None
    return None


def _build_system_prompt(signals: list[dict], conflict_name: str | None) -> str:
    signal_summary = json.dumps(signals[:30], indent=2)
    context = f" regarding {conflict_name}" if conflict_name else ""
    return f"""You are STRATEGOS, an AI geopolitical intelligence analyst.
You provide concise, data-driven analysis{context} based on real signal data from 10 independent layers:
L1=News, L2=Social, L3=Shipping, L4=Aviation, L5=Commodities, L6=Currency, L7=Equity, L8=Satellite, L9=Economic, L10=Connectivity.

Recent signal data (last 48 hours):
{signal_summary}

Rules:
- Always cite which signal layers support your conclusions.
- Provide probability estimates when asked about outcomes.
- Be direct and analytical. Avoid speculation beyond what signals support.
- Mention conflicting signals when they exist.
- If data is insufficient, say so explicitly.
- Never use emoji in your response."""


def _compute_probabilities(signals: list[dict]) -> dict[str, float] | None:
    if not signals:
        return None
    avg_score = sum(s["score"] for s in signals) / len(signals)
    n_alerts = sum(1 for s in signals if s["alert"])
    alert_factor = min(0.2, n_alerts * 0.02)
    esc = round(max(0.1, min(0.8, 0.5 - avg_score * 0.3 + alert_factor)), 2)
    neg = round(max(0.1, min(0.6, 0.3 + avg_score * 0.2)), 2)
    sta = round(max(0.05, min(0.5, 1.0 - esc - neg - 0.1)), 2)
    res = round(max(0.0, 1.0 - esc - neg - sta), 2)
    return {"escalation": esc, "negotiation": neg, "stalemate": sta, "resolution": res}


@router.post("/chat", response_model=ChatResponse)
async def chat_analysis(request: ChatRequest):
    """Natural language geopolitical query — full JSON response."""
    session_id = request.session_id or str(uuid4())
    conflict_id_str = str(request.conflict_id) if request.conflict_id else None

    conflict_name = await _get_conflict_name(conflict_id_str)
    signals, sources = await _gather_signal_context(conflict_id_str)
    convergence = await _get_convergence(conflict_id_str)

    system_prompt = _build_system_prompt(signals, conflict_name)
    signal_context = ""
    result = await call_llm(request.message, system_prompt=system_prompt, signal_context=signal_context)
    analysis = result["response"]

    n_layers = len(set(s["layer"] for s in signals))
    confidence = "HIGH" if len(signals) > 50 and n_layers >= 4 else "MEDIUM" if len(signals) > 10 else "LOW"

    return ChatResponse(
        analysis=analysis,
        probabilities=_compute_probabilities(signals),
        convergence_score=convergence,
        sources=sources or [SourceCitation(name="No recent signals", layer="N/A")],
        confidence=confidence,
        session_id=session_id,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming SSE variant — emits text chunks as they arrive from the LLM."""
    conflict_id_str = str(request.conflict_id) if request.conflict_id else None
    signals, _ = await _gather_signal_context(conflict_id_str, limit=60)
    conflict_name = await _get_conflict_name(conflict_id_str)
    system_prompt = _build_system_prompt(signals, conflict_name)

    async def _generate():
        async for chunk in stream_llm(request.message, system_prompt=system_prompt):
            data = json.dumps({"chunk": chunk})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
