@echo off
setlocal
cd /d "D:\workspace\sources\ds_opt_app"
set "PYTHONPATH=D:\workspace\sources\ds_opt_app"
set "CPLEX_SOLVER_URL="
set "DATABASE_URL="
set "PULP_LOG_DIR=D:\workspace\sources\ds_opt_app\logs"
set "SOLVER_REQUEST_TIMEOUT=30"
set "HIGHS_SOLVER_URL=http://127.0.0.1:8102/solve"
set "CBC_SOLVER_URL=http://127.0.0.1:8101/solve"
"D:\workspace\sources\ds_opt_app\.venv\Scripts\python.exe" -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 1>> "D:\workspace\sources\ds_opt_app\logs\pulp-api.out.log" 2>> "D:\workspace\sources\ds_opt_app\logs\pulp-api.err.log"
