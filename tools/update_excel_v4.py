"""X7 강화 시스템 Excel 업데이트 v4
- 확률표 시트의 T1 기준값 + 수식 패턴을 읽어 나머지 계산
- 기대값/델피나드/노강소모/요약 시트 재계산
- 확률표 셀 컬러 서식 재적용 (범례 기준)
"""
import math, random, shutil, time
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

SRC = r'C:\Users\hoy5343\Downloads\X7_강화시스템_v3_완만분포.xlsx'
DST = r'C:\Users\hoy5343\Downloads\X7_강화시스템_v4_완만분포.xlsx'

shutil.copy2(SRC, DST)
print(f"복사 완료: {DST}")

# ──────────────────────────────────────────────────────────────
# 1. 확률표에서 T1 기준값 읽기 + 수식 패턴으로 전 티어 계산
# ──────────────────────────────────────────────────────────────
wb = load_workbook(DST, data_only=False)
ws_prob = wb['확률표']

# T1 기준값 (col C, row 8~17)
t1 = {}
for idx, lvl in enumerate(range(1, 11)):
    val = ws_prob.cell(8 + idx, 3).value
    t1[lvl] = float(val) if not isinstance(val, str) else 1.0

print("\n[T1 기준값]")
for lvl in range(1, 11):
    print(f"  +{lvl}: {t1[lvl]*100:.2f}%")

def eval_probs(t1_vals):
    """수식 패턴으로 전 티어 확률 계산.

    +1      : 전 티어 100%
    +2 ~ +7 : T2=T1*0.9, T3~T7 = 등차수열 (step = T1*0.1)
    +8      : 티어당 -1.5%p 감소
    +9      : 티어당 -1.0%p 감소
    +10     : 티어당 -0.5%p 감소
    """
    probs = {}
    probs[1] = [1.0] * 7

    for lvl in range(2, 8):
        base = t1_vals[lvl]
        step = base * 0.1          # T1*0.9, 이후 등차
        probs[lvl] = [max(0.001, round(base - i * step, 6)) for i in range(7)]

    flat_steps = {8: 0.015, 9: 0.010, 10: 0.005}
    for lvl in range(8, 11):
        base = t1_vals[lvl]
        s    = flat_steps[lvl]
        probs[lvl] = [max(0.001, round(base - i * s, 6)) for i in range(7)]

    return probs

PROBS = eval_probs(t1)

print("\n[전 티어 확률]")
print(f"{'강화':>4}  " + "  ".join(f"T{i+1:>5}" for i in range(7)))
for lvl in range(1, 11):
    vals = "  ".join(f"{v*100:>6.2f}%" for v in PROBS[lvl])
    print(f"+{lvl:2d}   {vals}")

# ──────────────────────────────────────────────────────────────
# ENERGY (변경 없음)
# ──────────────────────────────────────────────────────────────
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
# 2. 계산 함수
# ──────────────────────────────────────────────────────────────
def compute_step_ev():
    return {lvl: [1.0 / p for p in PROBS[lvl]] for lvl in range(1, 11)}

def compute_cumulative_ev(step_ev):
    cum, running = {}, [0.0] * 7
    for lvl in range(1, 11):
        for ti in range(7):
            running[ti] += step_ev[lvl][ti]
        cum[lvl] = running[:]
    return cum

def compute_ceiling_p(lvl, ti):
    if lvl not in ENERGY:
        return 0.0
    pb  = PROBS[lvl][ti]
    epf = ENERGY[lvl]['epf']
    bst = ENERGY[lvl]['boost']
    N   = math.ceil(100.0 / epf)
    p_not = 1.0
    for k in range(N):
        pk = min(1.0, pb + k * bst / 100.0)
        p_not *= (1.0 - pk)
    return p_not

def mc_nodrop(tier_idx, n_sim=3000):
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
                pb   = PROBS[tlvl][tier_idx]
                if tlvl >= 4 and tlvl in ENERGY:
                    ba, ea = pity[tlvl]
                    p_eff = 1.0 if ea >= 100.0 else min(1.0, pb + ba / 100.0)
                else:
                    p_eff = pb
                if rng.random() < p_eff:
                    level += 1
                    if tlvl >= 4:
                        pity[tlvl] = [0.0, 0.0]
                    attempts = 3
                else:
                    if tlvl >= 4 and tlvl in ENERGY:
                        cfg = ENERGY[tlvl]
                        pity[tlvl][0] += cfg['boost']
                        pity[tlvl][1]  = min(100.0, pity[tlvl][1] + cfg['epf'])
                    attempts -= 1
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
# 3. 계산 실행
# ──────────────────────────────────────────────────────────────
print("\n[1/3] 기대값/천장 계산...")
step_ev = compute_step_ev()
cum_ev  = compute_cumulative_ev(step_ev)
ceil_p  = {lvl: [compute_ceiling_p(lvl, ti) for ti in range(7)] for lvl in range(4, 11)}
succ_p  = {lvl: [1.0 - ceil_p[lvl][ti]      for ti in range(7)] for lvl in range(4, 11)}

print("[2/3] MC 노강소모 시뮬레이션 (n=3000 × 7티어)...")
t0 = time.time()
mc_all = {}
for ti in range(7):
    mc_all[ti] = mc_nodrop(ti, n_sim=3000)
    print(f"  {TIER_LABELS[ti]} 완료  +10={mc_all[ti][10]:,}개")
print(f"  MC 완료 ({time.time()-t0:.1f}s)")

# ──────────────────────────────────────────────────────────────
# 4. 확률표 — 셀 컬러 재적용 (수식/값은 건드리지 않음)
# ──────────────────────────────────────────────────────────────
print("\n[3/3] Excel 업데이트...")

