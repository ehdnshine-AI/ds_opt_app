@echo off
setlocal
cd /d "D:\workspace\sources\ds_opt_app"
set "PYTHONPATH=D:\workspace\sources\ds_opt_app"
set "SOLVER_NAME=HIGHS"
set "HIGHS_THREADS=4"
set "PULP_LOG_DIR=D:\workspace\sources\ds_opt_app\logs"
"D:\workspace\sources\ds_opt_app\.venv\Scripts\python.exe" -m uvicorn app.connector_api.main:app --host 0.0.0.0 --port 8102 1>> "D:\workspace\sources\ds_opt_app\logs\pulp-solver-highs.out.log" 2>> "D:\workspace\sources\ds_opt_app\logs\pulp-solver-highs.err.log"
