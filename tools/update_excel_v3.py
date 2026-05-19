"""X7 강화 시스템 Excel 업데이트 v3 — 초기 분포 재설계
- 안전 강화: +1만 100%, +2~+4는 완만한 실패 확률
- +5부터 주요 관문 (T4 기준 11%)
- 목표 분포(T4, 내구도 없이): 4강 종료 61%, 5강 도달 30%, 6강 도달 10%
- ENERGY: +4~+10 동일 유지
- MC 시뮬 n=3000으로 노강소모 재계산
"""
import math, random, shutil, time
from openpyxl import load_workbook

SRC = r'C:\Users\hoy5343\Downloads\X7_강화시스템_티어별_수정.xlsx'
DST = r'C:\Users\hoy5343\Downloads\X7_강화시스템_v3_완만분포.xlsx'

shutil.copy2(SRC, DST)
print(f"복사 완료: {DST}")

# ──────────────────────────────────────────────────────────────
# 상수 (simulator/enhance.py 와 동기화)
# ──────────────────────────────────────────────────────────────
NEW_PROBS = {
    #     T1    T2    T3    T4    T5    T6    T7
    1:  [1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],  # 안전 강화
    2:  [0.90, 0.86, 0.82, 0.77, 0.73, 0.68, 0.63],
    3:  [0.85, 0.81, 0.77, 0.72, 0.67, 0.62, 0.57],
    4:  [0.80, 0.76, 0.72, 0.67, 0.62, 0.57, 0.52],
    5:  [0.33, 0.25, 0.19, 0.14, 0.10, 0.07, 0.05],  # 주요 관문
    6:  [0.28, 0.23, 0.18, 0.14, 0.11, 0.07, 0.05],
    7:  [0.22, 0.18, 0.13, 0.10, 0.07, 0.05, 0.04],
    8:  [0.14, 0.11, 0.08, 0.06, 0.04, 0.025, 0.020],
    9:  [0.09, 0.06, 0.04, 0.025, 0.015, 0.010, 0.010],
    10: [0.05, 0.03, 0.020, 0.012, 0.010, 0.010, 0.010],
}

ENERGY = {
    4:  {'epf': 20.0, 'boost': 2.0},   # 천장  5회
    5:  {'epf': 15.0, 'boost': 1.5},   # 천장  7회
    6:  {'epf': 10.0, 'boost': 1.0},   # 천장 10회
    7:  {'epf':  6.0, 'boost': 0.8},   # 천장 17회
    8:  {'epf':  4.0, 'boost': 0.6},   # 천장 25회
    9:  {'epf':  3.0, 'boost': 0.4},   # 천장 34회
    10: {'epf':  2.5, 'boost': 0.4},   # 천장 40회
}

TIER_LABELS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

# ──────────────────────────────────────────────────────────────
# 계산 함수
# ──────────────────────────────────────────────────────────────
def compute_step_ev():
    """단계별 기대 시도수 E(k) = 1/p(k) (no-drop 기하분포)"""
    ev = {}
    for lvl in range(1, 11):
        ev[lvl] = [1.0 / p for p in NEW_PROBS[lvl]]
    return ev

def compute_cumulative_ev(step_ev):
    """누적 기대 시도수 (1~k 합산)"""
    cum = {}
    running = [0.0] * 7
    for lvl in range(1, 11):
        for ti in range(7):
            running[ti] += step_ev[lvl][ti]
        cum[lvl] = running[:]
    return cum

def compute_ceiling_p(lvl, ti):
    """천장 도달 확률 P(천장) — lvl 4~10만 ENERGY 적용"""
    if lvl not in ENERGY:
        return 0.0
    pb  = NEW_PROBS[lvl][ti]
    epf = ENERGY[lvl]['epf']
    bst = ENERGY[lvl]['boost']
    N   = math.ceil(100.0 / epf)
    p_not = 1.0
    for k in range(N):
        pk = min(1.0, pb + k * bst / 100.0)
        p_not *= (1.0 - pk)
    return p_not

