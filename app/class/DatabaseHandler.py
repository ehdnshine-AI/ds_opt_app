from __future__ import annotations

"""Database access layer for job persistence.

Uses SQL files loaded by name and SQLAlchemy connections.
"""

import json
import configparser
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.api import sql_store


logger = logging.getLogger("pulp-solver-api")


@dataclass
class JobRecord:
    """Typed container for job rows."""
    request_id: str
    status: str
    objective_value: Optional[float]
    variables: list[Optional[float]]
    solver: str
    duration_ms: int
    variable_names: list[str] = field(default_factory=list)


@dataclass
class ScenarioProductParam:
    """Scenario-level product parameters loaded from DB."""
    product_code: str
    unit_profit: float
    inventory_cost: float
    backorder_penalty: float
    initial_inventory: float


@dataclass
class MilpScenarioModel:
    """Reconstructed MILP payload loaded from DB tables."""
    scenario_code: str
    scenario_name: str
    payload_version: int
    sense: str
    problem_type: str
    objective: list[float]
    constraints: list[dict]
    var_bounds: list[dict]
    var_cats: list[str]
    var_names: list[str]


class DatabaseHandler:
    """Small wrapper around SQLAlchemy engine with CRUD helpers."""
    def __init__(self, database_url: str):
        self._database_url = database_url or self._load_database_url_from_config()
        self._engine = self._build_engine(self._database_url)

    @staticmethod
    def _load_database_url_from_config() -> str:
        config_path = Path(__file__).resolve().parents[1] / "util" / "db_config.ini"
        if not config_path.exists():
            return ""

        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")

        # 1) Prefer a full URL from [database].
        if parser.has_section("database"):
            db_url = parser.get("database", "database_url", fallback="").strip()
            if db_url:
                return db_url

        # 2) Fallback: compose URL from [postgres] fields.
        if parser.has_section("postgres"):
            host = parser.get("postgres", "host", fallback="").strip()
            port = parser.get("postgres", "port", fallback="5432").strip()
            name = parser.get("postgres", "name", fallback="").strip()
            user = parser.get("postgres", "user", fallback="").strip()
            password = parser.get("postgres", "password", fallback="").strip()
            if all([host, port, name, user, password]):
                return f"postgresql://{user}:{password}@{host}:{port}/{name}"

        return ""

    @staticmethod
    def _build_engine(database_url: str):
        if not database_url:
            return None
        # Default SQLAlchemy Postgres URL uses psycopg2. We ship psycopg3, so
        # normalize to the psycopg driver when no driver is specified.
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        try:
            return create_engine(database_url, pool_pre_ping=True)
        except SQLAlchemyError:
            return None

    @property
    def enabled(self) -> bool:
        return self._engine is not None

    def _execute(self, conn, query_name: str, params: Optional[dict] = None):
        sql = sql_store.get_query(query_name)
        query_params = params or {}
        logger.info(
            "db query_name=%s sql=%s params=%s",
            query_name,
            " ".join(sql.split()),
            query_params,
        )
        return conn.execute(text(sql), query_params)

    @staticmethod
    def _is_solver_payload(payload_json: dict) -> bool:
        return all(key in payload_json for key in ("objective", "constraints", "var_bounds", "var_cats"))

    @staticmethod
    def _build_prod_schedule_milp(payload_json: dict, fallback_sense: str, fallback_problem_type: str) -> Optional[dict]:
        required_keys = (
            "lines",
            "products",
            "periods",
            "demand",
            "price",
            "prod_cost",
            "hold_cost",
            "backorder_cost",
            "initial_inventory",
            "process_time",
            "workers",
            "worker_regular_hours",
            "worker_overtime_hours",
            "overtime_cost",
        )
        if not all(key in payload_json for key in required_keys):
            return None

        lines = [str(v) for v in payload_json["lines"]]
        products = [str(v) for v in payload_json["products"]]
        periods = [str(v) for v in payload_json["periods"]]
        demand = payload_json["demand"]
        price = payload_json["price"]
        prod_cost = payload_json["prod_cost"]
        hold_cost = payload_json["hold_cost"]
        backorder_cost = payload_json["backorder_cost"]
        initial_inventory = payload_json["initial_inventory"]
        process_time = payload_json["process_time"]
        workers = float(payload_json["workers"])
        regular_hours = float(payload_json["worker_regular_hours"])
        overtime_hours = float(payload_json["worker_overtime_hours"])
        overtime_cost = float(payload_json["overtime_cost"])

        objective: list[float] = []
        var_bounds: list[dict] = []
        var_cats: list[str] = []
        var_names: list[str] = []

        prod_var_idx: dict[tuple[str, str, str], int] = {}
        inv_var_idx: dict[tuple[str, str], int] = {}
        back_var_idx: dict[tuple[str, str], int] = {}
        ot_var_idx: dict[str, int] = {}

        def add_var(name: str, coeff: float, low: float = 0.0, up: Optional[float] = None, cat: str = "Continuous") -> int:
            idx = len(objective)
            objective.append(float(coeff))
            bound: dict[str, float] = {"low": float(low)}
            if up is not None:
                bound["up"] = float(up)
            var_bounds.append(bound)
            var_cats.append(cat)
            var_names.append(name)
            return idx

        for product in products:
            for line in lines:
                cycle_time = process_time.get(product, {}).get(line)
                if cycle_time is None:
                    continue
                for period in periods:
                    prod_var_idx[(product, line, period)] = add_var(
                        f"make[{product},{line},{period}]",
                        coeff=float(price[product]) - float(prod_cost[product]),
                        low=0.0,
                        cat="Integer",
                    )

        for product in products:
            for period in periods:
                inv_var_idx[(product, period)] = add_var(
                    f"inv[{product},{period}]",
                    coeff=-float(hold_cost[product]),
                    low=0.0,
                    cat="Integer",
                )
                back_var_idx[(product, period)] = add_var(
                    f"backlog[{product},{period}]",
                    coeff=-float(backorder_cost[product]),
                    low=0.0,
                    cat="Integer",
                )

        overtime_cap = workers * overtime_hours
        for period in periods:
            ot_var_idx[period] = add_var(
                f"overtime[{period}]",
                coeff=-overtime_cost,
                low=0.0,
                up=overtime_cap,
                cat="Continuous",
            )

        constraints: list[dict] = []

        for product in products:
            for period_idx, period in enumerate(periods):
                coeffs = [0.0] * len(objective)
                for line in lines:
                    idx = prod_var_idx.get((product, line, period))
                    if idx is not None:
                        coeffs[idx] = 1.0

                coeffs[inv_var_idx[(product, period)]] = -1.0
                coeffs[back_var_idx[(product, period)]] = 1.0

                if period_idx == 0:
                    rhs = float(demand[period][product]) - float(initial_inventory[product])
                else:
                    prev_period = periods[period_idx - 1]
                    coeffs[inv_var_idx[(product, prev_period)]] = 1.0
                    coeffs[back_var_idx[(product, prev_period)]] = -1.0
                    rhs = float(demand[period][product])

                constraints.append({"coeffs": coeffs, "sense": "=", "rhs": rhs})

        regular_capacity = workers * regular_hours
        for period in periods:
            coeffs = [0.0] * len(objective)
            for product in products:
                for line in lines:
                    idx = prod_var_idx.get((product, line, period))
                    if idx is None:
                        continue
                    coeffs[idx] = float(process_time[product][line])
            coeffs[ot_var_idx[period]] = -1.0
            constraints.append({"coeffs": coeffs, "sense": "<=", "rhs": regular_capacity})

        return {
            "sense": fallback_sense or "max",
            "problem_type": fallback_problem_type or "MILP",
            "objective": objective,
            "constraints": constraints,
            "var_bounds": var_bounds,
            "var_cats": var_cats,
            "var_names": var_names,
        }

    @classmethod
    def _normalize_payload_model(cls, payload_json: dict, fallback_sense: str, fallback_problem_type: str) -> Optional[dict]:
        if cls._is_solver_payload(payload_json):
            return {
                "sense": str(payload_json.get("sense", fallback_sense or "max")),
                "problem_type": str(payload_json.get("problem_type", fallback_problem_type or "MILP")),
                "objective": payload_json.get("objective", []),
                "constraints": payload_json.get("constraints", []),
                "var_bounds": payload_json.get("var_bounds", []),
                "var_cats": payload_json.get("var_cats", []),
                "var_names": payload_json.get("var_names", []),
            }

        nested_payload = payload_json.get("payload")
        if isinstance(nested_payload, dict) and cls._is_solver_payload(nested_payload):
            return {
                "sense": str(nested_payload.get("sense", payload_json.get("sense", fallback_sense or "max"))),
                "problem_type": str(nested_payload.get("problem_type", payload_json.get("problem_type", fallback_problem_type or "MILP"))),
                "objective": nested_payload.get("objective", []),
                "constraints": nested_payload.get("constraints", []),
                "var_bounds": nested_payload.get("var_bounds", []),
                "var_cats": nested_payload.get("var_cats", []),
                "var_names": nested_payload.get("var_names", []),
            }

        return cls._build_prod_schedule_milp(payload_json, fallback_sense, fallback_problem_type)

    def ping(self) -> bool:
        if not self._engine:
            return False
        try:
            with self._engine.connect() as conn:
                self._execute(conn, "system_ping")
            return True
        except SQLAlchemyError:
            return False

    def insert_job(self, record: JobRecord) -> None:
        if not self._engine:
            return
        try:
            with self._engine.begin() as conn:
                self._execute(
                    conn,
                    "jobs_insert_completed_job",
                    {
                        "id": record.request_id,
                        "solver": record.solver,
                        "status": record.status,
                        "objective": record.objective_value,
                        "variable_names": json.dumps(record.variable_names),
                        "variables": json.dumps(record.variables),
                        "duration_ms": record.duration_ms,
                    },
                )
        except SQLAlchemyError:
            pass

    def get_job(self, request_id: str) -> Optional[JobRecord]:
        if not self._engine:
            return None
        try:
            with self._engine.connect() as conn:
                row = self._execute(
                    conn,
                    "jobs_select_completed_job_by_id",
                    {"id": request_id},
                ).first()
                if not row:
                    return None
                variables = json.loads(row.variables) if row.variables else []
                variable_names = json.loads(row.variable_names) if row.variable_names else []
                if not variable_names and variables:
                    variable_names = [f"x{i}" for i in range(len(variables))]
                return JobRecord(
                    request_id=row.id,
                    status=row.status,
                    objective_value=row.objective,
                    variables=variables,
                    variable_names=variable_names,
                    solver=row.solver,
                    duration_ms=row.duration_ms,
                )
        except SQLAlchemyError:
            return None

    def job_exists(self, request_id: str) -> Optional[bool]:
        if not self._engine:
            return None
        try:
            with self._engine.connect() as conn:
                row = self._execute(
                    conn,
                    "jobs_check_completed_job_exists_by_id",
                    {"id": request_id},
                ).first()
                return row is not None
        except SQLAlchemyError:
            return None

    def delete_job(self, request_id: str) -> Optional[int]:
        if not self._engine:
            return None
        try:
            with self._engine.begin() as conn:
                result = self._execute(
                    conn,
                    "jobs_delete_completed_job_by_id",
                    {"id": request_id},
                )
                return result.rowcount
        except SQLAlchemyError:
            return None

    def get_scenario_product_params(self, scenario_name: str) -> Optional[list[ScenarioProductParam]]:
        if not self._engine:
            return None
        try:
            with self._engine.connect() as conn:
                rows = self._execute(
                    conn,
                    "planning_select_product_params_by_scenario_name",
                    {"scenario_name": scenario_name},
                ).all()
                return [
                    ScenarioProductParam(
                        product_code=row.product_code,
                        unit_profit=float(row.unit_profit),
                        inventory_cost=float(row.inventory_cost),
                        backorder_penalty=float(row.backorder_penalty),
                        initial_inventory=float(row.initial_inventory),
                    )
                    for row in rows
                ]
        except SQLAlchemyError:
            return None

    def get_milp_scenario_model(self, scenario_key: str, payload_version: Optional[int] = None) -> Optional[dict]:
        """Load MILP scenario payload stored in optimization_* tables.

        Returns:
        - None: DB error
        - {}: scenario not found
        - dict: model components for /solve payload
        """
        if not self._engine:
            return None
        try:
            with self._engine.connect() as conn:
                if payload_version is None:
                    payload_row = self._execute(
                        conn,
                        "optimization_select_latest_payload_by_scenario_key",
                        {"scenario_key": scenario_key},
                    ).first()
                else:
                    payload_row = self._execute(
                        conn,
                        "optimization_select_payload_by_scenario_key_and_version",
                        {"scenario_key": scenario_key, "payload_version": payload_version},
                    ).first()

                if not payload_row:
                    return {}

                payload_json = payload_row.payload_json
                if isinstance(payload_json, str):
                    payload_json = json.loads(payload_json)
                if not isinstance(payload_json, dict):
                    return None

                normalized_model = self._normalize_payload_model(
                    payload_json,
                    str(payload_row.sense or payload_json.get("sense", "max")),
                    str(payload_row.problem_type or payload_json.get("problem_type", "MILP")),
                )
                if normalized_model is None:
                    logger.info("db payload_json keys=%s", sorted(payload_json.keys()))
                    return None

                objective = normalized_model["objective"]
                constraints = normalized_model["constraints"]
                var_bounds = normalized_model["var_bounds"]
                var_cats = normalized_model["var_cats"]

                if not isinstance(objective, list) or not isinstance(constraints, list):
                    return None
                if not isinstance(var_bounds, list) or not isinstance(var_cats, list):
                    return None

                var_count = len(objective)
                if len(var_bounds) != var_count or len(var_cats) != var_count:
                    return None

                var_names = normalized_model.get("var_names", [])
                if len(var_names) != var_count:
                    var_map_rows = self._execute(
                        conn,
                        "optimization_select_var_index_map_by_scenario_id_and_version",
                        {"scenario_id": payload_row.scenario_id, "payload_version": payload_row.payload_version},
                    ).all()

                    var_names = [f"x{i}" for i in range(var_count)]
                    for row in var_map_rows:
                        idx = int(row.var_index)
                        if 0 <= idx < var_count:
                            var_names[idx] = row.var_name_text

                model = MilpScenarioModel(
                    scenario_code=payload_row.scenario_code,
                    scenario_name=payload_row.scenario_name,
                    payload_version=int(payload_row.payload_version),
                    sense=str(normalized_model["sense"]),
                    problem_type=str(normalized_model["problem_type"]),
                    objective=[float(v) for v in objective],
                    constraints=constraints,
                    var_bounds=var_bounds,
                    var_cats=[str(v) for v in var_cats],
                    var_names=var_names,
                )
                return {
                    "scenario_code": model.scenario_code,
                    "scenario_name": model.scenario_name,
                    "payload_version": model.payload_version,
                    "sense": model.sense,
                    "problem_type": model.problem_type,
                    "objective": model.objective,
                    "constraints": model.constraints,
                    "var_bounds": model.var_bounds,
                    "var_cats": model.var_cats,
                    "var_names": model.var_names,
                }
        except SQLAlchemyError:
            return None
