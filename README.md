# PuLP Solver Platform

PuLP 기반 최적화 API 서버입니다. 외부 요청을 받는 API와 실제 Solver를 실행하는 Connector를 분리했고, PostgreSQL을 연결하면 작업 결과와 시나리오 기반 모델을 저장/조회할 수 있습니다.

## 구성 개요

```text
Client
  -> app/api/main.py
     -> app/api/solver_client.py
        -> app/connector_api/main.py
           -> app/solver/pulp_solver.py
              -> CBC / HiGHS / CPLEX

Optional:
app/api/main.py
  -> app/class/DatabaseHandler.py
     -> PostgreSQL
```

핵심 역할은 다음과 같습니다.

- `app/api/main.py`
  외부 진입점입니다. `/solve`, `/scenarios/solve`, `/scenarios/milp/solve`, `/jobs/{request_id}`를 제공합니다.
- `app/connector_api/main.py`
  개별 Solver 서비스입니다. `SOLVER_NAME` 환경변수에 따라 CBC, HiGHS, CPLEX 중 하나를 담당합니다.
- `app/solver/pulp_solver.py`
  PuLP 모델 생성과 실제 solve 실행 로직입니다.
- `app/class/DatabaseHandler.py`
  SQLAlchemy 기반 DB 접근 레이어입니다.
- `app/api/sql_store.py`
  `app/sql/*.sql`의 named query를 읽어옵니다.
- `scripts/create_tables.sql`
  DDL 전용 스키마 생성 스크립트입니다.
- `scripts/data_insert.sql`
  seed/update용 DML 스크립트입니다.

## 디렉터리

```text
app/
  api/
    main.py
    solver_client.py
    sql_store.py
  connector_api/
    main.py
  solver/
    pulp_solver.py
  class/
    DatabaseHandler.py
  sql/
    quries.sql
    *.sq_
  util/
    db_config.ini
    connector/
scripts/
  create_tables.sql
  data_insert.sql
  update_ab_2line_realistic.py
tests/
docs/
install.script
requirements.txt
```

## 지원 기능

- 일반 LP/MILP solve 요청 전달
- 시나리오 기반 LP 자동 생성 후 solve
- DB payload 기반 MILP 모델 복원 후 solve
- 완료 작업 결과 저장/조회/삭제
- 요청/응답 로그 파일 기록

## 요구 사항

- Python 3.12 계열 권장
- PostgreSQL 선택 사항
- CBC는 기본 사용 가능
- HiGHS는 `pulp[highs]`, `highspy` 필요
- CPLEX는 코드 경로는 있으나 실행 환경에 CPLEX가 별도 설치되어 있어야 합니다

패키지 목록은 [requirements.txt](/home/dnshine/sources/opt_app/requirements.txt)에 있습니다.

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

또는:

```bash
./install.script install
```

## 실행

### 1. Solver Connector 실행

CBC:

```bash
export SOLVER_NAME=CBC
uvicorn app.connector_api.main:app --host 0.0.0.0 --port 8101
```

HiGHS:

```bash
export SOLVER_NAME=HIGHS
export HIGHS_THREADS=4
uvicorn app.connector_api.main:app --host 0.0.0.0 --port 8102
```

### 2. API 실행

