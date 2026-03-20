"""Tests for pipeline job state machine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.app import app, _jobs, JobStatusResponse


client = TestClient(app)


class TestJobStatusResponse:
    def test_status_includes_skeleton_url(self):
        """When skeleton is ready, response should include skeleton_result_url."""
        _jobs["test-1"] = {
            "status": "skeleton_ready",
            "step": "Enhancing with SMPL-X...",
            "result_url": None,
            "skeleton_result_url": "https://r2.example.com/skeleton.json",
            "mannequin_result_url": None,
            "error": None,
        }
        response = client.get("/status/test-1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skeleton_ready"
        assert data["skeleton_result_url"] == "https://r2.example.com/skeleton.json"

    def test_mannequin_ready_includes_both_urls(self):
        """When mannequin is ready, both skeleton and mannequin URLs should be present."""
        _jobs["test-2"] = {
            "status": "mannequin_ready",
            "step": None,
            "result_url": "https://r2.example.com/skeleton.json",
            "skeleton_result_url": "https://r2.example.com/skeleton.json",
            "mannequin_result_url": "https://r2.example.com/mannequin.json",
            "error": None,
        }
        response = client.get("/status/test-2")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "mannequin_ready"
        assert data["mannequin_result_url"] is not None

    def test_backward_compatible_complete_status(self):
        """Old 'complete' status should still work for v1 results."""
        _jobs["test-3"] = {
            "status": "complete",
            "step": None,
            "result_url": "https://r2.example.com/result.json",
            "skeleton_result_url": None,
            "mannequin_result_url": None,
            "error": None,
        }
        response = client.get("/status/test-3")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"

    def test_not_found(self):
        response = client.get("/status/nonexistent")
        assert response.status_code == 404


class TestHealthEndpoint:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
