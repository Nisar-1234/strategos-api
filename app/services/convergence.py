"""
Convergence Score Engine

Score = SUM(Layer Weight x Layer Direction Score) / SUM(Layer Weights)

Where:
- Layer Direction Score in {-1 (divergent), 0 (neutral), +1 (convergent)} x magnitude (0.0 - 1.0)
- Weights: L1/L2 = 0.6, L5/L6/L7 = 0.9, L3/L4/L8/L10 = 1.2
"""

from app.core.config import get_settings

settings = get_settings()


def calculate_convergence_score(
    layer_signals: dict[str, dict],
) -> tuple[float, dict]:
    """
    Calculate convergence score from per-layer signal summaries.

    Args:
        layer_signals: Dict keyed by layer ID (L1-L10), each containing:
            - direction: float (-1.0 to +1.0) indicating signal direction
            - magnitude: float (0.0 to 1.0) indicating signal strength
            - active: bool indicating if this layer has fresh data

    Returns:
        Tuple of (score 0-10, per-layer contributions dict)
    """
    weights = settings.LAYER_WEIGHTS
    total_weighted_score = 0.0
    total_weight = 0.0
    contributions = {}

    for layer_id, signal in layer_signals.items():
        if not signal.get("active", False):
            contributions[layer_id] = {"weight": 0, "contribution": 0, "status": "offline"}
            continue

        weight = weights.get(layer_id, 0.9)
        direction = signal.get("direction", 0.0)
        magnitude = signal.get("magnitude", 0.0)

        layer_score = direction * magnitude
        weighted = weight * layer_score

        total_weighted_score += weighted
        total_weight += weight

        contributions[layer_id] = {
            "weight": weight,
            "direction": direction,
            "magnitude": magnitude,
            "contribution": weighted,
            "status": "alert" if abs(layer_score) > 0.7 else "active",
        }

    if total_weight == 0:
        return 0.0, contributions

    raw_score = total_weighted_score / total_weight
    normalized = (raw_score + 1.0) / 2.0 * 10.0
    final_score = max(0.0, min(10.0, round(normalized, 1)))

    return final_score, contributions
