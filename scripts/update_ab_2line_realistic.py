#!/usr/bin/env python3
"""Update ab_2line_7d_noinv scenario with realistic daily demand caps.

Why:
- Existing model has only capacity constraints, so it tends to produce only the
  most profitable product.
- This script adds day-level demand caps for A/B to generate realistic plans.
"""

from __future__ import annotations

import argparse
import configparser
import json
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import Json


def _load_db_dsn() -> str:
    config_path = Path(__file__).resolve().parents[1] / "app" / "util" / "db_config.ini"
    parser = configparser.ConfigParser()
    if not config_path.exists():
        raise FileNotFoundError(f"db config not found: {config_path}")
    parser.read(config_path, encoding="utf-8")

    if parser.has_section("database"):
        dsn = parser.get("database", "database_url", fallback="").strip()
        if dsn:
            return dsn

    if parser.has_section("postgres"):
        host = parser.get("postgres", "host", fallback="").strip()
        port = parser.get("postgres", "port", fallback="5432").strip()
        name = parser.get("postgres", "name", fallback="").strip()
        user = parser.get("postgres", "user", fallback="").strip()
        password = parser.get("postgres", "password", fallback="").strip()
        if all([host, port, name, user, password]):
            return f"postgresql://{user}:{password}@{host}:{port}/{name}"

    raise ValueError("database_url or postgres section is required in db_config.ini")


def _is_two_var_cap(coeffs: list[float], i1: int, i2: int) -> bool:
    nz = [i for i, v in enumerate(coeffs) if abs(float(v)) > 1e-12]
    return nz == [i1, i2] and abs(coeffs[i1] - 1.0) < 1e-12 and abs(coeffs[i2] - 1.0) < 1e-12


