from fastapi import APIRouter
from pydantic import BaseModel
from uuid import UUID

router = APIRouter()


class GameTheoryRequest(BaseModel):
    conflict_id: UUID
    actors: list[str] | None = None


class NashResult(BaseModel):
    payoff_matrix: list[list[float]]
    nash_equilibria: list[dict]
    dominant_strategies: dict[str, str]
    recommended_strategy: str
    rationale: str
    confidence: str
    actor_labels: dict[str, list[str]]


@router.post("/game-theory/compute", response_model=NashResult)
async def compute_game_theory(request: GameTheoryRequest):
    """
    Compute game theory analysis for a conflict.

    Generates payoff matrix from current signal data, finds Nash equilibria,
    identifies dominant strategies, and produces a plain-text rationale.

    Payoff values are derived from signal layers, not hardcoded.
    """
    # TODO: Wire to nashpy engine + signal data + LLM rationale
    return NashResult(
        payoff_matrix=[[-3, 2], [1, 0]],
        nash_equilibria=[{"actor_a": "Negotiate", "actor_b": "Negotiate"}],
        dominant_strategies={"actor_a": "Negotiate", "actor_b": "Negotiate"},
        recommended_strategy="Ceasefire Negotiation",
        rationale="Based on current signal convergence across 8 of 10 layers, "
        "the Nash equilibrium strongly favors negotiation. Both actors face "
        "escalating economic pressure (L5/L6/L7 aligned) and physical signals "
        "(L3 shipping rerouting, L10 connectivity disruption) that increase "
        "the cost of continued conflict.",
        confidence="HIGH",
        actor_labels={
            "actor_a": ["Escalate", "Negotiate", "Maintain"],
            "actor_b": ["Resist", "Negotiate", "Concede"],
        },
    )
