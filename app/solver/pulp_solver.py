from __future__ import annotations

"""Core PuLP solver runner shared by API and connector services."""

import time
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import logging
from pulp import (
    LpProblem,
    LpMinimize,
    LpMaximize,
    LpVariable,
    lpSum,
    LpStatus,
    value,
)

from app.util.connector import (
    get_cbc_solver,
    get_cplex_solver,
    get_highs_solver,
)
from app.util.connector.cplex_connector import CPLEXUnavailable
from app.util.connector.highs_connector import HiGHSUnavailable


class SolverUnavailable(RuntimeError):
    pass


@dataclass
class SolveResult:
    status: str
    objective_value: Optional[float]
    variables: list[Optional[float]]
    solver: str
    duration_ms: int


def _select_solver(
    solver_name: str,
    time_limit_sec: Optional[float],
    request_id: str,
    logger: logging.Logger,
):
    """Select solver backend (CBC/HiGHS/CPLEX) with availability checks."""
    requested = solver_name
    solver_name = solver_name.upper()
    if solver_name == "HIGHS":
        try:
            return get_highs_solver(time_limit_sec), "HiGHS"
        except HiGHSUnavailable as exc:
            logger.error("solve.error request_id=%s reason=highs_not_available", request_id)
            raise SolverUnavailable(str(exc))

    if solver_name == "CPLEX":
        try:
            return get_cplex_solver(time_limit_sec), "CPLEX"
        except CPLEXUnavailable as exc:
            logger.error("solve.error request_id=%s reason=cplex_not_available", request_id)
            raise SolverUnavailable(str(exc))

    if solver_name == "CBC":
        return get_cbc_solver(time_limit_sec), "CBC"

    logger.error("solve.error request_id=%s reason=solver_not_available solver=%s", request_id, requested)
    raise SolverUnavailable(f"{requested} is not available")


def solve_linear_problem(
    *,
    objective: Sequence[float],
    constraints: Iterable[dict],
    var_bounds: Optional[Sequence[dict]],
    var_cats: Optional[Sequence[str]],
    sense: str,
    solver_name: str,
    time_limit_sec: Optional[float],
    request_id: str,
    logger: logging.Logger,
) -> SolveResult:
    """Solve a linear program with PuLP.

    Parameters:
    - objective: objective coefficients
    - constraints: list of dicts with coeffs/sense/rhs
    - var_bounds: list of {low, up} bound dicts
    - var_cats: list of variable categories
    - sense: min|max
    - solver_name: CBC|HiGHS|CPLEX
    - time_limit_sec: optional time limit
    - request_id: ID for logging/tracing
    - logger: logger instance for structured logs
    """
    n = len(objective)
    bounds = var_bounds or [{} for _ in range(n)]
    cats = var_cats or ["Continuous" for _ in range(n)]

    prob = LpProblem("pulp_api_problem", LpMinimize if sense == "min" else LpMaximize)

    vars_ = []
    for i in range(n):
        b = bounds[i] if i < len(bounds) else {}
        cat = cats[i] if i < len(cats) else "Continuous"
        vars_.append(
            LpVariable(
                f"x{i}",
                lowBound=b.get("low", None),
                upBound=b.get("up", None),
                cat=cat,
            )
        )

    prob += lpSum(objective[i] * vars_[i] for i in range(n))

    for idx, c in enumerate(constraints):
        coeffs = c["coeffs"]
        expr = lpSum(coeffs[i] * vars_[i] for i in range(n))
        if c["sense"] == "<=":
            prob += expr <= c["rhs"], f"c{idx}"
        elif c["sense"] == ">=":
            prob += expr >= c["rhs"], f"c{idx}"
        elif c["sense"] == "=":
            prob += expr == c["rhs"], f"c{idx}"
        else:
            raise ValueError("invalid constraint sense")

    solver, solver_name = _select_solver(solver_name, time_limit_sec, request_id, logger)

    logger.info("solve.start request_id=%s solver=%s sense=%s n=%s", request_id, solver_name, sense, n)

    t0 = time.time()
    try:
        prob.solve(solver)
    except Exception:
        logger.exception("solve.error request_id=%s", request_id)
        raise
    duration_ms = int((time.time() - t0) * 1000)

    status = LpStatus.get(prob.status, "Unknown")
    objective_value = value(prob.objective) if prob.objective is not None else None
    variables = [v.value() for v in vars_]

    logger.info(
        "solve.done request_id=%s status=%s objective=%s duration_ms=%s",
        request_id,
        status,
        objective_value,
        duration_ms,
    )

    return SolveResult(
        status=status,
        objective_value=objective_value,
        variables=variables,
        solver=solver_name,
        duration_ms=duration_ms,
    )


def solve_milp_problem(
    *,
    objective: Sequence[float],
    constraints: Iterable[dict],
    var_bounds: Optional[Sequence[dict]],
    var_cats: Optional[Sequence[str]],
    sense: str,
    solver_name: str,
    time_limit_sec: Optional[float],
    request_id: str,
    logger: logging.Logger,
    default_var_cat: str = "Binary",
) -> SolveResult:
    """Solve a MILP problem with PuLP.

    Parameters are the same as solve_linear_problem, with an extra:
    - default_var_cat: category applied when var_cats is not provided (default Binary).
    """
    if var_cats is None:
        var_cats = [default_var_cat for _ in range(len(objective))]
    return solve_linear_problem(
        objective=objective,
        constraints=constraints,
        var_bounds=var_bounds,
        var_cats=var_cats,
        sense=sense,
        solver_name=solver_name,
        time_limit_sec=time_limit_sec,
        request_id=request_id,
        logger=logger,
    )