def _drop_existing_daily_caps(constraints: Iterable[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for c in constraints:
        coeffs = c.get("coeffs") or []
        sense = c.get("sense")
        if sense == "<=" and len(coeffs) >= 28:
            matched = False
            for day in range(7):
                base = day * 4
                if _is_two_var_cap(coeffs, base, base + 1):
                    matched = True
                    break
                if _is_two_var_cap(coeffs, base + 2, base + 3):
                    matched = True
                    break
            if matched:
                continue
        cleaned.append(c)
    return cleaned


def _build_daily_caps(n_vars: int, a_caps: list[float], b_caps: list[float]) -> list[dict]:
    caps: list[dict] = []
    for day in range(7):
        base = day * 4
        coeffs_a = [0.0] * n_vars
        coeffs_a[base] = 1.0
        coeffs_a[base + 1] = 1.0
        caps.append({"coeffs": coeffs_a, "sense": "<=", "rhs": float(a_caps[day])})

        coeffs_b = [0.0] * n_vars
        coeffs_b[base + 2] = 1.0
        coeffs_b[base + 3] = 1.0
        caps.append({"coeffs": coeffs_b, "sense": "<=", "rhs": float(b_caps[day])})
    return caps


def _load_target_payload(cur, scenario_key: str, payload_version: int) -> tuple[int, dict, int]:
    cur.execute(
        """
        select s.scenario_id, p.payload_json, p.payload_id
        from public.optimization_scenario s
        join public.optimization_payload p
          on p.scenario_id = s.scenario_id
        where (s.scenario_code = %s or s.scenario_name = %s)
          and p.payload_version = %s
        limit 1
        """,
        (scenario_key, scenario_key, payload_version),
    )
    row = cur.fetchone()
    if row:
        scenario_id, payload_json, payload_id = row
        if isinstance(payload_json, str):
            payload_json = json.loads(payload_json)
        return scenario_id, payload_json, payload_id

    cur.execute("select count(*) from public.optimization_scenario")
    scenario_count = int(cur.fetchone()[0])
    cur.execute("select count(*) from public.optimization_payload")
    payload_count = int(cur.fetchone()[0])

    if scenario_count == 0 and payload_count == 0:
        raise ValueError(
            "optimization_scenario/optimization_payload tables are empty in the configured DB. "
            "Apply the schema/seed for optimization_* first, then rerun."
        )

    cur.execute(
        """
        select scenario_id, scenario_code, scenario_name
        from public.optimization_scenario
        where scenario_code = %s or scenario_name = %s
        limit 1
        """,
        (scenario_key, scenario_key),
    )
    scenario_row = cur.fetchone()
    if not scenario_row:
        cur.execute(
            """
            select scenario_code, scenario_name
            from public.optimization_scenario
            order by scenario_code, scenario_name
            limit 10
            """
        )
        available = [f"{code} ({name})" for code, name in cur.fetchall()]
        available_text = ", ".join(available) if available else "none"
        raise ValueError(
            f"scenario '{scenario_key}' not found in public.optimization_scenario. "
            f"Available scenarios: {available_text}"
        )

    scenario_id, scenario_code, scenario_name = scenario_row
    cur.execute(
        """
        select payload_version
        from public.optimization_payload
        where scenario_id = %s
        order by payload_version
        """,
        (scenario_id,),
    )
    versions = [str(version) for (version,) in cur.fetchall()]
    if not versions:
        raise ValueError(
            f"scenario '{scenario_code}' ({scenario_name}) exists, but has no rows in "
            "public.optimization_payload"
        )

    raise ValueError(
        f"scenario '{scenario_code}' ({scenario_name}) does not have payload_version={payload_version}. "
        f"Available versions: {', '.join(versions)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update ab_2line_7d_noinv scenario to realistic plan")
    parser.add_argument("--scenario-code", default="ab_2line_7d_noinv")
    parser.add_argument("--payload-version", type=int, default=1)
    parser.add_argument(
        "--a-caps",
        default="2,3,2,3,2,3,2",
        help="7 comma-separated daily caps for product A",
    )
    parser.add_argument(
        "--b-caps",
        default="6,6,6,6,6,6,6",
        help="7 comma-separated daily caps for product B",
    )
    args = parser.parse_args()

    a_caps = [float(v.strip()) for v in args.a_caps.split(",") if v.strip()]
    b_caps = [float(v.strip()) for v in args.b_caps.split(",") if v.strip()]
    if len(a_caps) != 7 or len(b_caps) != 7:
        raise ValueError("--a-caps and --b-caps must each contain exactly 7 values")

    dsn = _load_db_dsn()
    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            scenario_id, payload_json, payload_id = _load_target_payload(
                cur,
                args.scenario_code,
                args.payload_version,
            )

            objective = payload_json.get("objective", [])
            constraints = payload_json.get("constraints", [])
            if len(objective) < 28:
                raise ValueError("unexpected payload: expected at least 28 decision variables")

            n_vars = len(objective)
            new_constraints = _drop_existing_daily_caps(constraints)
            new_constraints.extend(_build_daily_caps(n_vars, a_caps, b_caps))

            payload_json["constraints"] = new_constraints
            payload_json["time_limit_sec"] = payload_json.get("time_limit_sec", 30)
            payload_json["demand_caps"] = {
                "A": a_caps,
                "B": b_caps,
                "note": "Added for realistic no-inventory/no-backorder plan",
            }

            cur.execute(
                """
                update public.optimization_payload
                set payload_json = %s,
                    constraint_count = %s,
                    variable_count = %s,
                    objective_count = %s,
                    updated_at = current_timestamp
                where payload_id = %s
                """,
                (
                    Json(payload_json),
                    len(new_constraints),
                    len(payload_json.get("var_bounds", [])),
                    len(objective),
                    payload_id,
                ),
            )

            cur.execute(
                """
                update public.optimization_scenario
                set description = %s,
                    updated_at = current_timestamp
                where scenario_id = %s
                """,
                (
                    "A/B 2line 7d no-inventory model with daily demand caps (A,B).",
                    scenario_id,
                ),
            )

        conn.commit()
        print(
            f"updated scenario={args.scenario_code} version={args.payload_version} "
            f"constraints={len(new_constraints)}"
        )
        print(f"A caps={a_caps}")
        print(f"B caps={b_caps}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
