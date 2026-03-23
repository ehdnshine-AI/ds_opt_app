# PuLP Solver API Specification (Markdown)

## Base URL
- Local: `http://localhost:8000`

## Endpoints

### GET `/healthz`
**Description**: 서비스 및 DB 연결 상태 확인

**Response 200**
```json
{
  "ok": true,
  "db": true
}
```

---

### POST `/solve`
**Description**: 최적화 문제를 solve 요청합니다. PuLP API는 solver connector로 요청을 전달합니다.

**Request Body**
```json
{
  "sense": "min",
  "objective": [2, 3],
  "constraints": [
    {"coeffs": [1, 2], "sense": ">=", "rhs": 8},
    {"coeffs": [3, 1], "sense": ">=", "rhs": 9}
  ],
  "var_bounds": [
    {"low": 0, "up": 10},
    {"low": 0}
  ],
  "var_cats": ["Binary", "Continuous"],
  "solver": "HiGHS",
  "problem_type": "MILP",
  "time_limit_sec": 10
}
```

**Parameters**
- `sense` (string): `min | max`
- `objective` (number[]): 목적함수 계수
- `constraints` (Constraint[]): 제약식 목록
  - `coeffs` (number[]): 변수 계수
  - `sense` (string): `<= | >= | =`
  - `rhs` (number): 우변 값
- `var_bounds` (object[] | null): 변수별 bound (예: `{low, up}`)
- `var_cats` (string[] | null): 변수 타입 (예: `Continuous`, `Binary`, `Integer`)
- `solver` (string): `CBC | HiGHS | CPLEX`
- `problem_type` (string): `LP | MILP` (default `MILP`)
- `time_limit_sec` (number | null): 시간 제한(초)

**Response 200**
```json
{
  "request_id": "3e1f2c2e-7b06-4b6c-9f6b-0b3fd4a6a35c",
  "status": "Optimal",
  "objective_value": 15.0,
  "variables": [1.0, 2.0],
  "solver": "HiGHS",
  "duration_ms": 12
}
```

**Error Responses**
- `400`: 입력 검증 실패
- `502`: solver connector 호출 실패
- `503`: solver 미지원/미설치

---

### GET `/jobs/{request_id}`
**Description**: 저장된 job 조회

**Response 200**
```json
{
  "request_id": "3e1f2c2e-7b06-4b6c-9f6b-0b3fd4a6a35c",
  "status": "Optimal",
  "objective_value": 15.0,
  "variables": [1.0, 2.0],
  "solver": "HiGHS",
  "duration_ms": 12
}
```

**Error Responses**
- `404`: Job not found
- `503`: Database not configured

---

### DELETE `/jobs/{request_id}`
**Description**: 저장된 job 삭제

**Response 200**
```json
{
  "detail": "Job deleted"
}
```

**Error Responses**
- `404`: Job not found
- `503`: Database not configured

---

## Notes
- `solver`가 지원되지 않으면 `${solver} is not available` 메시지로 실패합니다.
- `problem_type` 기본값은 `MILP`입니다.
