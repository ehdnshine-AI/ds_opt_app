from __future__ import annotations

"""CPLEX solver connector factory (requires CPLEX installation/license)."""

from typing import Optional

try:
    from pulp import CPLEX_CMD
except Exception:  # pragma: no cover - optional dependency
    CPLEX_CMD = None


class CPLEXUnavailable(RuntimeError):
    pass


def get_solver(time_limit_sec: Optional[float]):
    # CPLEX connector: expose additional params here as needed.
    # Common PuLP CPLEX params (version-dependent):
    # - timeLimit: float seconds, solver wall-clock limit.
    # - msg: bool, enable/disable solver logs.
    #   True: solver prints progress/log output to stdout/stderr during solve.
    #   False: suppress solver output (useful for APIs/background jobs to keep logs clean).
    # - gapRel: relative MIP gap target (stops when achieved).
    # - gapAbs: absolute MIP gap target.
    # - threads: integer, number of threads CPLEX may use.
    # - maxNodes: cap on branch-and-bound nodes.
    # - options: list[str], raw CPLEX parameters (e.g. "set mip tolerances mipgap 0.01").
    # - warmStart: bool, reuse previous solution as a starting point.
    # - keepFiles: bool, keep temporary LP/MPS files for debugging.
    # - path: explicit path to the CPLEX executable.
    # - logPath: write solver logs to a file instead of stdout/stderr.
    # - maxMemory: memory limit (MB) if supported by the backend.
    # Note: CPLEX has a rich parameter set; if needed, extend this connector to
    # pass additional keyword args through CPLEX_CMD.
    if not CPLEX_CMD:
        raise CPLEXUnavailable("CPLEX_CMD not available in this PuLP installation.")

    solver = CPLEX_CMD(timeLimit=time_limit_sec, msg=False)
    if not solver.available():
        raise CPLEXUnavailable("CPLEX solver not available. Ensure CPLEX is installed and licensed.")

    return solver
