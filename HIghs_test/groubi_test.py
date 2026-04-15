import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from param_gen import PAYLOAD_OUTPUT_PATH, load_problem_data

try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError as exc:
    print("gurobipy is not installed. Run `pip install gurobipy` first.")
    raise SystemExit(1) from exc


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = PAYLOAD_OUTPUT_PATH
DEFAULT_OUTPUT = BASE_DIR / "groubi.result.json"
SIZE_LIMITED_MAX_PRODUCTS = 1000
SIZE_LIMITED_MAX_CONSTRAINTS = 1000


def load_problem(input_path: Path) -> dict:
    return load_problem_data(input_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    problem = load_problem(args.input)

    n_products = problem["n_products"]
    n_constraints = problem["n_constraints"]
    profit = problem["profit"]
    setup = problem["setup"]
    cap = problem["cap"]
    A = problem["A"]
    b = problem["b"]
    scale_profit = problem["scale_profit"]
    scale_setup = problem["scale_setup"]
    w1 = float(problem["weights"]["w1"])
    w2 = float(problem["weights"]["w2"])

    model = gp.Model("production_milp")
    model.ModelSense = GRB.MAXIMIZE

    model.Params.Threads = 8
    model.Params.TimeLimit = 6000
    model.Params.MIPGap = 0.1
    model.Params.Presolve = 2

    x = model.addVars(
        n_products,
        lb=0.0,
        ub=cap.tolist(),
        vtype=GRB.CONTINUOUS,
        name="x",
    )
    y = model.addVars(
        n_products,
        lb=0.0,
        ub=1.0,
        vtype=GRB.BINARY,
        name="y",
    )

    model.setObjective(
        gp.quicksum((w1 * profit[i] / scale_profit) * x[i] for i in range(n_products))
        - gp.quicksum((w2 * setup[i] / scale_setup) * y[i] for i in range(n_products))
    )

    for j in range(n_constraints):
        model.addConstr(
            gp.quicksum(float(A[j, i]) * x[i] for i in range(n_products)) <= float(b[j]),
            name=f"resource_{j}",
        )

    for i in range(n_products):
        model.addConstr(x[i] <= float(cap[i]) * y[i], name=f"big_m_{i}")

    total_vars = 2 * n_products
    total_constraints = n_constraints + n_products
    print(f"Solving (gurobipy): {n_products} products, {n_constraints} constraints")
    print(f"Model size: {total_vars} vars, {total_constraints} constraints")

    t0 = time.time()
    try:
        model.optimize()
    except gp.GurobiError as exc:
        if "size-limited license" in str(exc).lower():
            print("\nGurobi restricted license limit was exceeded.")
            print("The pip license supports at most 2000 variables and 2000 linear constraints.")
            print(f"This model uses {total_vars} variables and {total_constraints} constraints.")
            print(
                "For this model family, the restricted license-safe upper bound is "
                f"products <= {SIZE_LIMITED_MAX_PRODUCTS} and constraints <= {SIZE_LIMITED_MAX_CONSTRAINTS}."
            )
            return 2
        raise
    elapsed = time.time() - t0

    print("\nModel Status:", model.Status)

    feasible_statuses = {
        GRB.OPTIMAL,
        GRB.SUBOPTIMAL,
        GRB.TIME_LIMIT,
        GRB.ITERATION_LIMIT,
        GRB.NODE_LIMIT,
        GRB.SOLUTION_LIMIT,
    }
    if model.Status not in feasible_statuses or model.SolCount == 0:
        print("No feasible solution returned.")
        return 1

    x_vals = np.array([x[i].X for i in range(n_products)], dtype=np.float64)
    y_vals = np.array([y[i].X for i in range(n_products)], dtype=np.float64)

    n_active = int(np.sum(y_vals > 0.5))
    total_profit = float(np.sum(profit * x_vals))
    total_setup = float(np.sum(setup * y_vals))
    obj_value = float(model.ObjVal)

    print(f"\n{'=' * 50}")
    print(f"Elapsed sec      : {elapsed:.2f}")
    print(f"Active products  : {n_active} / {n_products}")
    print(f"Total profit     : {total_profit:,.0f}")
    print(f"Total setup cost : {total_setup:,.0f}")
    print(f"Objective        : {obj_value:.6f}")
    print(f"{'=' * 50}")

    results = [
        (i, x_vals[i], profit[i], setup[i])
        for i in range(n_products)
        if y_vals[i] > 0.5
    ]
    results.sort(key=lambda row: row[1] * row[2], reverse=True)

    print("\n[ Top 10 products by total profit ]")
    print(f"{'Prod':>6} {'Qty':>8} {'Profit':>10} {'Setup':>10} {'Total':>12}")

    for i, xi, pi, si in results[:10]:
        print(f" {i:>4}  {xi:>6.1f}  {pi:>8.1f}  {si:>8.1f}  {pi * xi:>10.0f}")

    result_payload = {
        "input_file": str(args.input),
        "status": int(model.Status),
        "status_name": str(model.Status),
        "elapsed_sec": elapsed,
        "objective_value": obj_value,
        "n_active": n_active,
        "total_profit": total_profit,
        "total_setup": total_setup,
        "x_vals": x_vals.tolist(),
        "y_vals": y_vals.tolist(),
        "top_results": [
            {
                "product_index": int(i),
                "production": float(xi),
                "unit_profit": float(pi),
                "setup_cost": float(si),
                "total_profit": float(pi * xi),
            }
            for i, xi, pi, si in results[:10]
        ],
    }
    args.output.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
    print(f"\nResult JSON written to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
