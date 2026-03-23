-- DDL only
-- Combined from scripts/db_schema.sql and scripts/db_create_schema.sql

-- Create tables in public schema for PuLP solver API

CREATE TABLE IF NOT EXISTS public.opt_jobs (
  id UUID PRIMARY KEY,
  solver TEXT NOT NULL,
  status TEXT NOT NULL,
  objective DOUBLE PRECISION,
  variable_names TEXT,
  variables TEXT,
  duration_ms BIGINT NOT NULL,
  -- yyyymmdd + HH24MISS (e.g. 20260310170533)
  reg_date VARCHAR(14) NOT NULL DEFAULT to_char(NOW(), 'YYYYMMDDHH24MISS')
);

-- Backward compatible migration for existing opt_jobs schema.
ALTER TABLE public.opt_jobs
  ADD COLUMN IF NOT EXISTS reg_date VARCHAR(14);

ALTER TABLE public.opt_jobs
  ADD COLUMN IF NOT EXISTS variable_names TEXT;

ALTER TABLE public.opt_jobs
  ALTER COLUMN reg_date SET DEFAULT to_char(NOW(), 'YYYYMMDDHH24MISS');

ALTER TABLE public.opt_jobs
  ALTER COLUMN reg_date SET NOT NULL;

-- Job queue table: enqueue requests and process them in order.
-- Use queue_position for FIFO ordering.
CREATE TABLE IF NOT EXISTS public.opt_job_queue (
  queue_position BIGSERIAL PRIMARY KEY,
  request_id UUID NOT NULL,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', -- queued | running | done | failed
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_opt_job_queue_status_position
  ON public.opt_job_queue(status, queue_position);

CREATE INDEX IF NOT EXISTS idx_opt_job_queue_request_id
  ON public.opt_job_queue(request_id);

-- ============================================================
-- Production planning input schema
-- Stores reusable scenario/product parameters for optimization.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.opt_planning_scenarios (
  scenario_id BIGSERIAL PRIMARY KEY,
  scenario_name TEXT NOT NULL UNIQUE,
  horizon_days INTEGER NOT NULL CHECK (horizon_days > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.opt_products (
  product_id BIGSERIAL PRIMARY KEY,
  product_code TEXT NOT NULL UNIQUE,
  product_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.opt_scenario_product_params (
  scenario_id BIGINT NOT NULL REFERENCES public.opt_planning_scenarios(scenario_id) ON DELETE CASCADE,
  product_id BIGINT NOT NULL REFERENCES public.opt_products(product_id) ON DELETE RESTRICT,
  unit_profit NUMERIC(12,2) NOT NULL CHECK (unit_profit >= 0),
  inventory_cost NUMERIC(12,2) NOT NULL CHECK (inventory_cost >= 0),
  backorder_penalty NUMERIC(12,2) NOT NULL CHECK (backorder_penalty >= 0),
  initial_inventory NUMERIC(12,2) NOT NULL CHECK (initial_inventory >= 0),
  PRIMARY KEY (scenario_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_opt_scenario_product_params_product
  ON public.opt_scenario_product_params(product_id);

-- ============================================================
-- Generic MILP scenario schema (vector/matrix form)
-- Supports reconstructing /solve payload from DB.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.opt_milp_scenarios (
  milp_scenario_id BIGSERIAL PRIMARY KEY,
  scenario_name TEXT NOT NULL UNIQUE,
  sense TEXT NOT NULL DEFAULT 'max' CHECK (sense IN ('min', 'max')),
  problem_type TEXT NOT NULL DEFAULT 'MILP' CHECK (problem_type IN ('LP', 'MILP')),
  var_count INTEGER NOT NULL CHECK (var_count > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.opt_milp_variables (
  milp_scenario_id BIGINT NOT NULL REFERENCES public.opt_milp_scenarios(milp_scenario_id) ON DELETE CASCADE,
  var_index INTEGER NOT NULL CHECK (var_index >= 0),
  var_name TEXT NOT NULL,
  var_cat TEXT NOT NULL,
  low_bound DOUBLE PRECISION,
  up_bound DOUBLE PRECISION,
  PRIMARY KEY (milp_scenario_id, var_index)
);

CREATE TABLE IF NOT EXISTS public.opt_milp_objective_coeffs (
  milp_scenario_id BIGINT NOT NULL REFERENCES public.opt_milp_scenarios(milp_scenario_id) ON DELETE CASCADE,
  var_index INTEGER NOT NULL CHECK (var_index >= 0),
  coeff DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (milp_scenario_id, var_index)
);

CREATE TABLE IF NOT EXISTS public.opt_milp_constraints (
  milp_scenario_id BIGINT NOT NULL REFERENCES public.opt_milp_scenarios(milp_scenario_id) ON DELETE CASCADE,
  constraint_index INTEGER NOT NULL CHECK (constraint_index >= 0),
  sense TEXT NOT NULL CHECK (sense IN ('<=', '>=', '=')),
  rhs DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (milp_scenario_id, constraint_index)
);

CREATE TABLE IF NOT EXISTS public.opt_milp_constraint_coeffs (
  milp_scenario_id BIGINT NOT NULL REFERENCES public.opt_milp_scenarios(milp_scenario_id) ON DELETE CASCADE,
  constraint_index INTEGER NOT NULL CHECK (constraint_index >= 0),
  var_index INTEGER NOT NULL CHECK (var_index >= 0),
  coeff DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (milp_scenario_id, constraint_index, var_index)
);

CREATE INDEX IF NOT EXISTS idx_opt_milp_variables_scenario
  ON public.opt_milp_variables(milp_scenario_id);

CREATE INDEX IF NOT EXISTS idx_opt_milp_constraints_scenario
  ON public.opt_milp_constraints(milp_scenario_id);

CREATE INDEX IF NOT EXISTS idx_opt_milp_coeffs_scenario_constraint
  ON public.opt_milp_constraint_coeffs(milp_scenario_id, constraint_index);

-- ============================================
-- 1) 시나리오 기본정보
-- ============================================
CREATE TABLE IF NOT EXISTS public.optimization_scenario (
    scenario_id BIGSERIAL PRIMARY KEY,
    scenario_code VARCHAR(100) NOT NULL UNIQUE,
    scenario_name VARCHAR(200) NOT NULL,
    description TEXT,
    problem_type VARCHAR(50) NOT NULL DEFAULT 'MILP',
    solver_name VARCHAR(50) NOT NULL DEFAULT 'HiGHS',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

COMMENT ON TABLE public.optimization_scenario IS '최적화 시나리오 기본정보';
COMMENT ON COLUMN public.optimization_scenario.scenario_id IS '시나리오 PK';
COMMENT ON COLUMN public.optimization_scenario.scenario_code IS '시나리오 코드';
COMMENT ON COLUMN public.optimization_scenario.scenario_name IS '시나리오명';
COMMENT ON COLUMN public.optimization_scenario.description IS '설명';
COMMENT ON COLUMN public.optimization_scenario.problem_type IS '문제 유형 (LP/MILP 등)';
COMMENT ON COLUMN public.optimization_scenario.solver_name IS '사용 solver';
COMMENT ON COLUMN public.optimization_scenario.is_active IS '사용 여부';

-- ============================================
-- 2) Solver payload 저장
-- ============================================
CREATE TABLE IF NOT EXISTS public.optimization_payload (
    payload_id BIGSERIAL PRIMARY KEY,
    scenario_id BIGINT NOT NULL,
    payload_version INTEGER NOT NULL DEFAULT 1,
    sense VARCHAR(10) NOT NULL,
    solver VARCHAR(50) NOT NULL,
    problem_type VARCHAR(50) NOT NULL,
    time_limit_sec INTEGER,
    payload_json JSONB NOT NULL,
    objective_count INTEGER NOT NULL,
    constraint_count INTEGER NOT NULL,
    variable_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    CONSTRAINT fk_optimization_payload_scenario
        FOREIGN KEY (scenario_id)
        REFERENCES public.optimization_scenario (scenario_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_optimization_payload_scenario_version
        UNIQUE (scenario_id, payload_version)
);

COMMENT ON TABLE public.optimization_payload IS '최적화 solver payload 저장';
COMMENT ON COLUMN public.optimization_payload.payload_id IS 'payload PK';
COMMENT ON COLUMN public.optimization_payload.scenario_id IS '시나리오 FK';
COMMENT ON COLUMN public.optimization_payload.payload_version IS 'payload 버전';
COMMENT ON COLUMN public.optimization_payload.sense IS '목적함수 방향(max/min)';
COMMENT ON COLUMN public.optimization_payload.solver IS 'solver 이름';
COMMENT ON COLUMN public.optimization_payload.problem_type IS '문제유형';
COMMENT ON COLUMN public.optimization_payload.time_limit_sec IS '시간제한';
COMMENT ON COLUMN public.optimization_payload.payload_json IS '전체 payload JSONB';
COMMENT ON COLUMN public.optimization_payload.objective_count IS 'objective 길이';
COMMENT ON COLUMN public.optimization_payload.constraint_count IS '제약식 수';
COMMENT ON COLUMN public.optimization_payload.variable_count IS '변수 수';

-- ============================================
-- 3) 변수 인덱스 맵
-- ============================================
CREATE TABLE IF NOT EXISTS public.optimization_var_index_map (
    map_id BIGSERIAL PRIMARY KEY,
    scenario_id BIGINT NOT NULL,
    payload_version INTEGER NOT NULL DEFAULT 1,
    var_index INTEGER NOT NULL,
    var_group VARCHAR(50) NOT NULL,
    key_json JSONB NOT NULL,
    var_name_text VARCHAR(300) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    CONSTRAINT fk_var_map_scenario
        FOREIGN KEY (scenario_id)
        REFERENCES public.optimization_scenario (scenario_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_var_map_unique
        UNIQUE (scenario_id, payload_version, var_index)
);

COMMENT ON TABLE public.optimization_var_index_map IS '최적화 변수 인덱스 맵';
COMMENT ON COLUMN public.optimization_var_index_map.var_index IS 'solution 배열 인덱스';
COMMENT ON COLUMN public.optimization_var_index_map.var_group IS '변수 그룹(x, y, ship, inv, bo, regUsed, otUsed)';
COMMENT ON COLUMN public.optimization_var_index_map.key_json IS '변수 키 JSON';
COMMENT ON COLUMN public.optimization_var_index_map.var_name_text IS '가독성용 변수명 문자열';

-- ============================================
-- 4) 인덱스
-- ============================================
CREATE INDEX IF NOT EXISTS idx_optimization_payload_scenario_id
    ON public.optimization_payload (scenario_id);

CREATE INDEX IF NOT EXISTS idx_optimization_payload_payload_json_gin
    ON public.optimization_payload
    USING gin (payload_json);

CREATE INDEX IF NOT EXISTS idx_optimization_var_index_map_scenario_version
    ON public.optimization_var_index_map (scenario_id, payload_version);

CREATE INDEX IF NOT EXISTS idx_optimization_var_index_map_group
    ON public.optimization_var_index_map (var_group);

-- ============================================
-- 5) updated_at 자동 갱신 함수
-- ============================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = current_timestamp;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_optimization_scenario_updated_at ON public.optimization_scenario;
CREATE TRIGGER trg_optimization_scenario_updated_at
BEFORE UPDATE ON public.optimization_scenario
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_optimization_payload_updated_at ON public.optimization_payload;
CREATE TRIGGER trg_optimization_payload_updated_at
BEFORE UPDATE ON public.optimization_payload
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();
