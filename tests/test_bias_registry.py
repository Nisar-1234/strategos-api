"""Tests for the source bias registry seed data."""

import pytest
from app.services.bias_registry import SEED_SOURCES, SEED_CONFLICTS


class TestSeedSources:
    def test_has_sources(self):
        assert len(SEED_SOURCES) > 0

    def test_all_sources_have_required_fields(self):
        required = {"name", "layer", "ownership_type", "credibility_score", "political_lean", "agenda_flags"}
        for src in SEED_SOURCES:
            for field in required:
                assert field in src, f"Missing {field} in source {src.get('name', 'unknown')}"

    def test_credibility_score_range(self):
        for src in SEED_SOURCES:
            assert 0.0 <= src["credibility_score"] <= 10.0, f"Invalid credibility for {src['name']}"

    def test_political_lean_range(self):
        for src in SEED_SOURCES:
            assert -5.0 <= src["political_lean"] <= 5.0, f"Invalid lean for {src['name']}"

    def test_valid_layer_ids(self):
        valid = {f"L{i}" for i in range(1, 11)}
        for src in SEED_SOURCES:
            assert src["layer"] in valid, f"Invalid layer {src['layer']} for {src['name']}"

    def test_valid_ownership_types(self):
        valid = {"state", "corporate", "independent", "public"}
        for src in SEED_SOURCES:
            assert src["ownership_type"] in valid, f"Invalid ownership for {src['name']}"

    def test_has_wire_services(self):
        names = {s["name"] for s in SEED_SOURCES}
        assert "Reuters" in names
        assert "Associated Press" in names

    def test_has_state_media(self):
        state_sources = [s for s in SEED_SOURCES if s["ownership_type"] == "state"]
        assert len(state_sources) >= 3

    def test_state_media_lower_credibility(self):
        for src in SEED_SOURCES:
            if src["ownership_type"] == "state":
                assert src["credibility_score"] <= 7.0, f"State media {src['name']} should have lower credibility"

    def test_unique_names(self):
        names = [s["name"] for s in SEED_SOURCES]
        assert len(names) == len(set(names)), "Duplicate source names found"

    def test_has_ground_truth_sources(self):
        ground_truth_layers = {"L3", "L4", "L5", "L6", "L10"}
        layers = {s["layer"] for s in SEED_SOURCES}
        overlap = layers & ground_truth_layers
        assert len(overlap) >= 3


class TestSeedConflicts:
    def test_has_conflicts(self):
        assert len(SEED_CONFLICTS) >= 5

    def test_all_conflicts_have_required_fields(self):
        required = {"name", "region", "status", "description"}
        for c in SEED_CONFLICTS:
            for field in required:
                assert field in c, f"Missing {field} in conflict {c.get('name', 'unknown')}"

    def test_valid_statuses(self):
        valid = {"active", "monitoring", "resolved"}
        for c in SEED_CONFLICTS:
            assert c["status"] in valid, f"Invalid status for {c['name']}"

    def test_descriptions_are_substantial(self):
        for c in SEED_CONFLICTS:
            assert len(c["description"]) > 50, f"Description too short for {c['name']}"

    def test_has_major_conflicts(self):
        names = {c["name"] for c in SEED_CONFLICTS}
        assert "Gaza Conflict" in names
        assert "Ukraine Conflict" in names
        assert "Taiwan Strait" in names

    def test_multiple_regions(self):
        regions = {c["region"] for c in SEED_CONFLICTS}
        assert len(regions) >= 3

    def test_unique_names(self):
        names = [c["name"] for c in SEED_CONFLICTS]
        assert len(names) == len(set(names)), "Duplicate conflict names found"