```bash
export CBC_SOLVER_URL=http://127.0.0.1:8101/solve
export HIGHS_SOLVER_URL=http://127.0.0.1:8102/solve
export SOLVER_REQUEST_TIMEOUT=30
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

### 3. 배포 스크립트 사용

[install.script](/home/dnshine/sources/opt_app/install.script)는 로컬 백그라운드 실행용 래퍼입니다.

```bash
./install.script start-solvers
./install.script start-api
./install.script start-all
./install.script status
./install.script stop-all
./install.script restart-all
./install.script deploy
```

현재 스크립트는 CBC, HiGHS, API를 실행합니다. CPLEX 프로세스는 자동 기동 대상에 포함되어 있지 않습니다.

## 환경 변수

### API

- `CBC_SOLVER_URL`
- `HIGHS_SOLVER_URL`
- `CPLEX_SOLVER_URL`
- `SOLVER_REQUEST_TIMEOUT`
- `DATABASE_URL`
- `PULP_LOG_DIR`

### Connector

- `SOLVER_NAME`
- `HIGHS_THREADS`
- `OMP_NUM_THREADS`
- `PULP_LOG_DIR`

### install.script 주요 변수

- `CBC_HOST`, `CBC_PORT`
- `HIGHS_HOST`, `HIGHS_PORT`
- `PULP_API_HOST`, `PULP_API_PORT`
- `RUN_DIR`, `LOG_DIR`
- `VENV_DIR`, `PYTHON_BIN`, `PIP_BIN`

## DB 설정

DB 연결은 두 방식 중 하나로 읽습니다.

1. `DATABASE_URL` 환경변수
2. [app/util/db_config.ini](/home/dnshine/sources/opt_app/app/util/db_config.ini)

`DatabaseHandler`는 다음 순서로 DB URL을 구성합니다.

- `[database]` 섹션의 `database_url`
- 없으면 `[postgres]`의 `host`, `port`, `name`, `user`, `password`

PostgreSQL URL에 드라이버가 없으면 내부적으로 `postgresql+psycopg://`로 보정합니다.

## 스키마 초기화

DDL과 DML은 분리되어 있습니다.

1. 테이블/인덱스/함수 생성
2. seed 데이터 입력

```bash
psql "$DATABASE_URL" -f scripts/create_tables.sql
psql "$DATABASE_URL" -f scripts/data_insert.sql
```

관련 파일:

- [scripts/create_tables.sql](/home/dnshine/sources/opt_app/scripts/create_tables.sql)
- [scripts/data_insert.sql](/home/dnshine/sources/opt_app/scripts/data_insert.sql)
- [scripts/db_schema.sql](/home/dnshine/sources/opt_app/scripts/db_schema.sql)
- [scripts/db_create_schema.sql](/home/dnshine/sources/opt_app/scripts/db_create_schema.sql)

## API 엔드포인트

### `GET /healthz`

API 프로세스 상태를 확인합니다.

응답:

```json
{
  "ok": true,
  "db_configured": false
}
```

### `GET /readyz`

DB가 설정되어 있으면 ping까지 확인합니다.

응답:

```json
{
  "ok": true,
  "db_configured": true,
  "db_reachable": true
}
```

### `POST /solve`

일반 LP/MILP solve 요청입니다.

예시:

```bash
curl -X POST http://127.0.0.1:8000/solve \
  -H "Content-Type: application/json" \
  -d '{
    "sense": "min",
    "objective": [2, 3],
    "constraints": [
      {"coeffs": [1, 2], "sense": ">=", "rhs": 8},
      {"coeffs": [3, 1], "sense": ">=", "rhs": 9}
    ],
    "var_bounds": [{"low": 0}, {"low": 0}],
    "var_cats": ["Continuous", "Continuous"],
    "solver": "HiGHS",
    "problem_type": "LP",
    "time_limit_sec": 30
  }'
```

주요 필드:

- `sense`: `min` 또는 `max`
- `objective`: 목적함수 계수 배열
- `constraints`: `coeffs`, `sense`, `rhs`
- `var_bounds`: 변수별 `low`, `up`
- `var_cats`: `Continuous`, `Integer`, `Binary`
- `solver`: `CBC`, `HiGHS`, `CPLEX`
- `problem_type`: `LP`, `MILP`

### `POST /scenarios/solve`

DB의 `opt_planning_scenarios`, `opt_products`, `opt_scenario_product_params`를 읽어 간단한 LP를 구성합니다.

내부 규칙:

- 목적함수 계수 = `unit_profit - inventory_cost`
- 변수 상한 = `initial_inventory`
- 변수 유형 = 전부 `Continuous`
- 문제 유형 = `LP`
- 목적 = `max`

예시:

```bash
curl -X POST http://127.0.0.1:8000/scenarios/solve \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_name": "sample_7d_4p",
    "solver": "HiGHS"
  }'
```

