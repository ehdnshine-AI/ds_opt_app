from __future__ import annotations

"""HiGHS solver connector factory with thread control."""

import os
from typing import Optional

from pulp import HiGHS, HiGHS_CMD


class HiGHSUnavailable(RuntimeError):
    pass


def get_solver(time_limit_sec: Optional[float]):
    # HiGHS connector: expose additional params here as needed.
    # Common PuLP HiGHS params:
    # - timeLimit: float seconds, solver wall-clock limit.
    # - msg: bool, enable/disable solver logs.
    #   True: solver prints progress/log output to stdout/stderr during solve.
    #   False: suppress solver output (useful for APIs/background jobs to keep logs clean).
    # Threading:
    # - HiGHS uses OpenMP; set OMP_NUM_THREADS to control parallelism.
    # - We also accept HIGHS_THREADS for convenience and map it to OMP_NUM_THREADS.
    threads_env = os.getenv("HIGHS_THREADS") or os.getenv("OMP_NUM_THREADS")
    if threads_env:
        try:
            threads = int(threads_env)
            if threads > 0:
                # HiGHS uses OpenMP; setting OMP_NUM_THREADS controls thread count.
                os.environ["OMP_NUM_THREADS"] = str(threads)
        except ValueError:
            pass

    # Prefer python HiGHS (highspy). Fallback to external binary if needed.
    solver = HiGHS(timeLimit=time_limit_sec, msg=False)
    if solver.available():
        return solver

    solver = HiGHS_CMD(timeLimit=time_limit_sec, msg=False)
    if solver.available():
        return solver

    raise HiGHSUnavailable("HiGHS solver not available. Install highspy or highs binary.")
