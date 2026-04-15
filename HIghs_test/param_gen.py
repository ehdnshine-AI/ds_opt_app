import json
from pathlib import Path

import numpy as np


BASE_DIR = Path(__file__).resolve().parent
PAYLOAD_OUTPUT_PATH = BASE_DIR / "payload.variable.json"

SEED = 42
N_PRODUCTS = 200
N_CONSTRAINTS = 300

W1 = 0.7
W2 = 0.3


def build_problem_data() -> dict:
    np.random.seed(SEED)

    profit = np.random.uniform(10, 100, N_PRODUCTS)
    setup = np.random.uniform(50, 500, N_PRODUCTS)
    cap = np.random.uniform(10, 50, N_PRODUCTS)

    A = np.random.uniform(0, 1, (N_CONSTRAINTS, N_PRODUCTS))
    b = A.mean(axis=1) * N_PRODUCTS * 0.3

    scale_profit = profit.sum() * cap.mean()
    scale_setup = setup.sum()

    num_vars = 2 * N_PRODUCTS

    col_lower = np.zeros(num_vars, dtype=np.float64)
    col_upper = np.zeros(num_vars, dtype=np.float64)
    col_cost = np.zeros(num_vars, dtype=np.float64)
    integrality = np.zeros(num_vars, dtype=np.int32)

    col_lower[:N_PRODUCTS] = 0
    col_upper[:N_PRODUCTS] = cap

    col_lower[N_PRODUCTS:] = 0
    col_upper[N_PRODUCTS:] = 1
    integrality[N_PRODUCTS:] = 1

    for i in range(N_PRODUCTS):
        col_cost[i] = (W1 * profit[i]) / scale_profit
        col_cost[N_PRODUCTS + i] = -(W2 * setup[i]) / scale_setup

    return {
        "seed": SEED,
        "n_products": N_PRODUCTS,
        "n_constraints": N_CONSTRAINTS,
        "weights": {"w1": W1, "w2": W2},
        "profit": profit,
        "setup": setup,
        "cap": cap,
        "A": A,
        "b": b,
        "scale_profit": scale_profit,
        "scale_setup": scale_setup,
        "num_vars": num_vars,
        "col_lower": col_lower,
        "col_upper": col_upper,
        "col_cost": col_cost,
        "integrality": integrality,
    }


def export_problem_data(problem: dict, output_path: Path = PAYLOAD_OUTPUT_PATH) -> None:
    payload = {
        "seed": problem["seed"],
        "n_products": problem["n_products"],
        "n_constraints": problem["n_constraints"],
        "weights": problem["weights"],
        "scale_profit": float(problem["scale_profit"]),
        "scale_setup": float(problem["scale_setup"]),
        "num_vars": int(problem["num_vars"]),
        "profit": problem["profit"].tolist(),
        "setup": problem["setup"].tolist(),
        "cap": problem["cap"].tolist(),
        "A": problem["A"].tolist(),
        "b": problem["b"].tolist(),
        "col_lower": problem["col_lower"].tolist(),
        "col_upper": problem["col_upper"].tolist(),
        "col_cost": problem["col_cost"].tolist(),
        "integrality": problem["integrality"].tolist(),
        "variable_names": [f"x_{i}" for i in range(problem["n_products"])]
        + [f"y_{i}" for i in range(problem["n_products"])],
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_problem_data(input_path: Path = PAYLOAD_OUTPUT_PATH) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return {
        "seed": payload["seed"],
        "n_products": int(payload["n_products"]),
        "n_constraints": int(payload["n_constraints"]),
        "weights": payload["weights"],
        "scale_profit": float(payload["scale_profit"]),
        "scale_setup": float(payload["scale_setup"]),
        "num_vars": int(payload["num_vars"]),
        "profit": np.array(payload["profit"], dtype=np.float64),
        "setup": np.array(payload["setup"], dtype=np.float64),
        "cap": np.array(payload["cap"], dtype=np.float64),
        "A": np.array(payload["A"], dtype=np.float64),
        "b": np.array(payload["b"], dtype=np.float64),
        "col_lower": np.array(payload["col_lower"], dtype=np.float64),
        "col_upper": np.array(payload["col_upper"], dtype=np.float64),
        "col_cost": np.array(payload["col_cost"], dtype=np.float64),
        "integrality": np.array(payload["integrality"], dtype=np.int32),
        "variable_names": payload["variable_names"],
    }


def main() -> None:
    problem = build_problem_data()
    export_problem_data(problem)
    print(f"Problem variables written to: {PAYLOAD_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
