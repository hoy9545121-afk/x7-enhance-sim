"""인벤토리 기반 강화 시뮬레이터
아이템을 plain dict로 관리해 Streamlit session_state 변경 감지 문제 방지
"""
from __future__ import annotations
import random
from typing import Optional

import streamlit as st

from simulator.enhance import PROBS, ENERGY, TIER_LABEL, SC_LEVEL
from simulator.constants import C

# ── 상수 ─────────────────────────────────────────────────────────
TIER_GRADE  = {0:'하급', 1:'하급', 2:'하급', 3:'중급', 4:'중급', 5:'상급', 6:'상급'}
GRADE_COLOR = {'하급': '#4FC3F7', '중급': '#FFD54F', '상급': '#EF9A9A'}
TIER_EMOJI  = ['⚪', '🟢', '🔵', '🟡', '🟠', '🔴', '🟣']


# ── 아이템 dict 헬퍼 ─────────────────────────────────────────────
def _new_item(item_id: int, tier: int) -> dict:
    return {
        'id':      item_id,
        'tier':    tier,
        'level':   0,
        'charges': 3,
        'pity':    {k: [0.0, 0.0] for k in range(4, 11)},
    }

def _grade(item: dict) -> str:
    return TIER_GRADE[item['tier']]

def _tier_label(item: dict) -> str:
    return TIER_LABEL[item['tier']]

def _charges_bar(item: dict) -> str:
    c = item['charges']
    return '■' * c + '□' * (3 - c)


# ── 세션 상태 ─────────────────────────────────────────────────────
def _s() -> dict:
    if 'inv' not in st.session_state:
        st.session_state['inv'] = {
            'gold':      0,
            'scrolls':   0,
            'stones':    {'하급': 0, '중급': 0, '상급': 0},
            'items':     [],
            'selected_id': None,
            'gold_cost': 1000,
            'next_id':   0,
            'log':       [],
            'rng_seed':  0,
        }
    return st.session_state['inv']


def _log(msg: str) -> None:
    s = _s()
    s['log'].insert(0, msg)
    s['log'] = s['log'][:30]


def _get_item(item_id: int) -> Optional[dict]:
    for it in _s()['items']:
        if it['id'] == item_id:
            return it
    return None


def _replace_item(item: dict) -> None:
    """items 리스트에서 같은 id 항목을 교체 (session_state 변경 확실히 반영)."""
    s = _s()
    s['items'] = [item if it['id'] == item['id'] else it for it in s['items']]


# ── 액션 ─────────────────────────────────────────────────────────
def _add_item(tier: int) -> None:
    s    = _s()
    item = _new_item(s['next_id'], tier)
    s['items']   = s['items'] + [item]  # 새 리스트로 교체 → 변경 감지 확실
    s['next_id'] += 1
    _log(f"📦 {TIER_LABEL[tier]} 무기 획득 (노강)")


def _do_enhance(item_id: int) -> None:
    s    = _s()
    item = _get_item(item_id)
    if item is None:
        return

    tlvl = item['level'] + 1
    if tlvl > 10:
        return

    if s['scrolls'] < 1:
        _log('⛔ 주문서 없음');  return
    if s['gold'] < s['gold_cost']:
        _log(f'⛔ 골드 부족 ({s["gold"]:,} / {s["gold_cost"]:,})');  return

    s['scrolls'] -= 1
    s['gold']    -= s['gold_cost']

    # 횟수=0 상태로 강화 시도 → 파괴
    if item['charges'] == 0:
        stones = item['level']
        grade  = _grade(item)
        s['stones'][grade] += stones
        s['items']       = [it for it in s['items'] if it['id'] != item_id]
        s['selected_id'] = None
        _log(f"💥 {_tier_label(item)}+{item['level']} 파괴! → {grade} 충전석 {stones}개 지급")
        return

    # 정상 강화
    enh = f"+{tlvl}"
    pb  = PROBS[enh][item['tier']]
    if tlvl >= 4 and enh in ENERGY:
        b_acc, e_acc = item['pity'][tlvl]
        p_eff   = 1.0 if e_acc >= 100.0 else min(1.0, pb + b_acc / 100.0)
        ceiling = e_acc >= 100.0
    else:
        p_eff, e_acc, ceiling = pb, 0.0, False

    s['rng_seed'] += 1
    rng     = random.Random(s['rng_seed'])
    success = rng.random() < p_eff

    # 변경은 item dict를 직접 수정 후 _replace_item으로 강제 반영
    if success:
        prev          = item['level']
        item['level'] += 1
        if tlvl >= 4:
            item['pity'][tlvl] = [0.0, 0.0]
        suffix = ' ⚡천장!' if ceiling else ''
        _log(f"✅ {_tier_label(item)} +{prev}→+{item['level']} 성공 ({p_eff*100:.0f}%){suffix}")
        if item['level'] == 10:
            _log(f"🏆 {_tier_label(item)} 무기 +10 완성!")
    else:
        if tlvl >= 4 and enh in ENERGY:
            cfg = ENERGY[enh]
            item['pity'][tlvl][0] += cfg['boost']
            item['pity'][tlvl][1]  = min(100.0, item['pity'][tlvl][1] + cfg['energy_per_fail'])
        item['charges'] -= 1            # 실패 시에만 차감
        if item['charges'] == 0:
            _log(f"❌ {_tier_label(item)} +{item['level']} 실패 ({p_eff*100:.0f}%) ⚠️ 강화 횟수 소진!")
        else:
            _log(f"❌ {_tier_label(item)} +{item['level']} 실패 ({p_eff*100:.0f}%) — 남은 횟수 {_charges_bar(item)}")

    _replace_item(item)  # 리스트에 변경된 dict 확실히 반영


