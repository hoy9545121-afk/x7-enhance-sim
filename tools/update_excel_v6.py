"""X7 강화 시스템 Excel 기획서 v6 — 충전석 외부 조달 전략 추가
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
신규 시나리오:
  [A] 구버전   : 실패 3회 → 동일 단계 아이템 소모 (단계 유지)
  [B] 신버전   : 실패 3회 → 아이템 파괴 + 충전석 지급 → 재시작
  [C] 외부조달 : 피더 아이템(동일 티어 +1 강화 후 파괴)으로 충전석 선행 공급
                 메인 아이템 파괴 없이 계속 진행 (진행도 보존)

외부조달 피더 비용 가정:
  동일 티어 아이템 → +1 강화(100% 성공, 1스크롤) → 파괴 → 1 충전석
  피더 1개 = 충전석 1개  (보수적 · 최소비용 기준)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import math, random, time
from openpyxl import Workbook
from openpyxl.styles import (PatternFill, Font, Alignment, Border, Side)
from openpyxl.utils import get_column_letter

DST = r'C:\Users\hoy5343\Downloads\X7_강화시스템_v8_충전석상향.xlsx'

# ── 확률표 ───────────────────────────────────────────────────────
PROBS = {
    #            T1     T2      T3      T4      T5      T6      T7
    1:  [1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
    2:  [0.950, 0.900, 0.810, 0.720, 0.630, 0.540, 0.450],
    3:  [0.850, 0.750, 0.675, 0.600, 0.525, 0.450, 0.375],
    4:  [0.700, 0.500, 0.450, 0.400, 0.350, 0.300, 0.250],
    5:  [0.500, 0.300, 0.270, 0.240, 0.210, 0.180, 0.150],
    6:  [0.300, 0.250, 0.225, 0.200, 0.175, 0.150, 0.125],
    7:  [0.200, 0.200, 0.180, 0.160, 0.140, 0.120, 0.100],
    8:  [0.150, 0.150, 0.135, 0.120, 0.105, 0.090, 0.075],
    9:  [0.100, 0.100, 0.090, 0.080, 0.070, 0.060, 0.050],
    10: [0.050, 0.050, 0.045, 0.040, 0.035, 0.030, 0.025],
}
ENERGY = {
    4:  {'epf': 20.0, 'boost': 2.0},
    5:  {'epf': 15.0, 'boost': 1.5},
    6:  {'epf': 10.0, 'boost': 1.0},
    7:  {'epf':  6.0, 'boost': 0.8},
    8:  {'epf':  4.0, 'boost': 0.6},
    9:  {'epf':  3.0, 'boost': 0.4},
    10: {'epf':  2.5, 'boost': 0.4},
}
SC_LEVEL = {       # 강화 단계별 복구 1회당 소모 충전석 수
    1:  2,         # +1
    2:  4,         # +2
    3:  8,         # +3
    4:  15,        # +4
    5:  25,        # +5
    6:  40,        # +6
    7:  60,        # +7
    8:  100,       # +8
    9:  150,       # +9
    10: 200,       # +10
}
STONE_GRADE = {0:'하급', 1:'하급', 2:'하급',  # 티어별 충전석 종류 (표시용)
               3:'중급', 4:'중급',
               5:'상급', 6:'상급'}
TIER = ['T1','T2','T3','T4','T5','T6','T7']

# ── 스타일 팔레트 ────────────────────────────────────────────────
C_HEADER  = 'FF1F3A5A'
C_SUBHDR  = 'FF2E4E72'
C_OLD     = 'FFFCE4D6'
C_NEW     = 'FFE2EFDA'
C_EXT     = 'FFE8EAF6'   # 외부조달 연보라
C_COMPARE = 'FFDCE6F1'
C_GOLD    = 'FFFFF2CC'
C_WARN    = 'FFFF7043'

def hfont(bold=True, color='FFFFFFFF', size=11):
    return Font(bold=bold, color=color, size=size, name='맑은 고딕')

def dfont(bold=False, color='FF000000', size=10):
    return Font(bold=bold, color=color, size=size, name='맑은 고딕')

def fill(hex6):
    return PatternFill('solid', fgColor=hex6)

def center():
    return Alignment(horizontal='center', vertical='center', wrap_text=True)

def left():
    return Alignment(horizontal='left', vertical='center', wrap_text=True)

thin = Side(style='thin', color='FFB0B0B0')
med  = Side(style='medium', color='FF404040')
def border(t=thin, l=thin, r=thin, b=thin):
    return Border(top=t, left=l, right=r, bottom=b)

def prob_fill(p):
    if p >= 1.0:  return fill('4CAF50')
    if p >= 0.70: return fill('A5D6A7')
    if p >= 0.40: return fill('FFF59D')
    if p >= 0.20: return fill('FFCC80')
    if p >= 0.10: return fill('EF9A9A')
    return              fill('C62828')

def nogang_label(v):
    if v <= 2:    return '✅ 소량 (~2개)'
    if v <= 10:   return '🟡 적음 (~10개)'
    if v <= 50:   return '🟠 보통 (~50개)'
    if v <= 200:  return '🔴 많음 (~200개)'
    if v <= 1000: return '⛔ 수백~천개'
    return               '💀 천개 이상'

def fmt_v(v):
    return f'{v:.1f}' if v < 10 else f'{int(v):,}'

# ════════════════════════════════════════════════════════════════
# 1. MC 시뮬레이션
# ════════════════════════════════════════════════════════════════

def _sim_core(tier_idx, n_sim, seed, attempt_zero_fn):
    """공통 시뮬 루프. attempt_zero_fn(state_dict) 호출로 횟수=0 처리를 외부화."""
    rng = random.Random(seed + tier_idx * 211 + n_sim)
    results = {0: (1.0, 0.0)}  # target -> (items, stones)
    for target in range(1, 11):
        total_items = 0.0; total_stones = 0.0
        for _ in range(n_sim):
            state = {'level': 0, 'attempts': 3,
                     'items': 1, 'stones': 0,
                     'pity': {k: [0.0, 0.0] for k in range(4, 11)}}
            guard = 0
            while state['level'] < target and guard < 300_000:
                guard += 1
                lv  = state['level']
                tlvl = lv + 1
                pb   = PROBS[tlvl][tier_idx]
                if tlvl >= 4 and tlvl in ENERGY:
                    ba, ea = state['pity'][tlvl]
                    p_eff  = 1.0 if ea >= 100.0 else min(1.0, pb + ba/100.0)
                else:
                    p_eff = pb
                if rng.random() < p_eff:
                    state['level'] += 1
                    if tlvl >= 4: state['pity'][tlvl] = [0.0, 0.0]
                    state['attempts'] = 3
                else:
                    if tlvl >= 4 and tlvl in ENERGY:
                        cfg = ENERGY[tlvl]
                        state['pity'][tlvl][0] += cfg['boost']
                        state['pity'][tlvl][1]  = min(100.0, state['pity'][tlvl][1] + cfg['epf'])
                    state['attempts'] -= 1
                    if state['attempts'] == 0 and state['level'] < target:
                        attempt_zero_fn(state, tier_idx, target, results)
            total_items  += state['items']
            total_stones += state['stones']
        ri = total_items  / n_sim
        rs = total_stones / n_sim
        results[target] = (
            round(ri, 1) if ri < 10 else math.floor(ri),
            round(rs, 1) if rs < 10 else math.floor(rs),
        )
    return results


def mc_old(tier_idx, n_sim=3000):
    """구버전: 실패 3회 → 같은 단계 아이템 소모 (단계 유지)."""
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
                    p_eff  = 1.0 if ea >= 100.0 else min(1.0, pb + ba/100.0)
                else:
                    p_eff = pb
                if rng.random() < p_eff:
                    level += 1
                    if tlvl >= 4: pity[tlvl] = [0.0, 0.0]
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
        raw = total / n_sim
        pre[target] = round(raw, 1) if raw < 10 else math.floor(raw)
    return pre


def mc_new(tier_idx, n_sim=3000):
    """신버전: 실패 3회 → 아이템 파괴 + 충전석(단계 수) → 재시작 또는 충전석 복구."""
    rng = random.Random(77 + tier_idx * 211 + n_sim)
    pre = {0: 1.0}
    for target in range(1, 11):
        total = 0.0
        for _ in range(n_sim):
            items_used  = 1
            stone_bank  = 0
            level       = 0
            attempts    = 3
            pity        = {k: [0.0, 0.0] for k in range(4, 11)}
            guard       = 0
            while level < target and guard < 300_000:
                guard += 1
                tlvl = level + 1
                pb   = PROBS[tlvl][tier_idx]
                if tlvl >= 4 and tlvl in ENERGY:
                    ba, ea = pity[tlvl]
                    p_eff  = 1.0 if ea >= 100.0 else min(1.0, pb + ba/100.0)
                else:
                    p_eff = pb
                if rng.random() < p_eff:
                    level += 1
                    if tlvl >= 4: pity[tlvl] = [0.0, 0.0]
                    attempts = 3
                else:
                    if tlvl >= 4 and tlvl in ENERGY:
                        cfg = ENERGY[tlvl]
                        pity[tlvl][0] += cfg['boost']
                        pity[tlvl][1]  = min(100.0, pity[tlvl][1] + cfg['epf'])
                    attempts -= 1
                    if attempts == 0 and level < target:
                        sc_now = SC_LEVEL[level + 1]
                        if stone_bank >= sc_now:
                            stone_bank -= sc_now
                            attempts = 1
                        else:
                            stone_bank += level
                            level      = 0
                            attempts   = 3
                            pity       = {k: [0.0, 0.0] for k in range(4, 11)}
                            items_used += 1
            total += items_used
        raw = total / n_sim
        pre[target] = round(raw, 1) if raw < 10 else math.floor(raw)
    return pre


def mc_external(tier_idx, n_sim=3000):
    """외부 조달 전략:
    - 메인 아이템은 절대 파괴하지 않음
    - 횟수=0 → 외부 충전석 SC_LEVEL[tlvl]개 사용해 1회 복구 (무한 공급 가정)
    - 외부 충전석 1개 = 동일 티어 피더 +1 강화 후 파괴 = 피더 1개
    반환: (items_pre, stones_pre)
      items_pre[target]  = 1(메인) + stones_consumed (피더 수)
      stones_pre[target] = 소모된 충전석 수
    """
    rng = random.Random(55 + tier_idx * 307 + n_sim)
    items_pre  = {0: 1.0}
    stones_pre = {0: 0.0}
    for target in range(1, 11):
        total_items  = 0.0
        total_stones = 0.0
        for _ in range(n_sim):
            stones_used = 0
            level       = 0
            attempts    = 3
            pity        = {k: [0.0, 0.0] for k in range(4, 11)}
            guard       = 0
            while level < target and guard < 300_000:
                guard += 1
                tlvl = level + 1
                pb   = PROBS[tlvl][tier_idx]
                if tlvl >= 4 and tlvl in ENERGY:
                    ba, ea = pity[tlvl]
                    p_eff  = 1.0 if ea >= 100.0 else min(1.0, pb + ba/100.0)
                else:
                    p_eff = pb
                if rng.random() < p_eff:
                    level += 1
                    if tlvl >= 4: pity[tlvl] = [0.0, 0.0]
                    attempts = 3
                else:
                    if tlvl >= 4 and tlvl in ENERGY:
                        cfg = ENERGY[tlvl]
                        pity[tlvl][0] += cfg['boost']
                        pity[tlvl][1]  = min(100.0, pity[tlvl][1] + cfg['epf'])
                    attempts -= 1
                    if attempts == 0 and level < target:
                        # 외부 충전석으로 즉시 복구 — 메인 아이템 파괴 없음
                        stones_used += SC_LEVEL[level + 1]
                        attempts    = 1
            total_items  += 1 + stones_used   # 메인 1 + 피더 stones_used
            total_stones += stones_used
        ri = total_items  / n_sim
        rs = total_stones / n_sim
        items_pre[target]  = round(ri, 1) if ri < 10 else math.floor(ri)
        stones_pre[target] = round(rs, 1) if rs < 10 else math.floor(rs)
    return items_pre, stones_pre


# ════════════════════════════════════════════════════════════════
# 2. 계산 실행
# ════════════════════════════════════════════════════════════════
print("MC 시뮬 시작 (n=3,000) …")
t0 = time.time()

ext_items_all, ext_stones_all = {}, {}

for ti in range(7):
    print(f"  {TIER[ti]} …", end=' ', flush=True)
    ext_items_all[ti], ext_stones_all[ti] = mc_external(ti, n_sim=3000)
    print(f"외부+10={ext_items_all[ti][10]:,}  (충전석={ext_stones_all[ti][10]:,})")

print(f"  완료 ({time.time()-t0:.1f}s)")

# 누적 기대 시도수
step_ev = {lvl: [1.0/PROBS[lvl][ti] for ti in range(7)] for lvl in range(1,11)}
cum_ev  = {}
run = [0.0]*7
for lvl in range(1,11):
    for ti in range(7): run[ti] += step_ev[lvl][ti]
    cum_ev[lvl] = run[:]

# 천장 통계
def ceil_p(lvl, ti):
    if lvl not in ENERGY: return 0.0
    pb, epf, bst = PROBS[lvl][ti], ENERGY[lvl]['epf'], ENERGY[lvl]['boost']
    N = math.ceil(100.0/epf)
    p = 1.0
    for k in range(N):
        p *= 1.0 - min(1.0, pb + k*bst/100.0)
    return p

ceil_all = {lvl: [ceil_p(lvl,ti) for ti in range(7)] for lvl in range(4,11)}
succ_all = {lvl: [1.0-ceil_all[lvl][ti] for ti in range(7)] for lvl in range(4,11)}

# ════════════════════════════════════════════════════════════════
# 3. Excel 작성 헬퍼
# ════════════════════════════════════════════════════════════════
wb = Workbook()
wb.remove(wb.active)

def make_sheet(name):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    return ws

def set_col_widths(ws, widths):
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

def write_header(ws, row, col, text, span=1, bg=C_HEADER, fsize=11):
    cell = ws.cell(row, col, text)
    cell.font      = hfont(size=fsize)
    cell.fill      = fill(bg)
    cell.alignment = center()
    cell.border    = border()
    if span > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row, end_column=col+span-1)

def write_data(ws, row, col, val, bg=None, bold=False, fmt=None, align=None):
    cell = ws.cell(row, col, val)
    cell.font      = dfont(bold=bold)
    cell.alignment = align or center()
    cell.border    = border()
    if bg:   cell.fill = fill(bg)
    if fmt:  cell.number_format = fmt

# ────────────────────────────────────────────────────────────────
# 시트 1: 개요
# ────────────────────────────────────────────────────────────────
ws0 = make_sheet('📋 개요')
set_col_widths(ws0, [2, 22, 14, 14, 14, 14, 14, 14, 14, 20, 2])
ws0.row_dimensions[1].height = 10

ws0.merge_cells('B2:J2')
ws0.cell(2,2,'⚡ X7 강화 시스템 v8 — 분해 충전석 시스템 기획서')
ws0.cell(2,2).font      = Font(bold=True, color='FFFFFFFF', size=15, name='맑은 고딕')
ws0.cell(2,2).fill      = fill(C_HEADER[2:])
ws0.cell(2,2).alignment = center()
ws0.row_dimensions[2].height = 32

# 강화 메커니즘 설명
ws0.cell(4, 2, '■ 강화 메커니즘').font = hfont(size=11, color='FF1F3A5A')
rules = [
    ('기본 강화 가능 횟수', '3회 (무기 제작 시 고정)'),
    ('횟수 차감 조건', '⚠ 강화 실패 시에만 -1 감소 / 성공 시 횟수 유지'),
    ('횟수 0 → 강화 불가', '🔒 강화 시도 불가 — 충전석 소모로 횟수 복구 후 강화 가능'),
    ('충전석 사용 조건', '남은 강화 횟수가 0일 때만 충전 가능 / 1개 소모 → 횟수 1 충전'),
    ('충전 횟수 제한', '제한 없음 (충전석이 있는 한 계속 충전 가능)'),
    ('충전석 획득 방법', '장비 분해 시 획득 — 강화 단계 기준: 1~3강=하급 / 4~5강=중급 / 6강 이상=상급'),
    ('델피나드 기운', '+4 이상 — 실패마다 기운 충전, 100% 시 천장 보장'),
]
for i, (k, v) in enumerate(rules, 5):
    ws0.cell(i, 2, k).font = dfont(bold=True)
    ws0.cell(i, 2).alignment = left()
    ws0.merge_cells(start_row=i, start_column=3, end_row=i, end_column=9)
    ws0.cell(i, 3, v).alignment = left()
    ws0.cell(i, 3).font = dfont()
    if '불가' in k:
        ws0.cell(i, 2).fill = fill('FFF3E0')
        ws0.cell(i, 3).fill = fill('FFF3E0')
    if '획득' in k:
        ws0.cell(i, 2).fill = fill('E8F5E9')
        ws0.cell(i, 3).fill = fill('E8F5E9')

# 구버전 vs 신규 비교 표
ws0.cell(12, 2, '■ 구버전 vs 신규 시스템').font = hfont(size=11, color='FF1F3A5A')
write_header(ws0, 13, 2, '시스템', bg=C_HEADER[2:])
write_header(ws0, 13, 3, '설명', span=4, bg=C_HEADER[2:])
write_header(ws0, 13, 7, '메인 아이템 파괴?', bg=C_HEADER[2:])
write_header(ws0, 13, 8, '충전석 공급원', bg=C_HEADER[2:])
write_header(ws0, 13, 9, '비고', bg=C_HEADER[2:])

scenarios = [
    ('신규 시스템', '실패 시 횟수 -1 / 횟수 0 → 강화 불가\n강화 충전석 소모로 횟수 복구 (횟수 0일 때만 가능)\n충전석은 강화된 장비 분해로 획득', '🔒 강화 불가 (파괴 없음)', '장비 분해', '현행 기획', 'FFE8EAF6'),
]
for ri, (name, desc, dest, src, note, bg) in enumerate(scenarios, 14):
    ws0.row_dimensions[ri].height = 40
    write_data(ws0, ri, 2, name, bold=True, bg=bg[2:])
    ws0.merge_cells(start_row=ri, start_column=3, end_row=ri, end_column=6)
    write_data(ws0, ri, 3, desc, bg=bg[2:], align=left())
    write_data(ws0, ri, 7, dest, bg=bg[2:])
    write_data(ws0, ri, 8, src,  bg=bg[2:])
    write_data(ws0, ri, 9, note, bg=bg[2:])

# 외부조달 전략 설명 박스
ws0.merge_cells('B18:J18')
ws0.cell(18, 2, '■ 신규 시스템 상세').font = hfont(size=11, color='FF1F3A5A')
ext_notes = [
    ('충전석 획득 방법', '강화된 장비를 분해하면 강화 단계에 비례한 충전석 획득 (단계 수=획득량, 미정)'),
    ('분해 충전석 등급', '분해 단계 기준: 1~3강 → 하급 / 4~5강 → 중급 / 6강 이상 → 상급'),
    ('복구 비용 등급', '복구 소모 등급은 티어 기준: T1~3=하급 / T4~5=중급 / T6~7=상급'),
    ('메인 아이템 보존', '횟수 0이 되어도 파괴 없음 → 강화 단계 및 델피나드 기운 진행도 완전 보존'),
    ('밸런스 시사점', '충전석 분해 수급 설계에 따라 강화 비용이 크게 달라짐 — 분해 수량(미정) 확정 필요'),
]
for i, (k, v) in enumerate(ext_notes, 19):
    ws0.row_dimensions[i].height = 22
    ws0.cell(i, 2, k).font = dfont(bold=True); ws0.cell(i, 2).alignment = left()
    ws0.cell(i, 2).fill = fill('E8EAF6')
    ws0.merge_cells(start_row=i, start_column=3, end_row=i, end_column=9)
    ws0.cell(i, 3, v).alignment = left(); ws0.cell(i, 3).font = dfont()
    ws0.cell(i, 3).fill = fill('E8EAF6')

# 충전석 소모 개수 표 — 강화 단계별 (sc 미정, 아래는 기획안)
ws0.cell(25, 2, '■ 강화 단계별 충전석 소모 개수 sc  (※ 소모 개수 미정 — 아래는 기획안)').font = hfont(size=11, color='FF1F3A5A')
for ci, h in enumerate(['강화 단계', 'sc (소모)', '비고'], 2):
    write_header(ws0, 26, ci, h, bg=C_SUBHDR[2:], fsize=10)
sc_rows = [
    ('+1',  '2개',   '안전 강화 (실패 없음)'),
    ('+2',  '4개',   '낮은 실패율 구간'),
    ('+3',  '8개',   ''),
    ('+4',  '15개',  '중간 난이도 / 델피나드 기운 시작'),
    ('+5',  '25개',  ''),
    ('+6',  '40개',  '고난이도 구간'),
    ('+7',  '60개',  ''),
    ('+8',  '100개', '극한 구간'),
    ('+9',  '150개', ''),
    ('+10', '200개', '극한+ 구간'),
]
sc_bgs = ['FFEBF5EB','FFEBF5EB','FFEBF5EB',
          'FFFFF9E6','FFFFF9E6',
          'FFFCE4D6','FFFCE4D6','FFFCE4D6','FFFCE4D6','FFFCE4D6']
for ri, (row_data, bg) in enumerate(zip(sc_rows, sc_bgs), 27):
    for ci, val in enumerate(row_data, 2): write_data(ws0, ri, ci, val, bg=bg[2:])

# 티어별 충전석 종류 안내 (별도)
ws0.cell(35, 2, '■ 티어별 충전석 종류  (티어가 다르면 같은 등급 충전석만 사용 가능)').font = hfont(size=11, color='FF1F3A5A')
for ci, h in enumerate(['티어', '충전석 등급'], 2):
    write_header(ws0, 36, ci, h, bg=C_SUBHDR[2:], fsize=10)
grade_rows = [('T1 ~ T3', '하급 강화 충전석'), ('T4 ~ T5', '중급 강화 충전석'), ('T6 ~ T7', '상급 강화 충전석')]
grade_bgs  = ['FFEBF5EB', 'FFFFF9E6', 'FFFCE4D6']
for ri, (row_data, bg) in enumerate(zip(grade_rows, grade_bgs), 37):
    for ci, val in enumerate(row_data, 2): write_data(ws0, ri, ci, val, bg=bg[2:])

# ────────────────────────────────────────────────────────────────
# 시트 2: 확률표
# ────────────────────────────────────────────────────────────────
ws1 = make_sheet('📊 확률표')
set_col_widths(ws1, [2, 12] + [11]*7 + [18, 2])
ws1.row_dimensions[1].height = 8

ws1.merge_cells('B2:J2')
ws1.cell(2,2,'강화 성공 확률표  (T4 기준값 · 티어 높을수록 확률 감소)')
ws1.cell(2,2).font = hfont(size=12, color='FF1F3A5A'); ws1.cell(2,2).alignment = center()
ws1.row_dimensions[2].height = 28

write_header(ws1, 4, 2, '강화 단계')
for ti, t in enumerate(TIER): write_header(ws1, 4, 3+ti, t)
write_header(ws1, 4, 10, '난이도')

diff_lbl = {1:'✅ 안전',2:'🟢 쉬움',3:'🟢 쉬움',4:'🟡 보통',
            5:'🟠 높음',6:'🟠 높음',7:'🔴 매우 높음',
            8:'🔴 매우 높음',9:'⛔ 극한',10:'💀 극한+'}

for idx, lvl in enumerate(range(1, 11)):
    r = 5 + idx
    ws1.row_dimensions[r].height = 20
    write_data(ws1, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        p = PROBS[lvl][ti]
        cell = ws1.cell(r, 3+ti)
        cell.value=p; cell.number_format='0.00%'
        cell.font=dfont(bold=(lvl<=1)); cell.fill=prob_fill(p)
        cell.alignment=center(); cell.border=border()
    write_data(ws1, r, 10, diff_lbl[lvl])

ws1.row_dimensions[4].height = 22
ws1.cell(17, 2, '색상 범례').font = hfont(size=10, color='FF1F3A5A')
legend = [('100%','4CAF50'),('≥70%','A5D6A7'),('40~70%','FFF59D'),
          ('20~40%','FFCC80'),('10~20%','EF9A9A'),('<10%','C62828')]
for i,(lbl,clr) in enumerate(legend):
    c = ws1.cell(18, 2+i, lbl)
    c.fill=fill(clr); c.font=dfont(size=9); c.alignment=center(); c.border=border()

# ────────────────────────────────────────────────────────────────
# 시트 3: 기대값
# ────────────────────────────────────────────────────────────────
ws2 = make_sheet('📈 기대값')
set_col_widths(ws2, [2, 12] + [11]*7 + [12, 2])
ws2.row_dimensions[1].height = 8

ws2.merge_cells('B2:J2')
ws2.cell(2,2,'강화 단계별 기대 시도수  (E = 1/p, 순수 기하분포)')
ws2.cell(2,2).font = hfont(size=12, color='FF1F3A5A'); ws2.cell(2,2).alignment = center()
ws2.row_dimensions[2].height = 26

write_header(ws2, 4, 2, '■ 단계별 기대 시도수', span=9, bg=C_SUBHDR[2:])
write_header(ws2, 5, 2, '강화 단계')
for ti,t in enumerate(TIER): write_header(ws2, 5, 3+ti, t)
write_header(ws2, 5, 10, 'T7/T1 배율')
for idx, lvl in enumerate(range(1,11)):
    r = 6+idx
    ws2.row_dimensions[r].height = 18
    write_data(ws2, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        write_data(ws2, r, 3+ti, round(step_ev[lvl][ti],2),
                   bg='FFEEF2FF' if lvl>=5 else None)
    ratio = step_ev[lvl][6]/step_ev[lvl][0]
    write_data(ws2, r, 10, f'×{ratio:.1f}')

write_header(ws2, 18, 2, '■ 누적 기대 시도수 (노강→+N)', span=9, bg=C_SUBHDR[2:])
write_header(ws2, 19, 2, '강화 목표')
for ti,t in enumerate(TIER): write_header(ws2, 19, 3+ti, t)
write_header(ws2, 19, 10, 'T7/T1 배율')
for idx, lvl in enumerate(range(1,11)):
    r = 20+idx
    ws2.row_dimensions[r].height = 18
    write_data(ws2, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        write_data(ws2, r, 3+ti, round(cum_ev[lvl][ti],1),
                   bg='FFEEF2FF' if lvl>=5 else None)
    ratio = cum_ev[lvl][6]/cum_ev[lvl][0]
    write_data(ws2, r, 10, f'×{ratio:.1f}')

# ────────────────────────────────────────────────────────────────
# 시트 4: 델피나드
# ────────────────────────────────────────────────────────────────
ws3 = make_sheet('⚡ 델피나드')
set_col_widths(ws3, [2, 14] + [11]*7 + [14, 2])
ws3.row_dimensions[1].height = 8

ws3.merge_cells('B2:J2')
ws3.cell(2,2,'델피나드 에너지 / 천장 시스템  (+4~+10 적용)')
ws3.cell(2,2).font = hfont(size=12, color='FF1F3A5A'); ws3.cell(2,2).alignment = center()
ws3.row_dimensions[2].height = 26

write_header(ws3, 4, 2, '강화 단계')
for h, c in [('기운%/실패', 3), ('확률%p/실패', 4), ('천장(회)', 5)]:
    write_header(ws3, 4, c, h)
write_header(ws3, 4, 6, '천장 도달 시', span=4)
for idx, lvl in enumerate(range(4,11)):
    r = 5+idx
    cfg = ENERGY[lvl]; ceil = math.ceil(100/cfg['epf'])
    ws3.row_dimensions[r].height = 18
    write_data(ws3, r, 2, f'+{lvl}', bold=True)
    write_data(ws3, r, 3, f"{cfg['epf']:.1f}%")
    write_data(ws3, r, 4, f"{cfg['boost']:.1f}%p")
    write_data(ws3, r, 5, f'{ceil}회', bg='FFFFF2CC')
    ws3.merge_cells(start_row=r, start_column=6, end_row=r, end_column=9)
    write_data(ws3, r, 6, '100% 성공 보장', bg='FFE8F5E9', bold=True)

write_header(ws3, 14, 2, '■ 천장 도달 확률', span=9, bg=C_SUBHDR[2:])
write_header(ws3, 15, 2, '강화 단계')
for ti,t in enumerate(TIER): write_header(ws3, 15, 3+ti, t)
write_header(ws3, 15, 10, '비고')
for idx, lvl in enumerate(range(4,11)):
    r = 16+idx
    ws3.row_dimensions[r].height = 18
    write_data(ws3, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        cp = ceil_all[lvl][ti]
        write_data(ws3, r, 3+ti, cp, fmt='0.00%',
                   bg='FFFFE0E0' if cp>0.3 else ('FFFFF2CC' if cp>0.1 else None))
    write_data(ws3, r, 10, f'성공률 T4: {succ_all[lvl][3]*100:.0f}%')

# ────────────────────────────────────────────────────────────────
# 시트 5: 충전석 경제
# ────────────────────────────────────────────────────────────────
ws4 = make_sheet('💎 충전석 경제')
set_col_widths(ws4, [2, 18] + [11]*7 + [16, 2])
ws4.row_dimensions[1].height = 8

ws4.merge_cells('B2:J2')
ws4.cell(2,2,'강화 충전석 경제 분석 — 피더 전략 포함')
ws4.cell(2,2).font = hfont(size=13, color='FF1F3A5A'); ws4.cell(2,2).alignment = center()
ws4.row_dimensions[2].height = 28

# 충전석 설정
write_header(ws4, 4, 2, '■ 충전석 소모 설정', span=8, bg=C_SUBHDR[2:])
write_header(ws4, 5, 2, '티어'); write_header(ws4, 5, 3, '충전석 등급')
write_header(ws4, 5, 4, '복구 1회당'); write_header(ws4, 5, 5, '비고', span=5)
stone_cfg = [
    ('T1~T3', '하급 강화 충전석', '1개',  '낮은 티어 · 접근성 우선',       'FFE8F5E9'),
    ('T4~T5', '중급 강화 충전석', '2개',  '중간 티어 · 밸런스 중시',       'FFFFF9E6'),
    ('T6~T7', '상급 강화 충전석', '10개', '고티어 · 희소성 유지 / 외부조달 억제', 'FFFCE4D6'),
]
for i, (tier, grade, cost, note, bg) in enumerate(stone_cfg, 6):
    ws4.row_dimensions[i].height = 20
    write_data(ws4, i, 2, tier, bold=True, bg=bg[2:])
    write_data(ws4, i, 3, grade, bg=bg[2:]); write_data(ws4, i, 4, cost, bg=bg[2:], bold=True)
    ws4.merge_cells(start_row=i, start_column=5, end_row=i, end_column=9)
    write_data(ws4, i, 5, note, bg=bg[2:], align=left())

# 분해 시 충전석 획득 및 복구 소모 표
write_header(ws4, 11, 2, '■ 강화 단계별 분해 획득 충전석 / 복구 소모 충전석', span=9, bg=C_SUBHDR[2:])
write_header(ws4, 12, 2, '강화 단계')
write_header(ws4, 12, 3, '충전석 등급')
write_header(ws4, 12, 4, '분해 획득량')
write_header(ws4, 12, 5, '복구 소모량')
write_header(ws4, 12, 6, '비고', span=4)
ws4.row_dimensions[12].height = 22

_dis_grade = {
    1:'하급', 2:'하급', 3:'하급',
    4:'중급', 5:'중급',
    6:'상급', 7:'상급', 8:'상급', 9:'상급', 10:'상급',
}
_grade_bg = {'하급': 'FFE3F2FD', '중급': 'FFFFF9C4', '상급': 'FFFCE4D6'}
for idx, lvl in enumerate(range(1, 11)):
    r = 13+idx; ws4.row_dimensions[r].height = 20
    grade = _dis_grade[lvl]
    sc_l  = SC_LEVEL[lvl]
    bg_g  = _grade_bg[grade]
    write_data(ws4, r, 2, f'+{lvl}',       bold=True)
    write_data(ws4, r, 3, grade,            bold=True, bg=bg_g[2:])
    write_data(ws4, r, 4, '미정',           bg='FFFFF2CC')
    write_data(ws4, r, 5, f'{sc_l}개',      bold=True, bg='FFE8EAF6')
    ws4.merge_cells(start_row=r, start_column=6, end_row=r, end_column=9)
    note = ('안전 구간' if lvl <= 3 else
            '델피나드 기운 시작' if lvl == 4 else '')
    write_data(ws4, r, 6, note, bg='FFFFFFFF', align=left())

# 외부조달 충전석 소모량 분석 (핵심 테이블)
write_header(ws4, 26, 2, '■ 외부조달 전략 — 목표별 소모 충전석 수 (MC n=3,000)', span=9, bg='1565C0')
ws4.cell(26, 2).font = hfont(size=11)
write_header(ws4, 27, 2, '강화 목표')
for ti, t in enumerate(TIER): write_header(ws4, 27, 3+ti, t)
write_header(ws4, 27, 10, '피더 아이템 수 (T4)')
ws4.row_dimensions[26].height = 22; ws4.row_dimensions[27].height = 20

for idx, lvl in enumerate(range(1, 11)):
    r = 28+idx; ws4.row_dimensions[r].height = 18
    write_data(ws4, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        s = ext_stones_all[ti][lvl]
        write_data(ws4, r, 3+ti, fmt_v(s), bg='FFE8EAF6')
    # T4 피더 아이템 수 = 충전석 수 (1개당 1개)
    write_data(ws4, r, 10, f'{fmt_v(ext_stones_all[3][lvl])}개')

# ────────────────────────────────────────────────────────────────
# 시트 6: 노강소모 — 3시나리오 비교
# ────────────────────────────────────────────────────────────────
ws5 = make_sheet('🔧 노강소모')
set_col_widths(ws5, [2, 12] + [10]*7 + [18, 2])
ws5.row_dimensions[1].height = 8

ws5.merge_cells('B2:J2')
ws5.cell(2,2,'노강 아이템 기대 소모량 — 구버전 vs 신규 시스템 (MC n=3,000)')
ws5.cell(2,2).font = hfont(size=12, color='FF1F3A5A'); ws5.cell(2,2).alignment = center()
ws5.row_dimensions[2].height = 26


def write_nogang_section(ws, start_row, title, mc_data, bg_row, bg_title_hex, subtitle=None):
    ws.merge_cells(start_row=start_row, start_column=2,
                   end_row=start_row, end_column=10)
    c = ws.cell(start_row, 2, title)
    c.font=hfont(size=11); c.fill=fill(bg_title_hex); c.alignment=center()
    ws.row_dimensions[start_row].height = 26
    hdr_row = start_row+1
    if subtitle:
        ws.merge_cells(start_row=hdr_row, start_column=2, end_row=hdr_row, end_column=10)
        ws.cell(hdr_row, 2, subtitle).font = dfont(size=9)
        ws.cell(hdr_row, 2).alignment = center()
        ws.cell(hdr_row, 2).fill = fill('F3F3F3')
        hdr_row += 1
    write_header(ws, hdr_row, 2, '강화 목표')
    for ti,t in enumerate(TIER): write_header(ws, hdr_row, 3+ti, t)
    write_header(ws, hdr_row, 10, '규모(T4)')
    ws.row_dimensions[hdr_row].height = 20
    for idx, lvl in enumerate(range(1, 11)):
        r = hdr_row+1+idx; ws.row_dimensions[r].height = 18
        write_data(ws, r, 2, f'+{lvl}', bold=True)
        for ti in range(7):
            val = mc_data[ti][lvl]
            bg = bg_row if lvl>=5 else None
            write_data(ws, r, 3+ti, fmt_v(val), bg=bg)
        write_data(ws, r, 10, nogang_label(mc_data[3][lvl]))
    return hdr_row + 11   # 다음 섹션 시작 행 반환


write_nogang_section(ws5, 4,
    '▶ 노강 아이템 기대 소모량  — 충전석 외부조달 전략 (피더 아이템 +1 파괴, 메인 아이템 보존)',
    ext_items_all, 'FFE8EAF6', '1565C0',
    subtitle='* 표시값 = 1(메인) + 소모 충전석 수(피더 수)  |  피더 1개 = 동일티어 아이템 +1 강화→파괴 = 충전석 1개')

# ────────────────────────────────────────────────────────────────
# 시트 7: 요약
# ────────────────────────────────────────────────────────────────
ws6 = make_sheet('📌 요약')
set_col_widths(ws6, [2, 14] + [10]*7 + [20, 2])
ws6.row_dimensions[1].height = 8

ws6.merge_cells('B2:J2')
ws6.cell(2,2,'종합 요약 — X7 강화 시스템')
ws6.cell(2,2).font = hfont(size=13, color='FF1F3A5A'); ws6.cell(2,2).alignment = center()
ws6.row_dimensions[2].height = 28

# 확률 요약
write_header(ws6, 4, 2, '■ 강화 성공 확률 (전 티어)', span=9, bg=C_SUBHDR[2:])
write_header(ws6, 5, 2, '강화')
for ti,t in enumerate(TIER): write_header(ws6, 5, 3+ti, t)
write_header(ws6, 5, 10, '난이도')
for idx, lvl in enumerate(range(1,11)):
    r = 6+idx; ws6.row_dimensions[r].height = 18
    write_data(ws6, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        p = PROBS[lvl][ti]
        c2 = ws6.cell(r, 3+ti)
        c2.value=p; c2.number_format='0%'
        c2.fill=prob_fill(p); c2.font=dfont()
        c2.alignment=center(); c2.border=border()
    write_data(ws6, r, 10, diff_lbl[lvl])

# 핵심 목표별 노강 소모량
KEY_LVLS = [7, 8, 9, 10]

write_header(ws6, 18, 2, '■ 핵심 강화 목표별 노강 아이템 소모량', span=9, bg=C_HEADER[2:])
ws6.row_dimensions[18].height = 22

write_header(ws6, 19, 2, '강화 목표', bg='1565C0', fsize=10)
for ti,t in enumerate(TIER): write_header(ws6, 19, 3+ti, t, bg='1565C0', fsize=9)
write_header(ws6, 19, 10, '규모(T4)', bg='1565C0', fsize=10)
for idx, lvl in enumerate(KEY_LVLS):
    r = 20+idx; ws6.row_dimensions[r].height = 18
    write_data(ws6, r, 2, f'+{lvl}', bold=True)
    for ti in range(7):
        write_data(ws6, r, 3+ti, fmt_v(ext_items_all[ti][lvl]), bg='FFE8EAF6')
    write_data(ws6, r, 10, nogang_label(ext_items_all[3][lvl]))

# 밸런스 시사점 박스
ws6.merge_cells('B26:J26')
ws6.cell(26, 2, '⚠ 밸런스 시사점').font = hfont(size=11, color='FFFF7043')
ws6.cell(26, 2).fill = fill('FFF3E0')
ws6.cell(26, 2).alignment = center()
ws6.row_dimensions[26].height = 24

insights = [
    '핵심 조절 변수: 동일 티어 아이템 제작 비용 (피더 1개 = 충전석 1개 공급원)',
    '피더 재료 비용이 낮으면 고티어도 쉬워짐 → 제작 레시피 설계 시 반드시 고려',
    '충전석 소모 개수(sc)는 강화 단계별 설정 — 현재 기획안 (미정)',
]
for i, txt in enumerate(insights, 27):
    ws6.row_dimensions[i].height = 22
    ws6.merge_cells(start_row=i, start_column=2, end_row=i, end_column=10)
    cell = ws6.cell(i, 2, f'• {txt}')
    cell.font = dfont(size=10); cell.alignment = left()
    cell.fill = fill('FFF3E0')

# ════════════════════════════════════════════════════════════════
# 저장
# ════════════════════════════════════════════════════════════════
wb.save(DST)
print(f"\n✅ 저장 완료: {DST}")

print("\n====== 노강 소모량 요약 ======")
print(f"{'강화':>4}  {'T1':>6} {'T2':>6} {'T3':>6} {'T4':>6} {'T5':>6} {'T6':>6} {'T7':>6}")
for lvl in [7, 8, 9, 10]:
    vals = [fmt_v(ext_items_all[ti][lvl]) for ti in range(7)]
    print(f"+{lvl:2d}  " + "  ".join(f"{v:>6}" for v in vals))
