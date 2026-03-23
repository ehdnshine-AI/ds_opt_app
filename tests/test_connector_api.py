import importlib

import pytest
from fastapi.testclient import TestClient

from app.solver import pulp_solver


@pytest.fixture
def connector_module(monkeypatch, tmp_path):
    monkeypatch.setenv("PULP_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SOLVER_NAME", "CBC")
    import app.connector_api.main as main
    importlib.reload(main)
    return main


def test_healthz(connector_module):
    client = TestClient(connector_module.app)
    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "solver": "CBC"}


def test_solver_mismatch(connector_module):
    client = TestClient(connector_module.app)
    payload = {
        "sense": "min",
        "objective": [1],
        "constraints": [{"coeffs": [1], "sense": ">=", "rhs": 1}],
        "solver": "HiGHS",
    }

    resp = client.post("/solve", json=payload)

    assert resp.status_code == 400
    assert "solver mismatch" in resp.json()["detail"]


def test_invalid_problem_type(connector_module):
    client = TestClient(connector_module.app)
    payload = {
        "sense": "min",
        "objective": [1],
        "constraints": [{"coeffs": [1], "sense": ">=", "rhs": 1}],
        "problem_type": "QP",
    }

    resp = client.post("/solve", json=payload)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "problem_type must be LP or MILP"


def test_solve_lp_uses_linear_path(connector_module, monkeypatch):
    client = TestClient(connector_module.app)

    def fake_linear(**kwargs):
        return pulp_solver.SolveResult(
            status="Optimal",
            objective_value=1.0,
            variables=[1.0],
            solver="CBC",
            duration_ms=1,
        )

    monkeypatch.setattr(connector_module.pulp_solver, "solve_linear_problem", fake_linear)

    payload = {
        "sense": "min",
        "objective": [1],
        "constraints": [{"coeffs": [1], "sense": ">=", "rhs": 1}],
        "problem_type": "LP",
    }

    resp = client.post("/solve", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "Optimal"
    assert body["solver"] == "CBC"


def test_solve_milp_uses_milp_path(connector_module, monkeypatch):
    client = TestClient(connector_module.app)

    def fake_milp(**kwargs):
        return pulp_solver.SolveResult(
            status="Optimal",
            objective_value=2.0,
            variables=[1.0],
            solver="CBC",
            duration_ms=2,
        )

    monkeypatch.setattr(connector_module.pulp_solver, "solve_milp_problem", fake_milp)

    payload = {
        "sense": "min",
        "objective": [1],
        "constraints": [{"coeffs": [1], "sense": ">=", "rhs": 1}],
        "problem_type": "MILP",
    }

    resp = client.post("/solve", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["objective_value"] == 2.0
    assert body["duration_ms"] == 2