def _do_restore(item_id: int) -> None:
    s    = _s()
    item = _get_item(item_id)
    if item is None or item['charges'] > 0:
        return
    tlvl  = min(item['level'] + 1, 10)
    sc    = SC_LEVEL[tlvl]
    grade = _grade(item)
    if s['stones'][grade] < sc:
        _log(f'⛔ {grade} 충전석 부족 ({s["stones"][grade]}/{sc}개)')
        return
    s['stones'][grade] -= sc
    item['charges'] = 1
    _replace_item(item)
    _log(f"🔋 {grade} 충전석 {sc}개 소모 → {_tier_label(item)}+{item['level']} 횟수 1회 복구")


# ── 렌더 ─────────────────────────────────────────────────────────
def render_inventory_sim() -> None:
    s = _s()

    # 사이드바
    with st.sidebar:
        st.divider()
        st.subheader('🎒 획득 / 설정')

        new_gc = st.number_input(
            '강화당 골드', min_value=0, value=s['gold_cost'], step=500, key='inv_gc'
        )
        s['gold_cost'] = new_gc
        st.caption('강화당 주문서: **1개** (고정)')

        st.markdown('**⚔️ 무기 획득**')
        c2 = st.columns(2)
        for ti in range(7):
            if c2[ti % 2].button(f'{TIER_EMOJI[ti]} {TIER_LABEL[ti]}',
                                  key=f'getitem_{ti}', use_container_width=True):
                _add_item(ti);  st.rerun()

        st.markdown('**재료 획득**')
        ca, cb = st.columns(2)
        if ca.button('📜 주문서 +5',  use_container_width=True, key='gs5'):
            s['scrolls'] += 5;  _log('📜 주문서 5개 획득');  st.rerun()
        if cb.button('📜 주문서 +10', use_container_width=True, key='gs10'):
            s['scrolls'] += 10; _log('📜 주문서 10개 획득'); st.rerun()
        if st.button('💰 골드 +10만', use_container_width=True, key='gg'):
            s['gold'] += 100_000; _log('💰 골드 100,000 획득'); st.rerun()

    # 자원 현황
    st.subheader('🎒 인벤토리')
    r = st.columns(5)
    r[0].metric('💰 골드',        f"{s['gold']:,}")
    r[1].metric('📜 주문서',      f"{s['scrolls']}개")
    r[2].metric('🔵 하급 충전석',  f"{s['stones']['하급']}개")
    r[3].metric('🟡 중급 충전석',  f"{s['stones']['중급']}개")
    r[4].metric('🔴 상급 충전석',  f"{s['stones']['상급']}개")

    st.divider()

    # 인벤토리 그리드
    items  = s['items']
    sel_id = s.get('selected_id')

    if not items:
        st.info('👈 사이드바에서 아이템을 획득하세요.')
    else:
        n_cols = min(len(items), 5)
        gcols  = st.columns(n_cols)
        for i, item in enumerate(items):
            with gcols[i % n_cols]:
                is_sel  = (item['id'] == sel_id)
                bdr     = '#e8b84b' if is_sel else '#1e3048'
                chg     = item['charges']
                chg_c   = '#4CAF50' if chg > 1 else ('#FF9800' if chg == 1 else '#F44336')
                grade_c = GRADE_COLOR[_grade(item)]

                st.markdown(f"""
<div style="border:2px solid {bdr};border-radius:10px;padding:12px 6px;
            background:#0d1a28;text-align:center;margin-bottom:4px">
  <div style="font-size:1.5rem;line-height:1.1">{TIER_EMOJI[item['tier']]}</div>
  <div style="color:#9ab8cc;font-size:0.75rem">{_tier_label(item)} 무기</div>
  <div style="color:#e8b84b;font-size:1.7rem;font-weight:bold;line-height:1.2">+{item['level']}</div>
  <div style="color:{grade_c};font-size:0.7rem">{_grade(item)}</div>
  <div style="color:{chg_c};font-size:1rem;letter-spacing:3px">{_charges_bar(item)}</div>
</div>""", unsafe_allow_html=True)

                lbl = '✅ 선택됨' if is_sel else '선택'
                typ = 'primary' if is_sel else 'secondary'
                if st.button(lbl, key=f'sel_{item["id"]}', use_container_width=True, type=typ):
                    s['selected_id'] = None if is_sel else item['id']
                    st.rerun()

    # 강화 패널
    selected = _get_item(sel_id) if sel_id is not None else None
    if selected is None:
        return

    st.divider()
    left, right = st.columns([1, 1])

    with left:
        st.markdown(f"#### ⚡ {_tier_label(selected)} 무기")
        tlvl = selected['level'] + 1

        if tlvl > 10:
            st.success('🏆 최대 강화 +10 완성!')
        else:
            enh = f'+{tlvl}'
            pb  = PROBS[enh][selected['tier']]
            if tlvl >= 4 and enh in ENERGY:
                b_acc, e_acc = selected['pity'][tlvl]
                p_eff   = 1.0 if e_acc >= 100.0 else min(1.0, pb + b_acc / 100.0)
                ceiling = e_acc >= 100.0
            else:
                p_eff, e_acc, ceiling = pb, 0.0, False

            m1, m2, m3 = st.columns(3)
            m1.metric('기본 확률', f'{pb*100:.0f}%')
            delta = f'+{(p_eff-pb)*100:.1f}%p' if p_eff > pb else None
            m2.metric('현재 확률', f'{p_eff*100:.0f}%', delta=delta)
            chg_d = '⚠ 소진!' if selected['charges'] == 0 else None
            m3.metric('남은 횟수', _charges_bar(selected),
                      delta=chg_d,
                      delta_color='inverse' if selected['charges'] == 0 else 'normal')

            if tlvl >= 4 and enh in ENERGY:
                st.markdown(f'**델피나드 기운 {e_acc:.0f}%**')
                st.progress(min(1.0, e_acc / 100.0))
                if ceiling:
                    st.warning('⚡ 천장! 다음 강화 **100%** 보장')

            st.markdown('---')

            sc         = SC_LEVEL[min(tlvl, 10)]
            grade      = _grade(selected)
            has_scroll = s['scrolls'] >= 1
            has_gold   = s['gold'] >= s['gold_cost']
            has_stones = s['stones'][grade] >= sc
            can_enh    = has_scroll and has_gold

            b1, b2 = st.columns(2)

            if selected['charges'] > 0:
                enh_label = '🎲 강화 시도'
                enh_type  = 'primary'
            else:
                enh_label = '💥 강화 시도 (파괴!)'
                enh_type  = 'secondary'

            if b1.button(enh_label, key=f'enh_{selected["id"]}',
                         use_container_width=True, type=enh_type, disabled=not can_enh):
                _do_enhance(selected['id'])
                st.rerun()

            can_restore = (selected['charges'] == 0 and has_stones)
            restore_lbl = f'🔋 충전석 소모\n({grade} {sc}개 → 1회)'
            if b2.button(restore_lbl, key=f'res_{selected["id"]}',
                         use_container_width=True, disabled=not can_restore):
                _do_restore(selected['id'])
                st.rerun()

            if not has_scroll:
                st.caption('⚠ 주문서 없음')
            elif not has_gold:
                st.caption(f'⚠ 골드 부족 ({s["gold"]:,} / {s["gold_cost"]:,})')
            if selected['charges'] == 0 and not has_stones:
                st.caption(f'⚠ {grade} 충전석 부족 ({s["stones"][grade]}/{sc}개)')

            if st.button('🗑️ 버리기', key=f'disc_{selected["id"]}', use_container_width=True):
                _log(f'🗑️ {_tier_label(selected)}+{selected["level"]} 버림')
                s['items']       = [it for it in s['items'] if it['id'] != selected['id']]
                s['selected_id'] = None
                st.rerun()

    with right:
        st.markdown('#### 📋 행동 로그')
        if s['log']:
            html = ''.join(
                f'<div style="font-size:0.85rem;color:#a0c0d8;padding:3px 0;'
                f'border-bottom:1px solid #1a2a3a">{e}</div>'
                for e in s['log'][:15]
            )
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.caption('아직 행동 없음')
