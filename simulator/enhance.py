"""X7 강화 시뮬레이터 — 확률 데이터 및 시뮬레이션 엔진 (gen_tier_enhance_v2.py 기반)"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

# ── 강화 데이터 (gen_tier_enhance_v2.py에서 이관) ──────────────────────────
ENHANCES = ['+1', '+2', '+3', '+4', '+5', '+6', '+7', '+8', '+9', '+10']

PROBS: dict[str, list[float]] = {
    #            T1     T2      T3      T4      T5      T6      T7
    '+1' : [1.000, 1.000,  1.000,  1.000,  1.000,  1.000,  1.000],  # 안전 강화
    '+2' : [0.950, 0.900,  0.810,  0.720,  0.630,  0.540,  0.450],
    '+3' : [0.850, 0.750,  0.675,  0.600,  0.525,  0.450,  0.375],
    '+4' : [0.700, 0.500,  0.450,  0.400,  0.350,  0.300,  0.250],
    '+5' : [0.500, 0.300,  0.270,  0.240,  0.210,  0.180,  0.150],  # 주요 관문
    '+6' : [0.300, 0.250,  0.225,  0.200,  0.175,  0.150,  0.125],
    '+7' : [0.200, 0.200,  0.180,  0.160,  0.140,  0.120,  0.100],
    '+8' : [0.150, 0.150,  0.135,  0.120,  0.105,  0.090,  0.075],
    '+9' : [0.100, 0.100,  0.090,  0.080,  0.070,  0.060,  0.050],
    '+10': [0.050, 0.050,  0.045,  0.040,  0.035,  0.030,  0.025],
}

# energy_per_fail: 실패 1회당 기운 충전%  /  boost: 실패 1회당 성공 확률 상승%p
# 천장 횟수 = CEILING(100 / energy_per_fail)
ENERGY: dict[str, dict[str, float]] = {
    '+4' : {'energy_per_fail': 20.0, 'boost': 2.0},   # 천장  5회
    '+5' : {'energy_per_fail': 15.0, 'boost': 1.5},   # 천장  7회
    '+6' : {'energy_per_fail': 10.0, 'boost': 1.0},   # 천장 10회
    '+7' : {'energy_per_fail':  6.0, 'boost': 0.8},   # 천장 17회
    '+8' : {'energy_per_fail':  4.0, 'boost': 0.6},   # 천장 25회
    '+9' : {'energy_per_fail':  3.0, 'boost': 0.4},   # 천장 34회
    '+10': {'energy_per_fail':  2.5, 'boost': 0.4},   # 천장 40회
}

ENH_LIST   = ['+4', '+5', '+6', '+7', '+8', '+9', '+10']
TIER_LABEL = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

# 강화 단계별 복구 1회당 소모 충전석 수 (기획안 — 미정)
SC_LEVEL: dict[int, int] = {
    1:  2,    # +1
    2:  4,    # +2
    3:  8,    # +3
    4:  15,   # +4
    5:  25,   # +5
    6:  40,   # +6
    7:  60,   # +7
    8:  100,  # +8
    9:  150,  # +9
    10: 200,  # +10
}

# 티어×강화단계별 기본 골드 비용 (강화 1회당, 인덱스 0=T1..6=T7)
GOLD_BASE: dict[str, list[int]] = {
    '+4' : [  500,    700,   1000,   1500,   2500,   4000,   6000],
    '+5' : [  800,   1200,   2000,   3000,   5000,   8000,  12000],
    '+6' : [ 1500,   2500,   4000,   6000,  10000,  16000,  25000],
    '+7' : [ 3000,   5000,   8000,  12000,  20000,  32000,  50000],
    '+8' : [ 6000,  10000,  16000,  25000,  40000,  65000, 100000],
    '+9' : [12000,  20000,  32000,  50000,  80000, 130000, 200000],
    '+10': [25000,  40000,  65000, 100000, 160000, 260000, 400000],
}


def default_gold(tier_idx: int, target_level: int) -> int:
    """티어와 목표 강화 단계에 따른 기본 골드 반환."""
    if target_level <= 3:
        return 0
    enh = f'+{target_level}'
    return GOLD_BASE.get(enh, GOLD_BASE['+10'])[tier_idx]


@dataclass
class EnhanceSession:
    tier_idx: int           # 0=T1 ~ 6=T7
    target_level: int       # 목표 강화 레벨 (4~10)
    current_level: int = 0
    # pity[k] = [boost_acc%p, energy_acc%]  (k=4~10, 단계별 독립)
    pity: dict = field(
        default_factory=lambda: {k: [0.0, 0.0] for k in range(4, 11)}
    )
    total_attempts: int = 0
    scrolls_used: int = 0
    gold_spent: int = 0
    ceiling_hits: int = 0
    restore_counter: int = 3   # 남은 강화 횟수 (실패 시 -1, 성공 레벨업 시 3 리셋)
    stones_used: int = 0       # 소모 충전석 누계
    restore_events: list = field(default_factory=list)  # 복구 발동 시점의 레벨 기록
    history: list = field(default_factory=list)
    done: bool = False


def effective_prob(session: EnhanceSession, tlvl: int) -> tuple[float, bool]:
    """유효 확률 계산. (p_eff, ceiling_active) 반환.

    천장 규칙:
      - 기운 100% → 100% 성공 (ceiling_active=True)
      - 그 외 → min(1.0, p_base + boost_acc/100)
    """
    enh = f'+{tlvl}'
    pb  = PROBS[enh][session.tier_idx]
    if tlvl >= 4 and enh in ENERGY:
        boost_acc, energy_acc = session.pity[tlvl]
        if energy_acc >= 100.0:
            return 1.0, True
        return min(1.0, pb + boost_acc / 100.0), False
    return pb, False


def step_once(
    session: EnhanceSession,
    rng: random.Random,
    gold_per_attempt: int,
) -> dict:
    """강화 1회 시도. session 인플레이스 업데이트 후 결과 dict 반환."""
    if session.done:
        return {"done": True, "success": False}

    tlvl = session.current_level + 1
    enh  = f'+{tlvl}'

    prev_level     = session.current_level
    energy_before  = session.pity[tlvl][1] if tlvl >= 4 else 0.0
    boost_before   = session.pity[tlvl][0] if tlvl >= 4 else 0.0

    p_eff, ceiling_active = effective_prob(session, tlvl)
    success = rng.random() < p_eff

    # 소모 처리
    session.total_attempts  += 1
    session.scrolls_used    += 1
    session.gold_spent      += gold_per_attempt

    if success:
        session.current_level += 1
        if tlvl >= 4:
            session.pity[tlvl] = [0.0, 0.0]   # 성공 시 기운 초기화
        if ceiling_active:
            session.ceiling_hits += 1
        session.restore_counter = 3             # 성공(레벨 진급) 시 횟수 리셋
    else:
        if tlvl >= 4 and enh in ENERGY:
            cfg = ENERGY[enh]
            session.pity[tlvl][0] += cfg['boost']
            session.pity[tlvl][1]  = min(
                100.0, session.pity[tlvl][1] + cfg['energy_per_fail']
            )
        session.restore_counter -= 1            # 실패 시에만 차감

    energy_after = session.pity[tlvl][1] if tlvl >= 4 else 0.0

    # ── 완료 체크 (복구 판단 전) ──
    if session.current_level >= session.target_level:
        session.done = True

    # ── 복구 발동 (횟수 소진, 미완료 시에만) ──
    # 횟수=0 → 충전석 SC_LEVEL[tlvl]개 소모해 1회 복구 (메인 아이템 보존)
    restore_triggered = False
    restore_level     = None
    stones_spent_now  = 0
    if session.restore_counter == 0 and not session.done:
        sc = SC_LEVEL[tlvl]
        session.stones_used     += sc
        session.restore_counter  = 1     # 충전석 sc개 → 1회 복구
        restore_triggered        = True
        restore_level            = session.current_level
        stones_spent_now         = sc
        session.restore_events.append(restore_level)

    result = {
        "attempt_no"    : session.total_attempts,
        "success"       : success,
        "ceiling_active": ceiling_active,
        "ceiling_hit"   : ceiling_active and success,
        "p_eff"         : p_eff,
        "p_base"        : PROBS[enh][session.tier_idx],
        "prev_level"    : prev_level,
        "new_level"     : session.current_level,
        "enh_tried"     : enh,
        "energy_before" : energy_before,
        "energy_after"  : energy_after,
        "boost_before"  : boost_before,
        "restore"       : restore_triggered,
        "restore_level" : restore_level,
        "stones_spent"  : stones_spent_now,
        "gold_spent"    : session.gold_spent,
        "done"          : session.done,
    }
    session.history.append(result)
    return result


def run_batch(
    tier_idx: int,
    target_level: int,
    n_sim: int,
    gold_per_attempt: int,
) -> list[dict]:
    """N회 배치 시뮬레이션. [{attempts, scrolls, gold, ceiling_hits}, ...] 반환."""
    rng = random.Random(42 + tier_idx * 137)
    out = []
    for _ in range(n_sim):
        sess  = EnhanceSession(tier_idx=tier_idx, target_level=target_level)
        guard = 0
        while not sess.done and guard < 500_000:
            guard += 1
            step_once(sess, rng, gold_per_attempt)
        out.append({
            "attempts"     : sess.total_attempts,
            "scrolls"      : sess.scrolls_used,
            "gold"         : sess.gold_spent,
            "ceiling_hits" : sess.ceiling_hits,
            "restore_count": len(sess.restore_events),
            "stones_used"  : sess.stones_used,
        })
    return out


def simulate_max_level_without_restore(
    tier_idx: int,
    n_sim: int = 10_000,
) -> dict:
    """내구도 회복(복구) 없이 아이템 1개로 도달 가능한 최대 강화 레벨 분포.

    규칙:
      - 각 레벨마다 최대 3회 시도 (실패 시 차감, 성공 시 3회 리셋)
      - 실패 3회 소진 → 아이템 소모, 시뮬 종료
      - 기운(pity) 시스템 포함

    Returns:
        level_dist  : {레벨: 해당 레벨에서 종료된 횟수}
        reach_prob  : {레벨: P(≥레벨 도달)}
        expected_max: 평균 도달 레벨
        n_sim       : 시뮬 횟수
    """
    rng = random.Random(99 + tier_idx * 73)
    results: list[int] = []

    for _ in range(n_sim):
        level    = 0
        attempts = 3
        pity     = {k: [0.0, 0.0] for k in range(4, 11)}

        while level < 10:
            tlvl = level + 1
            enh  = f'+{tlvl}'
            pb   = PROBS[enh][tier_idx]

            if tlvl >= 4 and enh in ENERGY:
                boost_acc, energy_acc = pity[tlvl]
                p_eff = (
                    1.0 if energy_acc >= 100.0
                    else min(1.0, pb + boost_acc / 100.0)
                )
            else:
                p_eff = pb

            if rng.random() < p_eff:   # 성공
                level += 1
                if tlvl >= 4:
                    pity[tlvl] = [0.0, 0.0]
                attempts = 3           # 레벨 진급 시 리셋
            else:                       # 실패
                if tlvl >= 4 and enh in ENERGY:
                    cfg = ENERGY[enh]
                    pity[tlvl][0] += cfg['boost']
                    pity[tlvl][1]  = min(100.0, pity[tlvl][1] + cfg['energy_per_fail'])
                attempts -= 1
                if attempts == 0:
                    break              # 내구도 소진 → 종료

        results.append(level)

    level_dist  = {}
    for r in results:
        level_dist[r] = level_dist.get(r, 0) + 1

    reach_prob = {
        lvl: sum(1 for r in results if r >= lvl) / n_sim
        for lvl in range(0, 11)
    }

    return {
        'level_dist'  : level_dist,
        'reach_prob'  : reach_prob,
        'expected_max': sum(results) / n_sim,
        'n_sim'       : n_sim,
    }


def compute_ceiling_stats() -> dict:
    """티어×강화단계별 천장 도달 확률 계산.

    P(천장) = ∏[k=0..N-1] (1 - min(1, p_base + k*boost/100))
    N = ceil(100 / energy_per_fail)
    """
    stats: dict[str, dict[int, float]] = {}
    for enh in ENH_LIST:
        cfg  = ENERGY[enh]
        epf  = cfg['energy_per_fail']
        bst  = cfg['boost']
        N    = math.ceil(100.0 / epf)
        stats[enh] = {}
        for ti in range(7):
            pb    = PROBS[enh][ti]
            p_not = 1.0
            for k in range(N):
                pk    = min(1.0, pb + k * bst / 100.0)
                p_not *= (1.0 - pk)
            stats[enh][ti] = p_not
    return stats


def compute_expected_base_items(
    tier_idx: int,
    n_sim: int = 200,
    max_target: int = 10,
) -> dict[int, float]:
    """Monte Carlo: pre[k] = +k 목표 강화 시 소모 기대 충전석 수.

    신규 충전석 모델:
      - 메인 아이템 보존 (파괴 없음)
      - 실패 3회 소진 → SC_LEVEL[tlvl]개 충전석 소모 → 1회 복구
      - pre[0] = 0 (충전석 소모 없음)
    """
    rng = random.Random(42 + tier_idx * 137 + n_sim)
    pre: dict[int, float] = {0: 0.0}

    for target in range(1, max_target + 1):
        total = 0.0
        for _ in range(n_sim):
            level    = 0
            attempts = 3
            stones   = 0.0
            pity     = {k: [0.0, 0.0] for k in range(4, 11)}
            guard    = 0

            while level < target and guard < 300_000:
                guard += 1
                tlvl = level + 1
                enh  = f'+{tlvl}'
                pb   = PROBS[enh][tier_idx]

                if tlvl >= 4 and enh in ENERGY:
                    boost_acc, energy_acc = pity[tlvl]
                    p_eff = (
                        1.0 if energy_acc >= 100.0
                        else min(1.0, pb + boost_acc / 100.0)
                    )
                else:
                    p_eff = pb

                if rng.random() < p_eff:       # 성공
                    level += 1
                    if tlvl >= 4:
                        pity[tlvl] = [0.0, 0.0]
                    attempts = 3               # 성공(레벨 진급) 시 횟수 리셋
                else:                          # 실패 (단계 유지)
                    if tlvl >= 4 and enh in ENERGY:
                        cfg = ENERGY[enh]
                        pity[tlvl][0] += cfg['boost']
                        pity[tlvl][1]  = min(
                            100.0, pity[tlvl][1] + cfg['energy_per_fail']
                        )
                    attempts -= 1              # 실패 시에만 차감

                # 복구: 횟수 소진 → 충전석 SC_LEVEL[tlvl]개 소모 → 1회 복구
                if attempts == 0 and level < target:
                    stones   += SC_LEVEL[tlvl]
                    attempts  = 1

            total += stones
        v = round(total / n_sim, 1)
        pre[target] = v if v < 10 else math.floor(v)

    return pre