def mc_nodrop(tier_idx, n_sim=3000):
    """No-drop MC: pre[k] = +k 아이템 1개 만들기 위한 노강 기댓값.
    복구: 실패 3회 소진 → 현재 레벨 아이템 1개 소모, 3회 리셋.
    성공 시: 복구 횟수 3회로 리셋.
    """
    rng = random.Random(42 + tier_idx * 137 + n_sim)
    pre = {0: 1.0}
    for target in range(1, 11):
        total = 0.0
        for _ in range(n_sim):
            level, used, attempts = 0, 1.0, 3
            pity  = {k: [0.0, 0.0] for k in range(4, 11)}
            guard = 0
            while level < target and guard < 300_000:
                guard += 1
                tlvl = level + 1
                pb   = NEW_PROBS[tlvl][tier_idx]
                if tlvl >= 4 and tlvl in ENERGY:
                    ba, ea = pity[tlvl]
                    p_eff = 1.0 if ea >= 100.0 else min(1.0, pb + ba / 100.0)
                else:
                    p_eff = pb
                if rng.random() < p_eff:   # 성공
                    level += 1
                    if tlvl >= 4:
                        pity[tlvl] = [0.0, 0.0]
                    attempts = 3            # 성공 시 리셋
                else:                       # 실패 (단계 유지)
                    if tlvl >= 4 and tlvl in ENERGY:
                        cfg = ENERGY[tlvl]
                        pity[tlvl][0] += cfg['boost']
                        pity[tlvl][1]  = min(100.0, pity[tlvl][1] + cfg['epf'])
                    attempts -= 1           # 실패 시만 차감
                if attempts == 0 and level < target:
                    used    += pre.get(level, 1.0)
                    attempts = 3
            total += used
        pre[target] = math.floor(total / n_sim)
    return pre

def nogang_label(val):
    if val <= 2:    return '✅ 소량'
    if val <= 10:   return '🟡 약 10개↓'
    if val <= 50:   return '🟠 ~50개'
    if val <= 500:  return '🔴 ~수백개'
    if val <= 2000: return '⛔ 수천개'
    return '💀 수만개+'

# ──────────────────────────────────────────────────────────────
# 사전 계산
# ──────────────────────────────────────────────────────────────
print("\n[1/4] 기대값 계산...")
step_ev = compute_step_ev()
cum_ev  = compute_cumulative_ev(step_ev)

print("[2/4] 천장 통계 계산...")
ceil_p = {lvl: [compute_ceiling_p(lvl, ti) for ti in range(7)] for lvl in range(4, 11)}
succ_p = {lvl: [1.0 - ceil_p[lvl][ti]     for ti in range(7)] for lvl in range(4, 11)}

print("[3/4] MC 노강소모 시뮬레이션 (n=3000 × 7티어)...")
t0 = time.time()
mc_all = {}
for ti in range(7):
    mc_all[ti] = mc_nodrop(ti, n_sim=3000)
    print(f"  {TIER_LABELS[ti]} 완료  +10={mc_all[ti][10]:,}개")
print(f"  MC 완료 ({time.time()-t0:.1f}s)")

# ──────────────────────────────────────────────────────────────
# 엑셀 쓰기
# ──────────────────────────────────────────────────────────────
print("\n[4/4] Excel 업데이트...")
wb = load_workbook(DST)

# ──────────────────────────────────────────────
# 확률표 시트
# ──────────────────────────────────────────────
ws = wb['확률표']
ws.cell(3, 2).value = (
    '🔵 파란 테두리 셀 = 직접 수정 가능 | '
    '+1만 안전 강화 100% | +2~+4 완만한 실패 확률 | +5부터 주요 관문 | T4 = 기준값'
)
penalties = {lvl: '없음' for lvl in range(1, 11)}
for idx, lvl in enumerate(range(1, 11)):
    row = 8 + idx
    for ti in range(7):
        cell = ws.cell(row, 3 + ti)
        cell.value = NEW_PROBS[lvl][ti]
        cell.number_format = '0.00%'   # 소수점 2자리 % 표시
    ws.cell(row, 10).value = penalties[lvl]
print("  확률표 완료")

# ──────────────────────────────────────────────
# 기대값 시트
# ──────────────────────────────────────────────
ws2 = wb['기대값']
ws2.cell(3, 2).value = (
    '기하분포: E(k) = 1/p(k)  |  실패 시 단계 유지 (하락 없음)  |  +1 안전(100%)  |  T4 = 기준값'
)
ws2.cell(8, 2).value = '■  단계별 기대 시도수 (해당 레벨→다음 레벨 평균 시도)'
for idx, lvl in enumerate(range(1, 11)):
    row = 9 + idx
    for ti in range(7):
        ws2.cell(row, 3 + ti).value = round(step_ev[lvl][ti], 6)
    ratio = step_ev[lvl][6] / step_ev[lvl][0] if step_ev[lvl][0] > 0 else 1.0
    ws2.cell(row, 10).value = round(ratio, 6)