### `POST /scenarios/milp/solve`

DB의 `optimization_scenario`, `optimization_payload`, `optimization_var_index_map`를 기준으로 payload를 복원한 뒤 solve합니다.

예시:

```bash
curl -X POST http://127.0.0.1:8000/scenarios/milp/solve \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_name": "sample_7d_4p",
    "solver": "HiGHS",
    "payload_version": 1,
    "time_limit_sec": 30
  }'
```

`payload_version`을 생략하면 최신 버전을 조회합니다.

### `GET /jobs/{request_id}`

DB에 저장된 solve 결과를 조회합니다.

### `DELETE /jobs/{request_id}`

DB에 저장된 solve 결과를 삭제합니다.

## Solver Connector API

Connector 서비스는 다음 엔드포인트를 가집니다.

- `GET /healthz`
- `POST /solve`

`POST /solve`는 API가 전달한 payload를 받아 `problem_type`에 따라 분기합니다.

- `LP` -> `solve_linear_problem`
- `MILP` -> `solve_milp_problem`

또한 connector의 `SOLVER_NAME`과 요청의 `solver`가 다르면 400을 반환합니다.

## SQL 구조

### 런타임에서 실제 사용하는 쿼리

실제 `DatabaseHandler`는 [app/sql/quries.sql](/home/dnshine/sources/opt_app/app/sql/quries.sql)의 named query를 사용합니다.

예:

- `system_ping`
- `jobs_insert_completed_job`
- `planning_select_product_params_by_scenario_name`
- `optimization_select_latest_payload_by_scenario_key`

### 참고용 legacy 쿼리 파일

다음 파일들도 저장소에 남아 있습니다.

- [app/sql/pulp_jobs.sq_](/home/dnshine/sources/opt_app/app/sql/pulp_jobs.sq_)
- [app/sql/planning_scenarios.sq_](/home/dnshine/sources/opt_app/app/sql/planning_scenarios.sq_)
- [app/sql/milp_scenarios.sq_](/home/dnshine/sources/opt_app/app/sql/milp_scenarios.sq_)
- [app/sql/optimization_payload.sq_](/home/dnshine/sources/opt_app/app/sql/optimization_payload.sq_)

현재 로더는 `*.sql`만 읽기 때문에, 런타임 기준으로는 `quries.sql`이 중요합니다.

## 로그

기본 로그 디렉터리는 `./logs`입니다. `PULP_LOG_DIR`로 변경할 수 있습니다.

주요 로그 파일:

- `logs/solver.log`
- `logs/solver_connector.log`
- `logs/pulp-api.out.log`
- `logs/pulp-solver-cbc.out.log`
- `logs/pulp-solver-highs.out.log`

## 테스트

```bash
pytest
```

테스트 파일:

- [tests/test_api_main.py](/home/dnshine/sources/opt_app/tests/test_api_main.py)
- [tests/test_connector_api.py](/home/dnshine/sources/opt_app/tests/test_connector_api.py)
- [tests/test_sql_store.py](/home/dnshine/sources/opt_app/tests/test_sql_store.py)

테스트는 주로 다음을 검증합니다.

- API 입력 검증
- Connector 라우팅
- SQL named query 로딩
- 시나리오 기반 solve 흐름

## 참고 파일

- [docs/api.md](/home/dnshine/sources/opt_app/docs/api.md)
- [docs/pulp_api.postman_collection.json](/home/dnshine/sources/opt_app/docs/pulp_api.postman_collection.json)
- [scripts/update_ab_2line_realistic.py](/home/dnshine/sources/opt_app/scripts/update_ab_2line_realistic.py)

## 주의 사항

- 저장소에 `docker-compose.yml`은 현재 없습니다.
- `README`의 실행 방법은 현재 코드 기준으로 정리했습니다.
- `tests` 일부는 현재 구현 응답 필드와 완전히 일치하지 않는 흔적이 있어, 문서는 테스트보다 실제 앱 코드를 우선 기준으로 작성했습니다.
# ds_opt_app
