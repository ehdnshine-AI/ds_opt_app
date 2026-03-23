from __future__ import annotations

"""PuLP API entrypoint.

Accepts solve requests, forwards them to solver connector services,
and optionally persists results to PostgreSQL.
"""

import os
import uuid

import logging
import json
import time
import importlib
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.api.solver_client import SolverServiceError, call_solver

_db_module = importlib.import_module("app.class.DatabaseHandler")
DatabaseHandler = _db_module.DatabaseHandler
JobRecord = _db_module.JobRecord

APP_NAME = "pulp-solver-api"

LOG_DIR = Path(os.getenv("PULP_LOG_DIR", "./logs"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

logger = logging.getLogger(APP_NAME)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / "solver.log")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

class ConstraintIn(BaseModel):
    """Single linear constraint.

    coeffs: coefficients aligned with objective variable order.
    sense: one of <=, >=, =
    rhs: right-hand-side value.
    """
    coeffs: List[float]
    sense: str = Field(..., description="<=, >=, =")
    rhs: float

class SolveRequest(BaseModel):
    """Solve request payload sent by clients.

    sense: min|max
    objective: coefficients for objective function
    constraints: list of ConstraintIn
    var_bounds: list of dicts with optional low/up per variable
    var_cats: list of categories (e.g., Continuous, Binary)
    solver: CBC|HiGHS|CPLEX
    time_limit_sec: optional time limit in seconds
    """
    sense: str = Field("min", description="min|max")
    objective: List[float]
    constraints: List[ConstraintIn]
    var_bounds: Optional[List[dict]] = None
    var_cats: Optional[List[str]] = None
    solver: str = Field("CBC", description="CBC|HiGHS|CPLEX")
    problem_type: str = Field("MILP", description="LP|MILP")
    time_limit_sec: Optional[float] = None

class SolveResponse(BaseModel):
    """Solve response returned to clients."""
    request_id: str
    status: str
    objective_value: Optional[float]
    variables: List[Optional[float]]
    variable_names: Optional[List[str]] = None
    solver: str
    duration_ms: int


class ScenarioSolveRequest(BaseModel):
    """Scenario solve request payload."""
    scenario_name: str
    solver: str = Field("HiGHS", description="CBC|HiGHS|CPLEX")


class ScenarioSolveResponse(SolveResponse):
    """Scenario solve response."""
    scenario_name: str
    product_codes: List[str]


class ScenarioMilpSolveRequest(BaseModel):
    """MILP scenario solve request payload."""
    scenario_name: str = Field(..., description="scenario_code or scenario_name")
    solver: str = Field("HiGHS", description="CBC|HiGHS|CPLEX")
    time_limit_sec: Optional[float] = None
    payload_version: Optional[int] = None


class ScenarioMilpSolveResponse(SolveResponse):
    """MILP scenario solve response."""
    scenario_code: str
    scenario_name: str
    payload_version: int
    variable_names: List[str]


app = FastAPI(title=APP_NAME)

# DATABASE_URL: SQLAlchemy-compatible connection string (optional).
DATABASE_URL = os.getenv("DATABASE_URL", "")
db_handler = DatabaseHandler(DATABASE_URL)


def _truncate(text: str, limit: int = 10000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    body_text = ""
    try:
        raw_body = await request.body()
        if raw_body:
            body_text = raw_body.decode("utf-8", errors="replace")
    except Exception:
        body_text = "<unreadable>"

    parsed_body = None
    if body_text:
        try:
            parsed_body = json.loads(body_text)
        except Exception:
            parsed_body = _truncate(body_text)

    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)

    logger.info(
        "request method=%s path=%s status=%s duration_ms=%s query=%s body=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        dict(request.query_params),
        parsed_body,
    )
    return response

@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "db_configured": db_handler.enabled,
    }


@app.get("/readyz")
def readyz():
    db_configured = db_handler.enabled
    db_reachable = db_handler.ping() if db_configured else False
    return {
        "ok": (db_reachable if db_configured else True),
        "db_configured": db_configured,
        "db_reachable": db_reachable,
    }

@app.post("/solve", response_model=SolveResponse)
def solve(req: SolveRequest):
    if not req.objective:
        raise HTTPException(status_code=400, detail="objective is required")

    n = len(req.objective)
    request_id = str(uuid.uuid4())
    for c in req.constraints:
        if len(c.coeffs) != n:
            raise HTTPException(status_code=400, detail="constraint coeff length mismatch")

    constraints = [{"coeffs": c.coeffs, "sense": c.sense, "rhs": c.rhs} for c in req.constraints]
    try:
        result = call_solver(
            req.solver,
            {
                "sense": req.sense,
                "objective": req.objective,
                "constraints": constraints,
                "var_bounds": req.var_bounds,
                "var_cats": req.var_cats,
                "solver": req.solver,
                "time_limit_sec": req.time_limit_sec,
                "request_id": request_id,
                "problem_type": req.problem_type,
            },
        )
    except SolverServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    variable_values = result.get("variables", [])
    variable_names = [f"x{i}" for i in range(len(variable_values))]
    db_handler.insert_job(
        JobRecord(
            request_id=request_id,
            status=result["status"],
            objective_value=result.get("objective_value"),
            variables=variable_values,
            solver=result["solver"],
            duration_ms=result["duration_ms"],
            variable_names=variable_names,
        )
    )

    return SolveResponse(
        request_id=request_id,
        status=result["status"],
        objective_value=result.get("objective_value"),
        variables=variable_values,
        variable_names=variable_names,
        solver=result["solver"],
        duration_ms=result["duration_ms"],
    )


