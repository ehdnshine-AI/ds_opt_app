import importlib

import pytest
from fastapi.testclient import TestClient


class FakeDb:
    def __init__(self, enabled=True):
        self._enabled = enabled
        self.inserted = []
        self.records = {}
        self.scenarios = {}
        self.milp_scenarios = {}

    @property
    def enabled(self):
        return self._enabled

    def insert_job(self, record):
        self.inserted.append(record)
        self.records[record.request_id] = record

    def get_job(self, request_id):
        return self.records.get(request_id)

    def delete_job(self, request_id):
        if request_id in self.records:
            del self.records[request_id]
            return 1
        return 0

    def get_scenario_product_params(self, scenario_name):
        return self.scenarios.get(scenario_name, [])

    def get_milp_scenario_model(self, scenario_name, payload_version=None):
        return self.milp_scenarios.get(scenario_name, {})


@pytest.fixture
def api_module(monkeypatch, tmp_path):
    monkeypatch.setenv("PULP_LOG_DIR", str(tmp_path))
    import app.api.main as main
    importlib.reload(main)
    return main


def test_healthz_db_disabled(api_module, monkeypatch):
    fake_db = FakeDb(enabled=False)
    api_module.db_handler = fake_db

    client = TestClient(api_module.app)
    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "db": False}


def test_solve_validates_constraint_length(api_module):
    client = TestClient(api_module.app)
    payload = {
        "sense": "min",
        "objective": [1, 2],
        "constraints": [{"coeffs": [1], "sense": ">=", "rhs": 1}],
        "solver": "CBC",
    }

    resp = client.post("/solve", json=payload)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "constraint coeff length mismatch"


