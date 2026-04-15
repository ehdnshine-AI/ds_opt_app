import time
from pathlib import Path

import numpy as np
from highspy import Highs

from param_gen import PAYLOAD_OUTPUT_PATH, load_problem_data

BASE_DIR = Path(__file__).resolve().parent
RESULT_OUTPUT_PATH = BASE_DIR / "milp_test.result.json"


def solve_with_highs(problem: dict) -> dict:
    highs = Highs()
    highs.setMaximize()

    highs.setOptionValue("threads", 8)
    highs.setOptionValue("time_limit", 6000)
    highs.setOptionValue("mip_rel_gap", 0.1)
    highs.setOptionValue("presolve", "on")

    highs.addVars(problem["num_vars"], problem["col_lower"], problem["col_upper"])
    highs.changeColsCost(problem["num_vars"], np.arange(problem["num_vars"]), problem["col_cost"])
    highs.changeColsIntegrality(problem["num_vars"], np.arange(problem["num_vars"]), problem["integrality"])

    for j in range(problem["n_constraints"]):
        idxs = np.arange(problem["n_products"], dtype=np.int32)
        vals = problem["A"][j].astype(np.float64)
        highs.addRow(
            -np.inf,
            float(problem["b"][j]),
            len(idxs),
            idxs.tolist(),
            vals.tolist(),
        )

    for i in range(problem["n_products"]):
        highs.addRow(
            -np.inf,
            0.0,
            2,
            [i, problem["n_products"] + i],
            [1.0, -float(problem["cap"][i])],
        )

    print(f"Solving (highspy): {problem['n_products']} products, {problem['n_constraints']} constraints")

    t0 = time.time()
    highs.run()
    elapsed = time.time() - t0

    status = highs.getModelStatus()
    print("\nModel Status:", status)

    solution = highs.getSolution()
    values = solution.col_value

    if values is None or len(values) == 0:
        raise RuntimeError("No solution returned")

    values = np.array(values, dtype=np.float64)
    x_vals = values[: problem["n_products"]]
    y_vals = values[problem["n_products"] :]

    n_active = int(np.sum(y_vals > 0.5))
    total_profit = float(np.sum(problem["profit"] * x_vals))
    total_setup = float(np.sum(problem["setup"] * y_vals))
    obj_value = float(highs.getObjectiveValue())

    results = [
        (i, float(x_vals[i]), float(problem["profit"][i]), float(problem["setup"][i]))
        for i in range(problem["n_products"])
        if y_vals[i] > 0.5
    ]
    results.sort(key=lambda row: row[1] * row[2], reverse=True)

    return {
        "status": str(status),
        "elapsed_sec": elapsed,
        "objective_value": obj_value,
        "n_active": n_active,
        "total_profit": total_profit,
        "total_setup": total_setup,
        "x_vals": x_vals.tolist(),
        "y_vals": y_vals.tolist(),
        "top_results": [
            {
                "product_index": i,
                "production": xi,
                "unit_profit": pi,
                "setup_cost": si,
                "total_profit": xi * pi,
            }
            for i, xi, pi, si in results[:10]
        ],
    }


def print_summary(result: dict) -> None:
    n_products = len(result["x_vals"])
    print(f"\n{'=' * 50}")
    print(f"Elapsed sec      : {result['elapsed_sec']:.2f}")
    print(f"Active products  : {result['n_active']} / {n_products}")
    print(f"Total profit     : {result['total_profit']:,.0f}")
    print(f"Total setup cost : {result['total_setup']:,.0f}")
    print(f"Objective        : {result['objective_value']:.6f}")
    print(f"{'=' * 50}")

    print("\n[ Top 10 products by total profit ]")
    print(f"{'Prod':>6} {'Qty':>8} {'Profit':>10} {'Setup':>10} {'Total':>12}")
    for item in result["top_results"]:
        print(
            f"{item['product_index']:>6} "
            f"{item['production']:>8.1f} "
            f"{item['unit_profit']:>10.1f} "
            f"{item['setup_cost']:>10.1f} "
            f"{item['total_profit']:>12.0f}"
        )


def main() -> None:
    problem = load_problem_data()
    print(f"Problem variables loaded from: {PAYLOAD_OUTPUT_PATH}")

    result = solve_with_highs(problem)
    import json
    RESULT_OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Result summary written to: {RESULT_OUTPUT_PATH}")

    print_summary(result)


if __name__ == "__main__":
    main()
