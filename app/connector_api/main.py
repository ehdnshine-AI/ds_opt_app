from __future__ import annotations

"""Solver connector API.

Each connector pod runs this app with SOLVER_NAME set to CBC/HiGHS/CPLEX.
"""

import logging
import json
import time
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.solver import pulp_solver

APP_NAME = "pulp-solver-connector"
# SOLVER_NAME controls which solver this connector serves.
SOLVER_NAME = os.getenv("SOLVER_NAME", "CBC").upper()

LOG_DIR = Path(os.getenv("PULP_LOG_DIR", "./logs"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

logger = logging.getLogger(APP_NAME)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / "solver_connector.log")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


class ConstraintIn(BaseModel):
    """Single constraint in a linear program."""
    coeffs: List[float]
    sense: str = Field(..., description="<=, >=, =")
    rhs: float


class SolveRequest(BaseModel):
    """Payload accepted by solver connectors."""
    sense: str = Field("min", description="min|max")
    objective: List[float]
    constraints: List[ConstraintIn]
    var_bounds: Optional[List[dict]] = None
    var_cats: Optional[List[str]] = None
    solver: Optional[str] = Field(None, description="CBC|HiGHS|CPLEX")
    problem_type: str = Field("MILP", description="LP|MILP")
    time_limit_sec: Optional[float] = None
    request_id: Optional[str] = None


class SolveResponse(BaseModel):
    """Response returned by solver connectors."""
    status: str
    objective_value: Optional[float]
    variables: List[Optional[float]]
    solver: str
    duration_ms: int


app = FastAPI(title=f"{APP_NAME}-{SOLVER_NAME}")


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
    return {"ok": True, "solver": SOLVER_NAME}


@app.post("/solve", response_model=SolveResponse)
def solve(req: SolveRequest):
    if not req.objective:
        raise HTTPException(status_code=400, detail="objective is required")

    n = len(req.objective)
    for c in req.constraints:
        if len(c.coeffs) != n:
            raise HTTPException(status_code=400, detail="constraint coeff length mismatch")

    if req.solver and req.solver.upper() != SOLVER_NAME:
        raise HTTPException(status_code=400, detail=f"solver mismatch: {req.solver} != {SOLVER_NAME}")

    constraints = [{"coeffs": c.coeffs, "sense": c.sense, "rhs": c.rhs} for c in req.constraints]
    request_id = req.request_id or str(uuid.uuid4())

    try:
        if req.problem_type.upper() == "LP":
            result = pulp_solver.solve_linear_problem(
                objective=req.objective,
                constraints=constraints,
                var_bounds=req.var_bounds,
                var_cats=req.var_cats,
                sense=req.sense,
                solver_name=SOLVER_NAME,
                time_limit_sec=req.time_limit_sec,
                request_id=request_id,
                logger=logger,
            )
        elif req.problem_type.upper() == "MILP":
            result = pulp_solver.solve_milp_problem(
                objective=req.objective,
                constraints=constraints,
                var_bounds=req.var_bounds,
                var_cats=req.var_cats,
                sense=req.sense,
                solver_name=SOLVER_NAME,
                time_limit_sec=req.time_limit_sec,
                request_id=request_id,
                logger=logger,
            )
        else:
            raise HTTPException(status_code=400, detail="problem_type must be LP or MILP")
    except pulp_solver.SolverUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SolveResponse(
        status=result.status,
        objective_value=result.objective_value,
        variables=result.variables,
        solver=result.solver,
        duration_ms=result.duration_ms,
    )