for idx, lvl in enumerate(range(1, 11)):
    row = 22 + idx
    for ti in range(7):
        ws2.cell(row, 3 + ti).value = round(cum_ev[lvl][ti], 6)
    ratio = cum_ev[lvl][6] / cum_ev[lvl][0] if cum_ev[lvl][0] > 0 else 1.0
    ws2.cell(row, 10).value = round(ratio, 6)
print("  기대값 완료")

# ──────────────────────────────────────────────
# 델피나드 시트
# ──────────────────────────────────────────────
ws3 = wb['델피나드']
for idx, lvl in enumerate(range(4, 11)):
    row_c = 26 + idx
    row_s = 35 + idx
    for ti in range(7):
        ws3.cell(row_c, 3 + ti).value = round(ceil_p[lvl][ti], 10)
        ws3.cell(row_s, 3 + ti).value = round(succ_p[lvl][ti], 10)
print("  델피나드 완료")

# ──────────────────────────────────────────────
# 노강소모 시트
# ──────────────────────────────────────────────
ws4 = wb['노강소모']
ws4.cell(2, 2).value = '🔧  노강 아이템 기대 소모량  (Monte Carlo n=3,000 · 천장 시스템 포함 · 단계 하락 없음)'
ws4.cell(3, 2).value = (
    '조건: 강화 3회 소진 → 현재 강화 단계 동일 아이템 1개 소모 복구  |  '
    '성공 시 횟수 3회 리셋  |  +1 안전(100%)  |  +5부터 주요 관문'
)
for idx, lvl in enumerate(range(1, 11)):
    row = 7 + idx
    for ti in range(7):
        val = mc_all[ti][lvl]
        ws4.cell(row, 3 + ti).value = val
    ws4.cell(row, 10).value = nogang_label(mc_all[3][lvl])

t4_10 = mc_all[3][10]
t7_10 = mc_all[6][10]
ws4.cell(23, 2).value = 'T4 +10'
ws4.cell(23, 3).value = f'기대 소모 ≈ {t4_10:,}개  (천장 시스템으로 소모량 현실화)'
ws4.cell(24, 2).value = 'T7 +10'
ws4.cell(24, 3).value = f'기대 소모 ≈ {t7_10:,}개  (극한 희소성 — 서버 이벤트·보호권 필수 고려)'
print("  노강소모 완료")

# ──────────────────────────────────────────────
# 요약 시트
# ──────────────────────────────────────────────
ws5 = wb['요약']
difficulty = {4:'보통', 5:'높음', 6:'높음', 7:'매우 높음', 8:'매우 높음', 9:'극한', 10:'극한+'}
for idx, lvl in enumerate(range(4, 11)):
    row = 7 + idx
    for ti in range(7):
        cell = ws5.cell(row, 3 + ti)
        cell.value = NEW_PROBS[lvl][ti]
        cell.number_format = '0.00%'
    ws5.cell(row, 10).value = difficulty[lvl]

for idx, lvl in enumerate(range(4, 11)):
    row = 18 + idx
    for ti in range(7):
        ws5.cell(row, 3 + ti).value = round(cum_ev[lvl][ti], 6)
    ratio = cum_ev[lvl][6] / cum_ev[lvl][0] if cum_ev[lvl][0] > 0 else 1.0
    ws5.cell(row, 10).value = round(ratio, 4)

for idx, lvl in enumerate(range(4, 11)):
    row = 29 + idx
    for ti in range(7):
        ws5.cell(row, 3 + ti).value = mc_all[ti][lvl]
    ws5.cell(row, 10).value = nogang_label(mc_all[3][lvl])
print("  요약 완료")

wb.save(DST)
print(f"\n✅ 저장 완료: {DST}")

# ──────────────────────────────────────────────
# 결과 요약
# ──────────────────────────────────────────────
print("\n====== 주요 수치 요약 ======")
print("\n[확률표] 전 티어")
print(f"{'강화':>4}  {'T1':>6} {'T2':>6} {'T3':>6} {'T4':>6} {'T5':>6} {'T6':>6} {'T7':>6}")
for lvl in range(1, 11):
    vals = [f"{NEW_PROBS[lvl][ti]*100:.1f}%" for ti in range(7)]
    print(f"+{lvl:2d}   " + "  ".join(f"{v:>6}" for v in vals))

print(f"\n[노강소모] +5~+10  T4 / T7")
for lvl in [5,6,7,8,9,10]:
    print(f"  +{lvl}: T4={mc_all[3][lvl]:>6,}개  T7={mc_all[6][lvl]:>8,}개")
