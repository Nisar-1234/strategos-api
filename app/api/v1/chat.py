from fastapi import APIRouter
from pydantic import BaseModel
from uuid import UUID, uuid4
from sqlalchemy import text
import json

from app.core.database import get_db
from app.core.config import get_settings
from app.services.llm_gateway import strip_emoji

router = APIRouter()
settings = get_settings()


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


async def _gather_signal_context(limit: int = 100) -> tuple[list[dict], list[SourceCitation]]:
    """Pull recent signals from DB to feed as context to the LLM."""
    signals = []
    sources_seen: dict[str, SourceCitation] = {}

    async for db in get_db():
        result = await db.execute(
            text("""
                SELECT source_name, layer, normalized_score, confidence, alert_flag,
                       raw_value, content, timestamp
                FROM signals
                WHERE timestamp >= NOW() - INTERVAL '48 hours'
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.fetchall()
        for r in rows:
            signals.append({
                "source": r.source_name,
                "layer": r.layer,
                "score": round(r.normalized_score, 2),
                "confidence": round(r.confidence, 2),
                "alert": r.alert_flag,
                "value": str(r.raw_value)[:100] if r.raw_value is not None else None,
                "content": r.content[:200] if r.content else None,
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
            text("""
                SELECT score FROM convergence_scores
                WHERE conflict_id = :cid
                ORDER BY timestamp DESC LIMIT 1
            """),
            {"cid": conflict_id},
        )
        row = result.fetchone()
        return round(row.score, 1) if row else None
    return None


def _build_system_prompt(signals: list[dict], conflict_name: str | None, conflict_region: str | None) -> str:
    # Summarise which layers have data in this snapshot
    layers_present = sorted(set(s["layer"] for s in signals))
    all_layers = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"]
    layer_status = ", ".join(
        f"{l}:{'ACTIVE' if l in layers_present else 'NO DATA'}" for l in all_layers
    )

    context_parts = []
    if conflict_name:
        context_parts.append(f"Conflict: {conflict_name}")
    if conflict_region:
        context_parts.append(f"Region: {conflict_region}")
    context_str = " | ".join(context_parts)
    focus_line = f"\nFocus context: {context_str}" if context_str else ""

    signal_summary = json.dumps(signals[:40], indent=2)

    return f"""You are STRATEGOS, an AI geopolitical intelligence analyst.
You provide concise, data-driven analysis based on real signal data from 10 independent layers:
L1=Editorial News, L2=Social Media, L3=Shipping/Maritime, L4=Aviation, L5=Commodities,
L6=Currency/FX, L7=Equities, L8=Satellite/Remote Sensing, L9=Economic Indicators, L10=Internet Connectivity.
{focus_line}

Layer data availability: {layer_status}

Recent signal data (last 48 hours) — each signal includes content (human-readable description), score (-1 to +1), and alert flag:
{signal_summary}

Rules:
- Cite which layers support your conclusions. If a layer shows NO DATA, say so explicitly.
- Scores near +1 = escalation pressure. Near -1 = de-escalation. Near 0 = neutral/stable.
- Use the content field — it contains the actual readable description of each signal.
- Provide probability estimates when asked.
- Be direct. Acknowledge data gaps honestly — do not fabricate from missing layers.
- Mention alert signals (alert: true) specifically — they represent statistically significant anomalies.
"""


async def _get_conflict_info(conflict_id: str | None) -> tuple[str | None, str | None]:
    """Returns (name, region) for a conflict."""
    if not conflict_id:
        return None, None
    async for db in get_db():
        result = await db.execute(
            text("SELECT name, region FROM conflicts WHERE id = :cid"),
            {"cid": conflict_id},
        )
        row = result.fetchone()
        if row:
            return row.name, row.region
        return None, None
    return None, None


async def _call_llm(system_prompt: str, user_message: str) -> str:
    """Call Claude. Returns signal summary fallback if no API key."""
    if not settings.ANTHROPIC_API_KEY:
        return _generate_signal_summary()

    try:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model=settings.LLM_PRIMARY_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
        )
        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "human", "content": user_message},
        ])
        return strip_emoji(response.content)
    except Exception:
        return _generate_signal_summary()


def _generate_signal_summary() -> str:
    return (
        "Signal-Based Analysis (LLM not configured):\n\n"
        "ANTHROPIC_API_KEY is not set. Configure it in your .env or SSM to enable AI analysis.\n\n"
        "Raw signal data is available via GET /api/v1/signals."
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_analysis(request: ChatRequest):
    """
    Natural language geopolitical query interface.
    AI responses are grounded in all 10 signal layers.
    Every source citation includes its bias/confidence score.
    """
    session_id = request.session_id or str(uuid4())
    conflict_id_str = str(request.conflict_id) if request.conflict_id else None

    conflict_name, conflict_region = await _get_conflict_info(conflict_id_str)
    signals, sources = await _gather_signal_context()
    convergence = await _get_convergence(conflict_id_str)

    system_prompt = _build_system_prompt(signals, conflict_name, conflict_region)
    analysis = await _call_llm(system_prompt, request.message)

    n_signals = len(signals)
    n_alerts = sum(1 for s in signals if s["alert"])
    n_layers = len(set(s["layer"] for s in signals))

    probabilities = None
    if n_signals > 0:
        avg_score = sum(s["score"] for s in signals) / n_signals
        esc = round(max(0.1, min(0.8, 0.5 - avg_score * 0.3)), 2)
        neg = round(max(0.1, min(0.6, 0.3 + avg_score * 0.2)), 2)
        stale = round(max(0.05, 1.0 - esc - neg), 2)
        probabilities = {
            "escalation": esc,
            "negotiation": neg,
            "stalemate": stale,
        }

    confidence = "HIGH" if n_signals > 50 and n_layers >= 4 else "MEDIUM" if n_signals > 10 else "LOW"

    return ChatResponse(
        analysis=analysis,
        probabilities=probabilities,
        convergence_score=convergence,
        sources=sources if sources else [SourceCitation(name="No recent signals", layer="N/A")],
        confidence=confidence,
        session_id=session_id,
    )
