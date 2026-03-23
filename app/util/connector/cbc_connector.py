from __future__ import annotations

"""CBC solver connector factory."""

from typing import Optional

from pulp import PULP_CBC_CMD


def get_solver(time_limit_sec: Optional[float]):
    # CBC connector: expose additional params here as needed.
    # Common PuLP CBC params (version-dependent):
    # - timeLimit: float seconds, solver wall-clock limit.
    # - msg: bool, enable/disable solver logs.
    #   True: solver prints progress/log output to stdout/stderr during solve.
    #   False: suppress solver output (useful for APIs/background jobs to keep logs clean).
    # - gapRel: relative MIP gap target (stops when achieved).
    # - gapAbs: absolute MIP gap target.
    # - threads: integer, number of threads CBC may use.
    # - warmStart: bool, reuse previous solution as a starting point.
    # - maxNodes: integer, cap on branch-and-bound nodes.
    return PULP_CBC_CMD(timeLimit=time_limit_sec, msg=False)
