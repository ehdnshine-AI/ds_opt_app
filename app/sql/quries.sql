-- name: system_ping
-- Health check query used to validate DB connectivity.
SELECT 1;

-- name: jobs_insert_completed_job
-- Insert a completed optimization job record.
INSERT INTO public.opt_jobs(id, solver, status, objective, variable_names, variables, duration_ms)
VALUES (:id, :solver, :status, :objective, :variable_names, :variables, :duration_ms);

-- name: jobs_select_completed_job_by_id
-- Fetch a completed optimization job by request id.
SELECT id, solver, status, objective, variable_names, variables, duration_ms
FROM public.opt_jobs
WHERE id = :id;

-- name: jobs_check_completed_job_exists_by_id
-- Check whether a completed optimization job exists by request id.
SELECT 1
FROM public.opt_jobs
WHERE id = :id;

-- name: jobs_delete_completed_job_by_id
-- Delete a completed optimization job by request id.
DELETE FROM public.opt_jobs
WHERE id = :id;

-- name: planning_select_product_params_by_scenario_name
-- Fetch product-level planning parameters for a planning scenario.
SELECT
  p.product_code,
  spp.unit_profit,
  spp.inventory_cost,
  spp.backorder_penalty,
  spp.initial_inventory
FROM public.opt_planning_scenarios s
JOIN public.opt_scenario_product_params spp
  ON spp.scenario_id = s.scenario_id
JOIN public.opt_products p
  ON p.product_id = spp.product_id
WHERE s.scenario_name = :scenario_name
ORDER BY p.product_code;

-- name: optimization_select_latest_payload_by_scenario_key
-- Load the latest active optimization payload by scenario code or scenario name.
SELECT
  s.scenario_id,
  s.scenario_code,
  s.scenario_name,
  s.problem_type AS scenario_problem_type,
  s.solver_name AS scenario_solver_name,
  p.payload_id,
  p.payload_version,
  p.sense,
  p.solver,
  p.problem_type,
  p.time_limit_sec,
  p.payload_json
FROM public.optimization_scenario s
JOIN public.optimization_payload p
  ON p.scenario_id = s.scenario_id
WHERE s.is_active = TRUE
  AND (s.scenario_code = :scenario_key OR s.scenario_name = :scenario_key)
ORDER BY p.payload_version DESC, p.payload_id DESC
LIMIT 1;

-- name: optimization_select_payload_by_scenario_key_and_version
-- Load an active optimization payload by scenario code or scenario name and payload version.
SELECT
  s.scenario_id,
  s.scenario_code,
  s.scenario_name,
  s.problem_type AS scenario_problem_type,
  s.solver_name AS scenario_solver_name,
  p.payload_id,
  p.payload_version,
  p.sense,
  p.solver,
  p.problem_type,
  p.time_limit_sec,
  p.payload_json
FROM public.optimization_scenario s
JOIN public.optimization_payload p
  ON p.scenario_id = s.scenario_id
WHERE s.is_active = TRUE
  AND (s.scenario_code = :scenario_key OR s.scenario_name = :scenario_key)
  AND p.payload_version = :payload_version
LIMIT 1;

-- name: optimization_select_var_index_map_by_scenario_id_and_version
-- Load variable labels for a scenario payload.
SELECT var_index, var_name_text
FROM public.optimization_var_index_map
WHERE scenario_id = :scenario_id
  AND payload_version = :payload_version
ORDER BY var_index;

-- name: milp_select_scenario_by_name
-- Fetch MILP scenario metadata by name.
SELECT milp_scenario_id, scenario_name, sense, problem_type, var_count
FROM public.opt_milp_scenarios
WHERE scenario_name = :scenario_name;

-- name: milp_select_variables_by_scenario_id
-- Fetch variable definitions for a MILP scenario.
SELECT var_index, var_name, var_cat, low_bound, up_bound
FROM public.opt_milp_variables
WHERE milp_scenario_id = :milp_scenario_id
ORDER BY var_index;

-- name: milp_select_objective_coeffs_by_scenario_id
-- Fetch objective coefficients for a MILP scenario.
SELECT var_index, coeff
FROM public.opt_milp_objective_coeffs
WHERE milp_scenario_id = :milp_scenario_id
ORDER BY var_index;

-- name: milp_select_constraints_by_scenario_id
-- Fetch constraint headers for a MILP scenario.
SELECT constraint_index, sense, rhs
FROM public.opt_milp_constraints
WHERE milp_scenario_id = :milp_scenario_id
ORDER BY constraint_index;

-- name: milp_select_constraint_coeffs_by_scenario_id
-- Fetch sparse matrix coefficients for MILP scenario constraints.
SELECT constraint_index, var_index, coeff
FROM public.opt_milp_constraint_coeffs
WHERE milp_scenario_id = :milp_scenario_id
ORDER BY constraint_index, var_index;
