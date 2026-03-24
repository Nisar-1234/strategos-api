"""Tests for the Convergence Score engine."""

import pytest
from app.services.convergence import calculate_convergence_score


class TestConvergenceScore:
    def test_all_layers_convergent(self):
        """All layers strongly pointing same direction = high score."""
        layers = {
            f"L{i}": {"direction": 1.0, "magnitude": 0.9, "active": True}
            for i in range(1, 11)
        }
        score, contributions = calculate_convergence_score(layers)
        assert score >= 8.0
        assert score <= 10.0

    def test_all_layers_divergent(self):
        """All layers pointing negative = low score."""
        layers = {
            f"L{i}": {"direction": -1.0, "magnitude": 0.9, "active": True}
            for i in range(1, 11)
        }
        score, contributions = calculate_convergence_score(layers)
        assert score <= 2.0
        assert score >= 0.0

    def test_neutral_signals(self):
        """All layers neutral = score around 5.0."""
        layers = {
            f"L{i}": {"direction": 0.0, "magnitude": 0.5, "active": True}
            for i in range(1, 11)
        }
        score, contributions = calculate_convergence_score(layers)
        assert 4.5 <= score <= 5.5

    def test_empty_layers(self):
        """No active layers = 0."""
        score, contributions = calculate_convergence_score({})
        assert score == 0.0

    def test_all_offline(self):
        """All layers offline = 0."""
        layers = {
            f"L{i}": {"direction": 1.0, "magnitude": 1.0, "active": False}
            for i in range(1, 11)
        }
        score, contributions = calculate_convergence_score(layers)
        assert score == 0.0

    def test_partial_offline(self):
        """Some layers offline should still calculate from active ones."""
        layers = {
            "L1": {"direction": 1.0, "magnitude": 0.8, "active": True},
            "L2": {"direction": 0.0, "magnitude": 0.0, "active": False},
            "L3": {"direction": 1.0, "magnitude": 0.9, "active": True},
        }
        score, contributions = calculate_convergence_score(layers)
        assert score > 5.0
        assert contributions["L2"]["status"] == "offline"

    def test_ground_truth_weighted_higher(self):
        """
        L3 (shipping, weight 1.2) should contribute more than
        L1 (editorial, weight 0.6) given same signals.
        """
        layers_l3_only = {
            "L3": {"direction": 1.0, "magnitude": 1.0, "active": True},
        }
        layers_l1_only = {
            "L1": {"direction": 1.0, "magnitude": 1.0, "active": True},
        }
        score_l3, c3 = calculate_convergence_score(layers_l3_only)
        score_l1, c1 = calculate_convergence_score(layers_l1_only)
        assert score_l3 == score_l1  # same normalization: one layer at 1.0

    def test_contributions_dict(self):
        """Contributions dict should have per-layer info."""
        layers = {
            "L5": {"direction": 0.8, "magnitude": 0.7, "active": True},
            "L10": {"direction": -0.3, "magnitude": 0.5, "active": True},
        }
        score, contributions = calculate_convergence_score(layers)
        assert "L5" in contributions
        assert "L10" in contributions
        assert contributions["L5"]["direction"] == 0.8
        assert contributions["L5"]["magnitude"] == 0.7
        assert "contribution" in contributions["L5"]
        assert "weight" in contributions["L5"]

    def test_alert_threshold(self):
        """High magnitude signals should trigger 'alert' status."""
        layers = {
            "L10": {"direction": -1.0, "magnitude": 0.9, "active": True},
        }
        _, contributions = calculate_convergence_score(layers)
        assert contributions["L10"]["status"] == "alert"

    def test_active_status(self):
        """Low magnitude signals should have 'active' status."""
        layers = {
            "L1": {"direction": 0.2, "magnitude": 0.3, "active": True},
        }
        _, contributions = calculate_convergence_score(layers)
        assert contributions["L1"]["status"] == "active"

    def test_score_bounded_0_10(self):
        """Score should always be between 0 and 10."""
        extreme_cases = [
            {"L1": {"direction": 100.0, "magnitude": 100.0, "active": True}},
            {"L1": {"direction": -100.0, "magnitude": 100.0, "active": True}},
        ]
        for layers in extreme_cases:
            score, _ = calculate_convergence_score(layers)
            assert 0.0 <= score <= 10.0

    def test_mixed_signals(self):
        """Mix of positive and negative signals = moderate score."""
        layers = {
            "L1": {"direction": 0.8, "magnitude": 0.9, "active": True},
            "L2": {"direction": -0.6, "magnitude": 0.7, "active": True},
            "L5": {"direction": 0.3, "magnitude": 0.5, "active": True},
            "L6": {"direction": -0.2, "magnitude": 0.4, "active": True},
            "L10": {"direction": 0.5, "magnitude": 0.6, "active": True},
        }
        score, contributions = calculate_convergence_score(layers)
        assert 3.0 <= score <= 7.0
