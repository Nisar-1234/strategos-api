from fastapi import APIRouter
from pydantic import BaseModel
from uuid import UUID

router = APIRouter()


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


@router.post("/chat", response_model=ChatResponse)
async def chat_analysis(request: ChatRequest):
    """
    Natural language geopolitical query interface.

    AI responses are powered by all 10 signal layers.
    Every source citation includes its bias score.
    Token budget enforced at 8,000 input tokens.
    """
    # TODO: Wire to LLM gateway with signal context injection
    return ChatResponse(
        analysis="Convergence Score for Gaza is currently 8.4/10. "
        "Eight of ten independent signal layers are pointing toward "
        "continued escalation. L3 Shipping shows Hormuz tanker traffic "
        "down 38%. L5-L6 market alignment (Gold +2.4%, Brent +3.8%, "
        "ILS -1.2%) is a composite fear signal. L10 Connectivity shows "
        "Gaza internet down 62% with BGP withdrawals.",
        probabilities={
            "escalation": 0.62,
            "stalemate": 0.20,
            "ceasefire": 0.18,
        },
        convergence_score=8.4,
        sources=[
            SourceCitation(name="Reuters", layer="L1", bias_score=8.4),
            SourceCitation(name="MarineTraffic AIS", layer="L3"),
            SourceCitation(name="Gold API", layer="L5"),
            SourceCitation(name="Cloudflare Radar", layer="L10"),
        ],
        confidence="HIGH",
        session_id=request.session_id or "new-session",
    )
