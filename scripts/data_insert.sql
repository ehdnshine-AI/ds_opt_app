-- DML only
-- Combined from scripts/db_schema.sql

UPDATE public.opt_jobs
SET reg_date = to_char(NOW(), 'YYYYMMDDHH24MISS')
WHERE reg_date IS NULL OR reg_date = '';

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


----
-- 제품: 4종 
-- 생산라인 : 3 
-- 기간 일주일 
-- 작업자 : 8명 재고에 대한 백오더관련 된 내용도 포함
-- MILP 문제

INSERT INTO public.optimization_scenario (
    scenario_code,
    scenario_name,
    description,
    problem_type,
    solver_name
) VALUES (
    'prod_schedule_weekly',
    '주간 생산 계획 MILP 샘플',
    '제품 4종, 생산라인 3, 작업자 8명, 재고/백오더 포함 주간 MILP 최적화 샘플',
    'MILP',
    'HiGHS'
)
RETURNING scenario_id;

INSERT INTO public.optimization_payload (
    scenario_id,
    sense,
    solver,
    problem_type,
    payload_json,
    objective_count,
    constraint_count,
    variable_count
) VALUES (
    1, -- 위에서 받은 scenario_id
    'max',
    'HiGHS',
    'MILP',
    '{
        "products": ["A", "B", "C", "D"],
        "lines": ["L1", "L2", "L3"],
        "periods": [1,2,3,4,5,6,7],
        "workers": 8,
        "worker_regular_hours": 8,
        "worker_overtime_hours": 2,
        "regular_cost": 15,
        "overtime_cost": 22,
        "price": {"A": 40, "B": 52, "C": 34, "D": 65},
        "prod_cost": {"A": 22, "B": 28, "C": 18, "D": 35},
        "hold_cost": {"A": 1.0, "B": 1.2, "C": 0.8, "D": 1.5},
        "backorder_cost": {"A":4.0, "B":5.0, "C":3.0, "D":6.0},
        "initial_inventory": {"A":10,"B":8,"C":12,"D":5},
        "demand": {
            "1":{"A":20,"B":15,"C":24,"D":10},
            "2":{"A":18,"B":17,"C":22,"D":12},
            "3":{"A":22,"B":16,"C":26,"D":11},
            "4":{"A":25,"B":18,"C":28,"D":13},
            "5":{"A":20,"B":20,"C":25,"D":12},
            "6":{"A":24,"B":19,"C":27,"D":14},
            "7":{"A":26,"B":21,"C":30,"D":15}
        },
        "process_time": {
            "A":{"L1":0.8,"L2":1.0,"L3":null},
            "B":{"L1":1.1,"L2":null,"L3":0.9},
            "C":{"L1":null,"L2":0.7,"L3":1.0},
            "D":{"L1":null,"L2":null,"L3":1.2}
        }
    }',
    1,  -- objective_count
    10, -- constraint_count 예시
    56  -- variable_count 예시 (제품*라인*기간 + inventory/backorder + worker/ot 등)
);

-- 생산량 변수 x[p,l,t]
INSERT INTO public.optimization_var_index_map (scenario_id, payload_version, var_index, var_group, key_json, var_name_text)
VALUES
(1, 1, 1, 'production', '{"product":"A","line":"L1","period":1}', 'x_A_L1_1'),
(1, 1, 2, 'production', '{"product":"A","line":"L1","period":2}', 'x_A_L1_2'),
(1, 1, 3, 'production', '{"product":"B","line":"L3","period":1}', 'x_B_L3_1');

-- 재고 변수 inv[p,t]
INSERT INTO public.optimization_var_index_map (scenario_id, payload_version, var_index, var_group, key_json, var_name_text)
VALUES
(1, 1, 100, 'inventory', '{"product":"A","period":1}', 'inv_A_1'),
(1, 1, 101, 'inventory', '{"product":"B","period":1}', 'inv_B_1');

-- 백오더 변수 bo[p,t]
INSERT INTO public.optimization_var_index_map (scenario_id, payload_version, var_index, var_group, key_json, var_name_text)
VALUES
(1, 1, 200, 'backorder', '{"product":"A","period":1}', 'bo_A_1'),
(1, 1, 201, 'backorder', '{"product":"B","period":1}', 'bo_B_1');

-- 작업자/야근 변수
INSERT INTO public.optimization_var_index_map (scenario_id, payload_version, var_index, var_group, key_json, var_name_text)
VALUES
(1, 1, 300, 'worker', '{"line":"L1","period":1}', 'w_L1_1'),
(1, 1, 301, 'overtime', '{"line":"L1","period":1}', 'ot_L1_1');