@app.post("/scenarios/solve", response_model=ScenarioSolveResponse)
def solve_scenario(req: ScenarioSolveRequest):
    if not db_handler.enabled:
        raise HTTPException(status_code=503, detail="Database not configured")

    params = db_handler.get_scenario_product_params(req.scenario_name)
    if params is None:
        raise HTTPException(status_code=500, detail="Database error")
    if not params:
        raise HTTPException(status_code=404, detail="Scenario not found")

    objective = [p.unit_profit - p.inventory_cost for p in params]
    var_bounds = [{"low": 0, "up": p.initial_inventory} for p in params]
    product_codes = [p.product_code for p in params]
    request_id = str(uuid.uuid4())

    try:
        result = call_solver(
            req.solver,
            {
                "sense": "max",
                "objective": objective,
                "constraints": [],
                "var_bounds": var_bounds,
                "var_cats": ["Continuous"] * len(objective),
                "solver": req.solver,
                "problem_type": "LP",
                "request_id": request_id,
            },
        )
    except SolverServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    variable_values = result.get("variables", [])
    db_handler.insert_job(
        JobRecord(
            request_id=request_id,
            status=result["status"],
            objective_value=result.get("objective_value"),
            variables=variable_values,
            solver=result["solver"],
            duration_ms=result["duration_ms"],
            variable_names=product_codes,
        )
    )

    return ScenarioSolveResponse(
        request_id=request_id,
        status=result["status"],
        objective_value=result.get("objective_value"),
        variables=variable_values,
        variable_names=product_codes,
        solver=result["solver"],
        duration_ms=result["duration_ms"],
        scenario_name=req.scenario_name,
        product_codes=product_codes,
    )


@app.post("/scenarios/milp/solve", response_model=ScenarioMilpSolveResponse)
def solve_milp_scenario(req: ScenarioMilpSolveRequest):
    if not db_handler.enabled:
        raise HTTPException(status_code=503, detail="Database not configured")

    model = db_handler.get_milp_scenario_model(
        req.scenario_name,
        payload_version=req.payload_version,
    )
    if model is None:
        raise HTTPException(status_code=500, detail="Database error")
    if not model:
        raise HTTPException(status_code=404, detail="MILP scenario not found")

    request_id = str(uuid.uuid4())

    try:
        result = call_solver(
            req.solver,
            {
                "sense": model["sense"],
                "objective": model["objective"],
                "constraints": model["constraints"],
                "var_bounds": model["var_bounds"],
                "var_cats": model["var_cats"],
                "solver": req.solver or "HiGHS",
                "problem_type": model["problem_type"],
                "time_limit_sec": req.time_limit_sec,
                "request_id": request_id,
            },
        )
    except SolverServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    variable_values = result.get("variables", [])
    db_handler.insert_job(
        JobRecord(
            request_id=request_id,
            status=result["status"],
            objective_value=result.get("objective_value"),
            variables=variable_values,
            solver=result["solver"],
            duration_ms=result["duration_ms"],
            variable_names=model["var_names"],
        )
    )

    return ScenarioMilpSolveResponse(
        request_id=request_id,
        status=result["status"],
        objective_value=result.get("objective_value"),
        variables=variable_values,
        variable_names=model["var_names"],
        solver=result["solver"],
        duration_ms=result["duration_ms"],
        scenario_code=model["scenario_code"],
        scenario_name=model["scenario_name"],
        payload_version=model["payload_version"],
    )


@app.get("/jobs/{request_id}", response_model=SolveResponse)
def get_job(request_id: str):
    if not db_handler.enabled:
        raise HTTPException(status_code=503, detail="Database not configured")

    record = db_handler.get_job(request_id)
    if not record:
        exists = db_handler.job_exists(request_id)
        if exists is None:
            raise HTTPException(status_code=500, detail="Database error")
        raise HTTPException(status_code=404, detail="Job not found")
    return SolveResponse(
        request_id=record.request_id,
        status=record.status,
        objective_value=record.objective_value,
        variables=record.variables,
        variable_names=record.variable_names,
        solver=record.solver,
        duration_ms=record.duration_ms,
    )

@app.delete("/jobs/{request_id}")
def delete_job(request_id: str):
    if not db_handler.enabled:
        raise HTTPException(status_code=503, detail="Database not configured")
    rowcount = db_handler.delete_job(request_id)
    if rowcount is None:
        raise HTTPException(status_code=500, detail="Database error")
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"detail": "Job deleted"}