def prob_fill(p):
    """확률값에 따른 셀 배경색 반환 (범례 기준)."""
    if p >= 1.0:  return PatternFill('solid', fgColor='4CAF50')  # 녹색  100%
    if p >= 0.70: return PatternFill('solid', fgColor='A5D6A7')  # 연녹  ≥70%
    if p >= 0.40: return PatternFill('solid', fgColor='FFF59D')  # 노랑  40~70%
    if p >= 0.20: return PatternFill('solid', fgColor='FFCC80')  # 주황  20~40%
    if p >= 0.10: return PatternFill('solid', fgColor='EF9A9A')  # 연빨  10~20%
    return          PatternFill('solid', fgColor='C62828')        # 진빨  <10%

for idx, lvl in enumerate(range(1, 11)):
    row = 8 + idx
    for ti in range(7):
        p    = PROBS[lvl][ti]
        cell = ws_prob.cell(row, 3 + ti)
        cell.fill          = prob_fill(p)
        cell.number_format = '0.00%'
print("  확률표 컬러 완료")

# ──────────────────────────────────────────────────────────────
# 기대값 시트
# ──────────────────────────────────────────────────────────────
ws2 = wb['기대값']
ws2.cell(3, 2).value = '기하분포: E(k) = 1/p(k)  |  실패 시 단계 유지  |  T4 = 기준값'
ws2.cell(8, 2).value = '■  단계별 기대 시도수 (해당 레벨→다음 레벨 평균 시도)'
for idx, lvl in enumerate(range(1, 11)):
    row = 9 + idx
    for ti in range(7):
        ws2.cell(row, 3 + ti).value = round(step_ev[lvl][ti], 4)
    ratio = step_ev[lvl][6] / step_ev[lvl][0] if step_ev[lvl][0] > 0 else 1.0
    ws2.cell(row, 10).value = round(ratio, 4)
for idx, lvl in enumerate(range(1, 11)):
    row = 22 + idx
    for ti in range(7):
        ws2.cell(row, 3 + ti).value = round(cum_ev[lvl][ti], 4)
    ratio = cum_ev[lvl][6] / cum_ev[lvl][0] if cum_ev[lvl][0] > 0 else 1.0
    ws2.cell(row, 10).value = round(ratio, 4)
print("  기대값 완료")

# ──────────────────────────────────────────────────────────────
# 델피나드 시트
# ──────────────────────────────────────────────────────────────
ws3 = wb['델피나드']
for idx, lvl in enumerate(range(4, 11)):
    for ti in range(7):
        ws3.cell(26 + idx, 3 + ti).value = round(ceil_p[lvl][ti], 8)
        ws3.cell(35 + idx, 3 + ti).value = round(succ_p[lvl][ti], 8)
print("  델피나드 완료")

# ──────────────────────────────────────────────────────────────
# 노강소모 시트
# ──────────────────────────────────────────────────────────────
ws4 = wb['노강소모']
ws4.cell(2, 2).value = '🔧  노강 아이템 기대 소모량  (Monte Carlo n=3,000 · 천장+복구 포함 · 단계 하락 없음)'
ws4.cell(3, 2).value = '조건: 강화 3회 소진 → 같은 강화단계 아이템 1개 소모 복구  |  성공 시 3회 리셋'
for idx, lvl in enumerate(range(1, 11)):
    row = 7 + idx
    for ti in range(7):
        ws4.cell(row, 3 + ti).value = mc_all[ti][lvl]
    ws4.cell(row, 10).value = nogang_label(mc_all[3][lvl])
t4_10 = mc_all[3][10]
t7_10 = mc_all[6][10]
ws4.cell(23, 3).value = f'기대 소모 ≈ {t4_10:,}개  (천장 시스템으로 소모량 현실화)'
ws4.cell(24, 3).value = f'기대 소모 ≈ {t7_10:,}개  (극한 희소성)'
print("  노강소모 완료")

# ──────────────────────────────────────────────────────────────
# 요약 시트
# ──────────────────────────────────────────────────────────────
ws5 = wb['요약']
difficulty = {4:'보통', 5:'높음', 6:'높음', 7:'매우 높음', 8:'매우 높음', 9:'극한', 10:'극한+'}
for idx, lvl in enumerate(range(4, 11)):
    row = 7 + idx
    for ti in range(7):
        cell = ws5.cell(row, 3 + ti)
        cell.value = PROBS[lvl][ti]
        cell.number_format = '0.00%'
    ws5.cell(row, 10).value = difficulty[lvl]
def safe_write(ws, row, col, val):
    """병합 셀을 건너뛰며 값 쓰기."""
    try:
        ws.cell(row, col).value = val
    except AttributeError:
        pass

for idx, lvl in enumerate(range(4, 11)):
    row = 18 + idx
    for ti in range(7):
        safe_write(ws5, row, 3 + ti, round(cum_ev[lvl][ti], 4))
    ratio = cum_ev[lvl][6] / cum_ev[lvl][0] if cum_ev[lvl][0] > 0 else 1.0
    safe_write(ws5, row, 10, round(ratio, 4))
for idx, lvl in enumerate(range(4, 11)):
    row = 29 + idx
    for ti in range(7):
        safe_write(ws5, row, 3 + ti, mc_all[ti][lvl])
    safe_write(ws5, row, 10, nogang_label(mc_all[3][lvl]))
print("  요약 완료")

wb.save(DST)
print(f"\n✅ 저장 완료: {DST}")

# ──────────────────────────────────────────────────────────────
# 결과 요약
# ──────────────────────────────────────────────────────────────
print("\n====== 노강소모 요약 (T4 / T7) ======")
for lvl in [5, 6, 7, 8, 9, 10]:
    print(f"  +{lvl}: T4={mc_all[3][lvl]:>6,}개  T7={mc_all[6][lvl]:>8,}개")
