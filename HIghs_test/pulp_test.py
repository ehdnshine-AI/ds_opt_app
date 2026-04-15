import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from param_gen import PAYLOAD_OUTPUT_PATH, load_problem_data


BASE_DIR = Path(__file__).resolve().parent
API_RESULT_OUTPUT_PATH = BASE_DIR / "pulp_test.result.json"
DEFAULT_API_URL = "http://127.0.0.1:8000/solve"


def build_api_payload(problem: dict) -> dict:
    n_products = problem["n_products"]
    constraints = []

    for j in range(problem["n_constraints"]):
        coeffs = [float(v) for v in problem["A"][j].tolist()]
        coeffs.extend([0.0] * n_products)
        constraints.append({"coeffs": coeffs, "sense": "<=", "rhs": float(problem["b"][j])})

    for i in range(n_products):
        coeffs = [0.0] * problem["num_vars"]
        coeffs[i] = 1.0
        coeffs[n_products + i] = -float(problem["cap"][i])
        constraints.append({"coeffs": coeffs, "sense": "<=", "rhs": 0.0})

    return {
        "sense": "max",
        "objective": [float(v) for v in problem["col_cost"].tolist()],
        "constraints": constraints,
        "var_bounds": [
            {"low": float(problem["col_lower"][i]), "up": float(problem["col_upper"][i])}
            for i in range(problem["num_vars"])
        ],
        "var_cats": ["Integer" if int(v) == 1 else "Continuous" for v in problem["integrality"].tolist()],
        "solver": "HiGHS",
        "problem_type": "MILP",
        "time_limit_sec": 6000,
    }


def call_api(payload: dict, api_url: str = DEFAULT_API_URL) -> dict:
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started_at = time.time()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 502 and "timed out" in error_body:
            raise RuntimeError(
                "API call failed because the server-side solver timeout was reached. "
                "Increase SOLVER_REQUEST_TIMEOUT on the API server and restart it. "
                f"status={exc.code} body={error_body}"
            ) from exc
        raise RuntimeError(f"API call failed: status={exc.code} body={error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API call failed: {exc.reason}") from exc

    result["client_elapsed_sec"] = time.time() - started_at
    return result


def print_response_summary(result: dict) -> None:
    print(f"Request ID       : {result.get('request_id')}")
    print(f"Status           : {result.get('status')}")
    print(f"Solver           : {result.get('solver')}")
    print(f"Objective        : {result.get('objective_value')}")
    print(f"Duration(ms)     : {result.get('duration_ms')}")
    print(f"Client elapsed   : {result.get('client_elapsed_sec', 0.0):.2f}s")
    print(f"Variable count   : {len(result.get('variables', []))}")


def main() -> None:
    problem = load_problem_data()
    print(f"Problem variables loaded from: {PAYLOAD_OUTPUT_PATH}")

    payload = build_api_payload(problem)
    result = call_api(payload)
    API_RESULT_OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Result JSON written to: {API_RESULT_OUTPUT_PATH}")
    print_response_summary(result)


if __name__ == "__main__":
    main()
