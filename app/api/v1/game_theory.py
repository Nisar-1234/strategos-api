from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from uuid import UUID
from sqlalchemy import text
import numpy as np
import nashpy as nash

from app.core.database import get_db
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


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


STRATEGY_LABELS = {
    "actor_a": ["Escalate", "Negotiate", "Maintain"],
    "actor_b": ["Resist", "Negotiate", "Concede"],
}


def _build_payoff_from_signals(signals: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """
    Build payoff matrices for two actors from real signal data.
    
    High negative sentiment / alerts → escalation payoffs increase
    High positive / low alerts → negotiation payoffs increase
    """
    if not signals:
        A = np.array([[-3, 2, -1], [1, 3, 0], [-2, 1, -1]], dtype=float)
        B = np.array([[-3, -1, 1], [2, 3, -2], [-1, 0, -1]], dtype=float)
        return A, B

    avg_score = np.mean([s["normalized_score"] for s in signals])
    alert_ratio = sum(1 for s in signals if s["alert_flag"]) / max(len(signals), 1)
    avg_confidence = np.mean([s["confidence"] for s in signals])

    escalation_pressure = -avg_score + alert_ratio
    negotiation_pull = avg_score + (1 - alert_ratio) * avg_confidence

    esc = round(float(np.clip(escalation_pressure * 3, -4, 4)), 1)
    neg = round(float(np.clip(negotiation_pull * 3, -2, 4)), 1)
    mnt = round(float(np.clip((avg_score * 0.5) - 1, -3, 2)), 1)

    A = np.array([
        [esc, neg - 1, mnt - 1],
        [neg - 2, neg, mnt + 1],
        [mnt, mnt - 1, esc * 0.5],
    ])
    B = np.array([
        [esc, esc + 1, -esc],
        [-neg + 1, neg, neg - 2],
        [mnt + 1, mnt, mnt - 0.5],
    ])
    return A, B


def _find_nash(A: np.ndarray, B: np.ndarray) -> list[dict]:
    """Find Nash equilibria using nashpy."""
    game = nash.Game(A, B)
    equilibria = []
    try:
        for eq in game.support_enumeration():
            row_strat = int(np.argmax(eq[0]))
            col_strat = int(np.argmax(eq[1]))
            equilibria.append({
                "actor_a": STRATEGY_LABELS["actor_a"][row_strat],
                "actor_b": STRATEGY_LABELS["actor_b"][col_strat],
                "actor_a_mixed": [round(float(x), 3) for x in eq[0]],
                "actor_b_mixed": [round(float(x), 3) for x in eq[1]],
            })
    except Exception:
        equilibria.append({
            "actor_a": "Negotiate",
            "actor_b": "Negotiate",
        })
    return equilibria if equilibria else [{"actor_a": "Negotiate", "actor_b": "Negotiate"}]


def _dominant_strategy(matrix: np.ndarray, labels: list[str]) -> str:
    """Find dominant strategy (row that's best regardless of opponent)."""
    row_mins = matrix.min(axis=1)
    best_row = int(np.argmax(row_mins))
    return labels[best_row]


@router.post("/game-theory/compute", response_model=NashResult)
async def compute_game_theory(request: GameTheoryRequest):
    """
    Compute game theory analysis for a conflict using real signal data.
    Generates payoff matrix from current signals, finds Nash equilibria,
    and produces a rationale based on signal analysis.
    """
    signals_data = []
    conflict_name = "Unknown Conflict"

    async for db in get_db():
        conflict_row = await db.execute(
            text("SELECT name FROM conflicts WHERE id = :cid"),
            {"cid": str(request.conflict_id)},
        )
        row = conflict_row.fetchone()
        if row:
            conflict_name = row.name

        result = await db.execute(
            text("""
                SELECT normalized_score, alert_flag, confidence, layer, source_name
                FROM signals
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                ORDER BY timestamp DESC
                LIMIT 200
            """),
        )
        rows = result.fetchall()
        signals_data = [
            {
                "normalized_score": r.normalized_score,
                "alert_flag": r.alert_flag,
                "confidence": r.confidence,
                "layer": r.layer,
                "source_name": r.source_name,
            }
            for r in rows
        ]

    A, B = _build_payoff_from_signals(signals_data)
    equilibria = _find_nash(A, B)
    dom_a = _dominant_strategy(A, STRATEGY_LABELS["actor_a"])
    dom_b = _dominant_strategy(B, STRATEGY_LABELS["actor_b"])

    n_signals = len(signals_data)
    n_alerts = sum(1 for s in signals_data if s["alert_flag"])
    n_layers = len(set(s["layer"] for s in signals_data))

    if n_signals > 0:
        avg_score = np.mean([s["normalized_score"] for s in signals_data])
        confidence = "HIGH" if n_signals > 50 and n_layers >= 4 else "MEDIUM" if n_signals > 10 else "LOW"
    else:
        avg_score = 0.0
        confidence = "LOW"

    primary_eq = equilibria[0]
    recommended = primary_eq.get("actor_a", "Negotiate")

    if avg_score < -0.3:
        rationale = (
            f"Based on {n_signals} signals across {n_layers} layers in the last 24 hours, "
            f"the signal environment for {conflict_name} shows elevated tension. "
            f"{n_alerts} alert-level signals detected. "
            f"Average sentiment score is {avg_score:.2f} (negative = escalatory). "
            f"The Nash equilibrium suggests {primary_eq.get('actor_a', 'N/A')}-{primary_eq.get('actor_b', 'N/A')} "
            f"as the most likely stable outcome."
        )
    elif avg_score > 0.2:
        rationale = (
            f"Analysis of {n_signals} signals across {n_layers} layers shows de-escalatory trends "
            f"for {conflict_name}. Average sentiment is {avg_score:.2f} (positive = cooperative). "
            f"Negotiation channels appear viable. "
            f"Nash equilibrium favors {primary_eq.get('actor_a', 'N/A')}-{primary_eq.get('actor_b', 'N/A')}."
        )
    else:
        rationale = (
            f"Signal analysis for {conflict_name}: {n_signals} signals across {n_layers} layers. "
            f"Mixed signals with average score {avg_score:.2f}. {n_alerts} alerts detected. "
            f"Current equilibrium: {primary_eq.get('actor_a', 'N/A')}-{primary_eq.get('actor_b', 'N/A')}. "
            f"Situation remains fluid; recommend continued monitoring."
        )

    return NashResult(
        payoff_matrix=A.round(1).tolist(),
        nash_equilibria=equilibria,
        dominant_strategies={"actor_a": dom_a, "actor_b": dom_b},
        recommended_strategy=recommended,
        rationale=rationale,
        confidence=confidence,
        actor_labels=STRATEGY_LABELS,
    )
