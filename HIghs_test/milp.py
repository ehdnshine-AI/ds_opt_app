# =========================
# 설치 (필요시)
# =========================
# !pip install highspy

import numpy as np
import time
from highspy import Highs

# ── 설정 ───────────────────────────────────────
np.random.seed(42)

N_PRODUCTS = 3000
N_CONSTRAINTS = 2000

W1 = 0.7
W2 = 0.3

# ── 데이터 생성 ────────────────────────────────
profit = np.random.uniform(10, 100, N_PRODUCTS)
setup = np.random.uniform(50, 500, N_PRODUCTS)
cap = np.random.uniform(10, 50, N_PRODUCTS)

A = np.random.uniform(0, 1, (N_CONSTRAINTS, N_PRODUCTS))
b = A.mean(axis=1) * N_PRODUCTS * 0.3

# 정규화
scale_profit = profit.sum() * cap.mean()
scale_setup = setup.sum()

# ── Highs 모델 ────────────────────────────────
highs = Highs()
highs.setMaximize()

# Solver 옵션
highs.setOptionValue("threads", 8)
highs.setOptionValue("time_limit", 6000)
highs.setOptionValue("mip_rel_gap", 0.1)
highs.setOptionValue("presolve", "off")

# =========================
# 변수 정의
# =========================
num_vars = 2 * N_PRODUCTS  # x + y

col_lower = np.zeros(num_vars, dtype=np.float64)
col_upper = np.zeros(num_vars, dtype=np.float64)
col_cost = np.zeros(num_vars, dtype=np.float64)
integrality = np.zeros(num_vars, dtype=np.int32)

# x 변수
col_lower[:N_PRODUCTS] = 0
col_upper[:N_PRODUCTS] = cap

# y 변수
col_lower[N_PRODUCTS:] = 0
col_upper[N_PRODUCTS:] = 1
integrality[N_PRODUCTS:] = 1

# =========================
# 목적식
# =========================
for i in range(N_PRODUCTS):
    col_cost[i] = (W1 * profit[i]) / scale_profit
    col_cost[N_PRODUCTS + i] = -(W2 * setup[i]) / scale_setup

# =========================
# 변수 등록
# =========================
highs.addVars(num_vars, col_lower, col_upper)
highs.changeColsCost(num_vars, np.arange(num_vars), col_cost)
highs.changeColsIntegrality(num_vars, np.arange(num_vars), integrality)

# =========================
# 제약조건
# =========================

# 자원 제약
for j in range(N_CONSTRAINTS):
    idxs = np.arange(N_PRODUCTS, dtype=np.int32)
    vals = A[j].astype(np.float64)

    highs.addRow(
        -np.inf,
        float(b[j]),
        len(idxs),
        idxs.tolist(),
        vals.tolist()
    )

# Big-M (tight)
for i in range(N_PRODUCTS):
    highs.addRow(
        -np.inf,
        0.0,
        2,
        [i, N_PRODUCTS + i],
        [1.0, -float(cap[i])]
    )

# =========================
# Solve
# =========================
print(f"Solving (highspy): {N_PRODUCTS} products, {N_CONSTRAINTS} constraints")

t0 = time.time()
highs.run()
elapsed = time.time() - t0

# =========================
# 상태 체크 (중요🔥)
# =========================
status = highs.getModelStatus()
print("\nModel Status:", status)

solution = highs.getSolution()
values = solution.col_value

# 안전 처리
if values is None or len(values) == 0:
    print("❌ No solution returned")
    exit()

# numpy 변환 (중요🔥)
values = np.array(values, dtype=np.float64)

x_vals = values[:N_PRODUCTS]
y_vals = values[N_PRODUCTS:]

# =========================
# 결과 계산
# =========================
n_active = np.sum(y_vals > 0.5)

total_profit = np.sum(profit * x_vals)
total_setup = np.sum(setup * y_vals)

obj_value = highs.getObjectiveValue()

# =========================
# 결과 출력
# =========================
print(f"\n{'='*50}")
print(f"풀이 시간        : {elapsed:.2f}초")
print(f"생산 제품 수      : {n_active} / {N_PRODUCTS}")
print(f"총 이익         : {total_profit:,.0f}")
print(f"총 셋업비용       : {total_setup:,.0f}")
print(f"Objective       : {obj_value:.6f}")
print(f"{'='*50}")

# =========================
# 상위 제품 출력
# =========================
results = [(i, x_vals[i], profit[i], setup[i]) 
           for i in range(N_PRODUCTS) if y_vals[i] > 0.5]

results.sort(key=lambda r: r[1]*r[2], reverse=True)

print("\n[ 이익 상위 10개 제품 ]")
print(f"{'제품':>6} {'생산량':>8} {'단위이익':>8} {'셋업비':>8} {'총이익':>10}")

for i, xi, pi, si in results[:10]:
    print(f" {i:>4}  {xi:>6.1f}  {pi:>6.1f}  {si:>6.1f}  {pi*xi:>8.0f}")
