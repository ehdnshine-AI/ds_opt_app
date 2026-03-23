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

UPDATE public.opt_jobs
SET reg_date = to_char(NOW(), 'YYYYMMDDHH24MISS')
WHERE reg_date IS NULL OR reg_date = '';

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

-- Seed: sample scenario (7-day planning horizon)
INSERT INTO public.opt_planning_scenarios (scenario_name, horizon_days)
VALUES ('sample_7d_4p', 7)
ON CONFLICT (scenario_name) DO NOTHING;

-- Seed: products A-D
INSERT INTO public.opt_products (product_code, product_name)
VALUES
  ('A', 'Product A'),
  ('B', 'Product B'),
  ('C', 'Product C'),
  ('D', 'Product D')
ON CONFLICT (product_code) DO NOTHING;

-- Seed: product parameters for sample_7d_4p
INSERT INTO public.opt_scenario_product_params (
  scenario_id,
  product_id,
  unit_profit,
  inventory_cost,
  backorder_penalty,
  initial_inventory
)
SELECT
  s.scenario_id,
  p.product_id,
  v.unit_profit,
  v.inventory_cost,
  v.backorder_penalty,
  v.initial_inventory
FROM public.opt_planning_scenarios s
JOIN (
  VALUES
    ('A', 70.00::NUMERIC, 3.00::NUMERIC, 20.00::NUMERIC, 10.00::NUMERIC),
    ('B', 60.00::NUMERIC, 2.00::NUMERIC, 18.00::NUMERIC, 5.00::NUMERIC),
    ('C', 90.00::NUMERIC, 4.00::NUMERIC, 25.00::NUMERIC, 8.00::NUMERIC),
    ('D', 55.00::NUMERIC, 2.00::NUMERIC, 15.00::NUMERIC, 6.00::NUMERIC)
) AS v(product_code, unit_profit, inventory_cost, backorder_penalty, initial_inventory)
  ON TRUE
JOIN public.opt_products p
  ON p.product_code = v.product_code
WHERE s.scenario_name = 'sample_7d_4p'
ON CONFLICT (scenario_id, product_id) DO UPDATE
SET
  unit_profit = EXCLUDED.unit_profit,
  inventory_cost = EXCLUDED.inventory_cost,
  backorder_penalty = EXCLUDED.backorder_penalty,
  initial_inventory = EXCLUDED.initial_inventory;

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

-- Seed: 24-variable sample MILP scenario aligned with /solve payload
INSERT INTO public.opt_milp_scenarios (scenario_name, sense, problem_type, var_count)
VALUES ('sample_7d_4p', 'max', 'MILP', 24)
ON CONFLICT (scenario_name) DO UPDATE
SET
  sense = EXCLUDED.sense,
  problem_type = EXCLUDED.problem_type,
  var_count = EXCLUDED.var_count;