def test_solve_success_persists_job(api_module, monkeypatch):
    fake_db = FakeDb(enabled=True)
    api_module.db_handler = fake_db

    def fake_call_solver(solver, payload):
        return {
            "status": "Optimal",
            "objective_value": 10.0,
            "variables": [1.0, 2.0],
            "solver": solver,
            "duration_ms": 5,
        }

    monkeypatch.setattr(api_module, "call_solver", fake_call_solver)

    client = TestClient(api_module.app)
    payload = {
        "sense": "min",
        "objective": [1, 2],
        "constraints": [{"coeffs": [1, 1], "sense": ">=", "rhs": 1}],
        "solver": "CBC",
    }

    resp = client.post("/solve", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "Optimal"
    assert body["solver"] == "CBC"
    assert len(fake_db.inserted) == 1
    assert fake_db.inserted[0].request_id == body["request_id"]


def test_get_job_db_disabled(api_module):
    api_module.db_handler = FakeDb(enabled=False)
    client = TestClient(api_module.app)

    resp = client.get("/jobs/123")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Database not configured"


def test_get_job_not_found(api_module):
    api_module.db_handler = FakeDb(enabled=True)
    client = TestClient(api_module.app)

    resp = client.get("/jobs/123")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found"


def test_delete_job_ok(api_module):
    fake_db = FakeDb(enabled=True)
    api_module.db_handler = fake_db
    fake_db.records["abc"] = type("R", (), {"request_id": "abc"})()

    client = TestClient(api_module.app)
    resp = client.delete("/jobs/abc")

    assert resp.status_code == 200
    assert resp.json()["detail"] == "Job deleted"


def test_delete_job_not_found(api_module):
    api_module.db_handler = FakeDb(enabled=True)
    client = TestClient(api_module.app)

    resp = client.delete("/jobs/missing")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found"


def test_scenario_solve_db_disabled(api_module):
    api_module.db_handler = FakeDb(enabled=False)
    client = TestClient(api_module.app)

    resp = client.post("/scenarios/solve", json={"scenario_name": "sample_7d_4p"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Database not configured"


def test_scenario_solve_not_found(api_module):
    api_module.db_handler = FakeDb(enabled=True)
    client = TestClient(api_module.app)

    resp = client.post("/scenarios/solve", json={"scenario_name": "missing"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Scenario not found"


def test_scenario_solve_success(api_module, monkeypatch):
    fake_db = FakeDb(enabled=True)
    fake_db.scenarios["sample_7d_4p"] = [
        type(
            "P",
            (),
            {
                "product_code": "A",
                "unit_profit": 70.0,
                "inventory_cost": 3.0,
                "initial_inventory": 10.0,
            },
        )(),
        type(
            "P",
            (),
            {
                "product_code": "B",
                "unit_profit": 60.0,
                "inventory_cost": 2.0,
                "initial_inventory": 5.0,
            },
        )(),
    ]
    api_module.db_handler = fake_db

    captured = {}

    def fake_call_solver(solver, payload):
        captured["solver"] = solver
        captured["payload"] = payload
        return {
            "status": "Optimal",
            "objective_value": 960.0,
            "variables": [10.0, 5.0],
            "solver": solver,
            "duration_ms": 9,
        }

    monkeypatch.setattr(api_module, "call_solver", fake_call_solver)

    client = TestClient(api_module.app)
    resp = client.post(
        "/scenarios/solve",
        json={"scenario_name": "sample_7d_4p", "solver": "HiGHS"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario_name"] == "sample_7d_4p"
    assert body["product_codes"] == ["A", "B"]
    assert body["status"] == "Optimal"
    assert body["solver"] == "HiGHS"
    assert len(fake_db.inserted) == 1
    assert fake_db.inserted[0].request_id == body["request_id"]

    assert captured["solver"] == "HiGHS"
    assert captured["payload"]["sense"] == "max"
    assert captured["payload"]["problem_type"] == "LP"
    assert captured["payload"]["objective"] == [67.0, 58.0]
    assert captured["payload"]["var_bounds"] == [{"low": 0, "up": 10.0}, {"low": 0, "up": 5.0}]


def test_scenario_milp_solve_not_found(api_module):
    api_module.db_handler = FakeDb(enabled=True)
    client = TestClient(api_module.app)

    resp = client.post("/scenarios/milp/solve", json={"scenario_name": "missing"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "MILP scenario not found"


def test_scenario_milp_solve_success(api_module, monkeypatch):
    fake_db = FakeDb(enabled=True)
    fake_db.milp_scenarios["sample_7d_4p"] = {
        "scenario_code": "sample_7d_4p",
        "scenario_name": "sample_7d_4p",
        "payload_version": 1,
        "sense": "max",
        "problem_type": "MILP",
        "objective": [70.0, 60.0],
        "constraints": [{"coeffs": [1.0, 1.0], "sense": "<=", "rhs": 10.0}],
        "var_bounds": [{"low": 0.0, "up": 1000000.0}, {"low": 0.0, "up": 1000000.0}],
        "var_cats": ["Integer", "Integer"],
        "var_names": ["prod_a", "prod_b"],
    }
    api_module.db_handler = fake_db

    captured = {}

    def fake_call_solver(solver, payload):
        captured["solver"] = solver
        captured["payload"] = payload
        return {
            "status": "Optimal",
            "objective_value": 700.0,
            "variables": [10.0, 0.0],
            "solver": solver,
            "duration_ms": 15,
        }

    monkeypatch.setattr(api_module, "call_solver", fake_call_solver)

    client = TestClient(api_module.app)
    resp = client.post(
        "/scenarios/milp/solve",
        json={"scenario_name": "sample_7d_4p", "solver": "HiGHS", "time_limit_sec": 30},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario_name"] == "sample_7d_4p"
    assert body["scenario_code"] == "sample_7d_4p"
    assert body["payload_version"] == 1
    assert body["variable_names"] == ["prod_a", "prod_b"]
    assert body["status"] == "Optimal"
    assert body["solver"] == "HiGHS"
    assert len(fake_db.inserted) == 1
    assert fake_db.inserted[0].request_id == body["request_id"]

    assert captured["payload"]["sense"] == "max"
    assert captured["payload"]["problem_type"] == "MILP"
    assert captured["payload"]["objective"] == [70.0, 60.0]
    assert captured["payload"]["constraints"] == [{"coeffs": [1.0, 1.0], "sense": "<=", "rhs": 10.0}]
    assert captured["payload"]["time_limit_sec"] == 30
