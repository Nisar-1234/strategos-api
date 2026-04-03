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


async def _gather_signal_context(conflict_id: str | None = None, limit: int = 100) -> tuple[list[dict], list[SourceCitation]]:
    """Pull recent signals from DB to feed as context to the LLM."""
    signals = []
    sources_seen: dict[str, SourceCitation] = {}

    async for db in get_db():
        result = await db.execute(
            text("""
                SELECT source_name, layer, normalized_score, confidence, alert_flag,
                       raw_value, timestamp
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
"""


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


async def _call_llm(system_prompt: str, user_message: str) -> str:
    """Call LLM via LangChain. Falls back gracefully if no API key."""
    if settings.ANTHROPIC_API_KEY:
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
        except Exception as e:
            pass

    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.LLM_FALLBACK_MODEL,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
            )
            response = await llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "human", "content": user_message},
            ])
            return strip_emoji(response.content)
        except Exception:
            pass

    return _generate_signal_summary(system_prompt, user_message)


def _generate_signal_summary(system_prompt: str, user_message: str) -> str:
    """Generate a useful response directly from signal data when no LLM key is configured."""
    return (
        "**Signal-Based Analysis** (LLM not configured — raw signal summary):\n\n"
        "I've aggregated the latest signals from all available layers. "
        "Configure ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env for full AI analysis.\n\n"
        "The raw signal data shows recent activity across multiple layers. "
        "Check the sources panel for individual layer readings."
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_analysis(request: ChatRequest):
    """
    Natural language geopolitical query interface.
    AI responses are powered by all 10 signal layers.
    Every source citation includes its bias score.
    """
    session_id = request.session_id or str(uuid4())
    conflict_id_str = str(request.conflict_id) if request.conflict_id else None

    conflict_name = await _get_conflict_name(conflict_id_str)
    signals, sources = await _gather_signal_context(conflict_id_str)
    convergence = await _get_convergence(conflict_id_str)

    system_prompt = _build_system_prompt(signals, conflict_name)
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