INSERT INTO public.opt_milp_variables (
  milp_scenario_id, var_index, var_name, var_cat, low_bound, up_bound
)
SELECT s.milp_scenario_id, v.var_index, v.var_name, v.var_cat, v.low_bound, v.up_bound
FROM public.opt_milp_scenarios s
JOIN (
  VALUES
    (0, 'prod_t1_l1_a', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (1, 'prod_t1_l2_a', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (2, 'prod_t1_l1_b', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (3, 'prod_t1_l2_b', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (4, 'prod_t2_l1_a', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (5, 'prod_t2_l2_a', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (6, 'prod_t2_l1_b', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (7, 'prod_t2_l2_b', 'Integer', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (8, 'setup_t1_l1_a', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (9, 'setup_t1_l2_a', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (10, 'setup_t1_l1_b', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (11, 'setup_t1_l2_b', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (12, 'setup_t2_l1_a', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (13, 'setup_t2_l2_a', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (14, 'setup_t2_l1_b', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (15, 'setup_t2_l2_b', 'Binary', 0::DOUBLE PRECISION, 1::DOUBLE PRECISION),
    (16, 'inv_t1_a', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (17, 'inv_t1_b', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (18, 'inv_t2_a', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (19, 'inv_t2_b', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (20, 'back_t1_a', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (21, 'back_t1_b', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (22, 'back_t2_a', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION),
    (23, 'back_t2_b', 'Continuous', 0::DOUBLE PRECISION, 1000000::DOUBLE PRECISION)
) AS v(var_index, var_name, var_cat, low_bound, up_bound)
  ON TRUE
WHERE s.scenario_name = 'sample_7d_4p'
ON CONFLICT (milp_scenario_id, var_index) DO UPDATE
SET
  var_name = EXCLUDED.var_name,
  var_cat = EXCLUDED.var_cat,
  low_bound = EXCLUDED.low_bound,
  up_bound = EXCLUDED.up_bound;

INSERT INTO public.opt_milp_objective_coeffs (
  milp_scenario_id, var_index, coeff
)
SELECT s.milp_scenario_id, v.var_index, v.coeff
FROM public.opt_milp_scenarios s
JOIN (
  VALUES
    (0, 70::DOUBLE PRECISION), (1, 70), (2, 60), (3, 60),
    (4, 70), (5, 70), (6, 60), (7, 60),
    (8, -40), (9, -45), (10, -35), (11, -30),
    (12, -40), (13, -45), (14, -35), (15, -30),
    (16, -3), (17, -2), (18, -3), (19, -2),
    (20, -20), (21, -18), (22, -20), (23, -18)
) AS v(var_index, coeff)
  ON TRUE
WHERE s.scenario_name = 'sample_7d_4p'
ON CONFLICT (milp_scenario_id, var_index) DO UPDATE
SET coeff = EXCLUDED.coeff;

INSERT INTO public.opt_milp_constraints (
  milp_scenario_id, constraint_index, sense, rhs
)
SELECT s.milp_scenario_id, c.constraint_index, c.sense, c.rhs
FROM public.opt_milp_scenarios s
JOIN (
  VALUES
    (0, '<=', 0::DOUBLE PRECISION),
    (1, '<=', 0),
    (2, '<=', 0),
    (3, '<=', 0),
    (4, '<=', 0),
    (5, '<=', 0),
    (6, '<=', 0),
    (7, '<=', 0),
    (8, '<=', 1),
    (9, '<=', 1),
    (10, '<=', 1),
    (11, '<=', 1),
    (12, '<=', 16),
    (13, '<=', 18),
    (14, '<=', 16),
    (15, '<=', 18),
    (16, '=', 10),
    (17, '=', 10),
    (18, '=', 18),
    (19, '=', 17)
) AS c(constraint_index, sense, rhs)
  ON TRUE
WHERE s.scenario_name = 'sample_7d_4p'
ON CONFLICT (milp_scenario_id, constraint_index) DO UPDATE
SET
  sense = EXCLUDED.sense,
  rhs = EXCLUDED.rhs;

INSERT INTO public.opt_milp_constraint_coeffs (
  milp_scenario_id, constraint_index, var_index, coeff
)
SELECT s.milp_scenario_id, cc.constraint_index, cc.var_index, cc.coeff
FROM public.opt_milp_scenarios s
JOIN (
  VALUES
    (0, 0, 1::DOUBLE PRECISION), (0, 8, -32),
    (1, 1, 1), (1, 9, -30),
    (2, 2, 1), (2, 10, -40),
    (3, 3, 1), (3, 11, -36),
    (4, 4, 1), (4, 12, -32),
    (5, 5, 1), (5, 13, -30),
    (6, 6, 1), (6, 14, -40),
    (7, 7, 1), (7, 15, -36),
    (8, 8, 1), (8, 10, 1),
    (9, 9, 1), (9, 11, 1),
    (10, 12, 1), (10, 14, 1),
    (11, 13, 1), (11, 15, 1),
    (12, 0, 0.5), (12, 2, 0.4),
    (13, 1, 0.6), (13, 3, 0.5),
    (14, 4, 0.5), (14, 6, 0.4),
    (15, 5, 0.6), (15, 7, 0.5),
    (16, 0, 1), (16, 1, 1), (16, 16, -1), (16, 20, 1),
    (17, 2, 1), (17, 3, 1), (17, 17, -1), (17, 21, 1),
    (18, 4, 1), (18, 5, 1), (18, 16, 1), (18, 18, -1), (18, 20, -1), (18, 22, 1),
    (19, 6, 1), (19, 7, 1), (19, 17, 1), (19, 19, -1), (19, 21, -1), (19, 23, 1)
) AS cc(constraint_index, var_index, coeff)
  ON TRUE
WHERE s.scenario_name = 'sample_7d_4p'
ON CONFLICT (milp_scenario_id, constraint_index, var_index) DO UPDATE
SET coeff = EXCLUDED.coeff;
