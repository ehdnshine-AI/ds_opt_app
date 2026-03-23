from __future__ import annotations

"""HTTP client for calling solver connector services.

Parameters are sourced from environment variables:
- CBC_SOLVER_URL / HIGHS_SOLVER_URL / CPLEX_SOLVER_URL: full URL to each connector's /solve endpoint.
- SOLVER_REQUEST_TIMEOUT: request timeout in seconds.
"""

import json
import os
from typing import Any
from urllib import request


class SolverServiceError(RuntimeError):
    """Raised when a solver connector call fails or is misconfigured."""


def _get_solver_url(solver_name: str) -> str:
    """Resolve solver name to connector URL using environment variables."""
    solver = solver_name.upper()
    if solver == "HIGHS":
        return os.getenv("HIGHS_SOLVER_URL", "")
    if solver == "CPLEX":
        return os.getenv("CPLEX_SOLVER_URL", "")
    return os.getenv("CBC_SOLVER_URL", "")


def call_solver(solver_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call a solver connector over HTTP.

    Parameters:
    - solver_name: CBC | HiGHS | CPLEX (case-insensitive)
    - payload: JSON body passed to connector (/solve)
    """
    url = _get_solver_url(solver_name)
    if not url:
        raise SolverServiceError(f"solver URL not configured for {solver_name}")

    timeout_sec = float(os.getenv("SOLVER_REQUEST_TIMEOUT", "30"))
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            if resp.status != 200:
                raise SolverServiceError(f"solver error status={resp.status} body={body}")
            return json.loads(body)
    except SolverServiceError:
        raise
    except Exception as exc:
        raise SolverServiceError(str(exc))
