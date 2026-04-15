import argparse
import sys
import time

import numpy as np

try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError as exc:
    print("gurobipy is not installed. Run `pip install gurobipy` first.")
    raise SystemExit(1) from exc


np.random.seed(42)

DEFAULT_PRODUCTS = 300
DEFAULT_CONSTRAINTS = 200
SIZE_LIMITED_MAX_PRODUCTS = 1000
SIZE_LIMITED_MAX_CONSTRAINTS = 1000

W1 = 0.7
W2 = 0.3


def build_data(n_products: int, n_constraints: int):
    profit = np.random.uniform(10, 100, n_products)
    setup = np.random.uniform(50, 500, n_products)
    cap = np.random.uniform(10, 50, n_products)

    A = np.random.uniform(0, 1, (n_constraints, n_products))
    b = A.mean(axis=1) * n_products * 0.3

    scale_profit = profit.sum() * cap.mean()
    scale_setup = setup.sum()

    return profit, setup, cap, A, b, scale_profit, scale_setup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--products", type=int, default=DEFAULT_PRODUCTS)
    parser.add_argument("--constraints", type=int, default=DEFAULT_CONSTRAINTS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    n_products = args.products
    n_constraints = args.constraints

    profit, setup, cap, A, b, scale_profit, scale_setup = build_data(
        n_products, n_constraints
    )

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
        gp.quicksum((W1 * profit[i] / scale_profit) * x[i] for i in range(n_products))
        - gp.quicksum((W2 * setup[i] / scale_setup) * y[i] for i in range(n_products))
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
            print(
                "The pip license supports at most 2000 variables and 2000 linear constraints."
            )
            print(
                "This model uses "
                f"{total_vars} variables and {total_constraints} constraints."
            )
            print(
                "Run with a smaller model, for example:\n"
                "python3 HIghs_test/groubi_test.py --products 1000 --constraints 1000"
            )
            print(
                "For this model family, the restricted license-safe upper bound is "
                f"--products <= {SIZE_LIMITED_MAX_PRODUCTS} and "
                f"--constraints <= {SIZE_LIMITED_MAX_CONSTRAINTS}."
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
    print(f"풀이 시간        : {elapsed:.2f}초")
    print(f"생산 제품 수      : {n_active} / {n_products}")
    print(f"총 이익         : {total_profit:,.0f}")
    print(f"총 셋업비용       : {total_setup:,.0f}")
    print(f"Objective       : {obj_value:.6f}")
    print(f"{'=' * 50}")

    results = [
        (i, x_vals[i], profit[i], setup[i])
        for i in range(n_products)
        if y_vals[i] > 0.5
    ]
    results.sort(key=lambda row: row[1] * row[2], reverse=True)

    print("\n[ 이익 상위 10개 제품 ]")
    print(f"{'제품':>6} {'생산량':>8} {'단위이익':>8} {'셋업비':>8} {'총이익':>10}")

    for i, xi, pi, si in results[:10]:
        print(f" {i:>4}  {xi:>6.1f}  {pi:>6.1f}  {si:>6.1f}  {pi * xi:>8.0f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
