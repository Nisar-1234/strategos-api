"""Tests for FastAPI endpoints using TestClient."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_returns_status_healthy(self):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_returns_service_name(self):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert data["service"] == "strategos-api"

    def test_health_returns_version(self):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert "version" in data

    def test_health_returns_timestamp(self):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert "timestamp" in data

    def test_health_returns_layer_status(self):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert "layers" in data
        assert "L1_editorial" in data["layers"]
        assert data["layers"]["L1_editorial"] == "ready"


class TestSignalsEndpoint:
    def test_list_signals_returns_200(self):
        resp = client.get("/api/v1/signals")
        assert resp.status_code == 200

    def test_list_signals_returns_list(self):
        resp = client.get("/api/v1/signals")
        assert isinstance(resp.json(), list)

    def test_list_signals_with_layer_filter(self):
        resp = client.get("/api/v1/signals", params={"layer": "L5"})
        assert resp.status_code == 200

    def test_list_signals_with_alert_filter(self):
        resp = client.get("/api/v1/signals", params={"alert_only": True})
        assert resp.status_code == 200

    def test_signal_feed_returns_200(self):
        resp = client.get("/api/v1/signals/feed")
        assert resp.status_code == 200


class TestPredictionsEndpoint:
    def test_list_predictions_returns_200(self):
        resp = client.get("/api/v1/predictions")
        assert resp.status_code == 200

    def test_list_predictions_returns_list(self):
        resp = client.get("/api/v1/predictions")
        assert isinstance(resp.json(), list)

    def test_list_predictions_with_confidence_filter(self):
        resp = client.get("/api/v1/predictions", params={"confidence": "HIGH"})
        assert resp.status_code == 200


class TestConflictsEndpoint:
    def test_list_conflicts_returns_200(self):
        resp = client.get("/api/v1/conflicts")
        assert resp.status_code == 200

    def test_list_conflicts_returns_list(self):
        resp = client.get("/api/v1/conflicts")
        assert isinstance(resp.json(), list)

    def test_list_conflicts_with_status_filter(self):
        resp = client.get("/api/v1/conflicts", params={"status": "active"})
        assert resp.status_code == 200


class TestGameTheoryEndpoint:
    def test_compute_returns_200(self):
        resp = client.post(
            "/api/v1/game-theory/compute",
            json={"conflict_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200

    def test_compute_returns_nash_result(self):
        resp = client.post(
            "/api/v1/game-theory/compute",
            json={"conflict_id": "00000000-0000-0000-0000-000000000001"},
        )
        data = resp.json()
        assert "payoff_matrix" in data
        assert "nash_equilibria" in data
        assert "dominant_strategies" in data
        assert "recommended_strategy" in data
        assert "confidence" in data

    def test_compute_payoff_matrix_structure(self):
        resp = client.post(
            "/api/v1/game-theory/compute",
            json={"conflict_id": "00000000-0000-0000-0000-000000000001"},
        )
        data = resp.json()
        matrix = data["payoff_matrix"]
        assert len(matrix) == 2
        assert len(matrix[0]) == 2


class TestChatEndpoint:
    def test_chat_returns_200(self):
        resp = client.post(
            "/api/v1/chat",
            json={"message": "What is the current situation in Gaza?"},
        )
        assert resp.status_code == 200

    def test_chat_returns_analysis(self):
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Analyze Ukraine conflict"},
        )
        data = resp.json()
        assert "analysis" in data
        assert "sources" in data
        assert "confidence" in data
        assert "session_id" in data

    def test_chat_returns_source_citations(self):
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Gaza analysis"},
        )
        data = resp.json()
        sources = data["sources"]
        assert len(sources) > 0
        assert "name" in sources[0]
        assert "layer" in sources[0]

    def test_chat_invalid_request(self):
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422


class TestCORSHeaders:
    def test_cors_allows_localhost(self):
        resp = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200

    def test_docs_available(self):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_available(self):
        resp = client.get("/redoc")
        assert resp.status_code == 200
