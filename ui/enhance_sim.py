"""강화 시뮬레이터 Streamlit UI
탭 구성: 📋 확률표 / 🎮 인터랙티브 / 📊 배치 통계 / 🔬 몬테카를로 테이블
"""
from __future__ import annotations
import random
from collections import Counter

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from simulator.enhance import (
    PROBS,
    ENERGY,
    TIER_LABEL,
    EnhanceSession,
    compute_expected_base_items,
    default_gold,
    effective_prob,
    run_batch,
    simulate_max_level_without_restore,
    step_once,
)
from simulator.constants import C
from charts.plotly_charts import _dark_layout
from ui.inventory_sim import render_inventory_sim, TIER_GRADE


# ── 캐시된 노강 소모 테이블 ─────────────────────────────────────
@st.cache_data(show_spinner=False)
def _get_pre_table(tier_idx: int) -> dict[int, float]:
    """티어별 예상 노강 소모 테이블 (최초 1회 계산 후 캐시)."""
    return compute_expected_base_items(tier_idx, n_sim=150)


# ── 세션 관리 ────────────────────────────────────────────────────
def _get_session(tier_idx: int, target: int) -> EnhanceSession:
    sess = st.session_state.get("enh_session")
    if sess is None or sess.tier_idx != tier_idx or sess.target_level != target:
        sess = EnhanceSession(tier_idx=tier_idx, target_level=target)
        st.session_state["enh_session"] = sess
    return sess


# ═══════════════════════════════════════════════════════════════
#  탭 1 — 인터랙티브
# ═══════════════════════════════════════════════════════════════

def _render_interactive(tier_idx: int, target: int, gold_per_attempt: int) -> None:
    session = _get_session(tier_idx, target)

    col_left, col_right = st.columns([1, 2])

    # ── 왼쪽: 상태 + 버튼 ───────────────────────────────────────
    with col_left:
        st.markdown(
            f"<h2 style='color:{C['accent']};margin:0;font-size:3rem'>+{session.current_level}</h2>"
            f"<p style='color:{C['dim']};margin:0 0 8px 0'>{TIER_LABEL[tier_idx]} 아이템</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        if not session.done:
            tlvl = session.current_level + 1
            enh  = f'+{tlvl}'
            p_eff, ceiling_active = effective_prob(session, tlvl)
            pb   = PROBS[enh][tier_idx]

            st.markdown(f"**시도:** `+{session.current_level}` → `+{tlvl}`")

            c1, c2 = st.columns(2)
            c1.metric("기본 확률", f"{pb * 100:.0f}%")
            delta = f"+{(p_eff - pb) * 100:.1f}%p" if p_eff > pb else None
            c2.metric("현재 확률", f"{p_eff * 100:.0f}%", delta=delta)

            # 델피나드 기운 게이지
            if tlvl >= 4 and enh in ENERGY:
                boost_acc, energy_acc = session.pity[tlvl]
                st.markdown(f"**델피나드 기운 — {energy_acc:.1f}%**")
                st.progress(min(1.0, energy_acc / 100.0))
                if boost_acc > 0:
                    st.caption(f"확률 상승 누적: +{boost_acc:.1f}%p")
                if ceiling_active:
                    st.warning("⚡ 천장! 다음 강화 **100%** 보장")

            st.caption(f"이 단계 남은 실패 허용: {session.restore_counter}회 (0회 시 아이템 소모)")

            b1, b2 = st.columns(2)
            do_step  = b1.button("🎲 강화 시도", use_container_width=True, type="primary")
            do_reset = b2.button("🔄 처음부터",  use_container_width=True)

            if do_step:
                step_once(session, random.Random(), gold_per_attempt)
                st.rerun()
            if do_reset:
                st.session_state["enh_session"] = EnhanceSession(
                    tier_idx=tier_idx, target_level=target
                )
                st.rerun()

        else:
            st.success(f"🏆 **+{session.target_level}** 완성!")
            st.markdown(
                f"시도 **{session.total_attempts}회** / 스크롤 **{session.scrolls_used}개** / "
                f"골드 **{session.gold_spent:,}**"
            )
            if st.button("🔄 다시 시작", use_container_width=True, type="primary"):
                st.session_state["enh_session"] = EnhanceSession(
                    tier_idx=tier_idx, target_level=target
                )
                st.rerun()

    # ── 오른쪽: 결과 + 통계 ─────────────────────────────────────
    with col_right:
        # 마지막 결과
        if session.history:
            last = session.history[-1]
            if last["success"]:
                suffix = "  *(천장 발동 100%)*" if last.get("ceiling_hit") else ""
                st.success(f"✅ **성공!** `+{last['prev_level']}` → `+{last['new_level']}`{suffix}")
            else:
                st.error(f"❌ **실패!** `{last['enh_tried']}` 도전 → `+{last['new_level']}` 유지")
                # 실패 직후 기운/확률 상승 즉시 표시
                enh_tried = last["enh_tried"]
                e_before  = last["energy_before"]
                e_after   = last["energy_after"]
                b_before  = last.get("boost_before", 0.0)
                b_delta   = ENERGY.get(enh_tried, {}).get("boost", 0.0)
                b_after   = b_before + b_delta
                st.markdown(
                    f"**{enh_tried} 델피나드 기운: {e_before:.0f}% → {e_after:.0f}%**"
                    f"<span style='color:#e8b84b;font-size:0.9rem'>  (+{e_after - e_before:.0f}%p 충전)</span>",
                    unsafe_allow_html=True,
                )
                st.progress(min(1.0, e_after / 100.0))
                st.caption(f"{enh_tried} 확률 상승 누적: +{b_after:.1f}%p  (이번 +{b_delta:.1f}%p)")

        # 누적 통계
        st.markdown("#### 누적 통계")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("시도",   f"{session.total_attempts}회")
        m2.metric("스크롤", f"{session.scrolls_used}개")
        m3.metric("골드",   f"{session.gold_spent:,}")
        m4.metric("천장",   f"{session.ceiling_hits}회")

        # ── 복구 소모 아이템 & 예상 노강 소모 ──────────────────
        if session.restore_events:
            st.markdown("#### 복구 소모 아이템")
            counts  = Counter(session.restore_events)
            pre_tbl = _get_pre_table(tier_idx)          # 캐시에서 가져옴

            rows      = []
            est_total = 0.0
            for lvl in sorted(counts.keys()):
                cnt     = counts[lvl]
                est_one = pre_tbl.get(lvl, 1.0)
                est_sub = est_one * cnt
                est_total += est_sub
                rows.append({
                    "소모 아이템": f"+{lvl} 아이템",
                    "수량":        cnt,
                    "개당 노강 기댓값": f"≈{est_one:,.1f}개",
                    "소계 노강":  f"≈{est_sub:,.0f}개",
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            total_scrolls = session.scrolls_used
            est_grand = pre_tbl.get(target, est_total) if session.done else (
                pre_tbl.get(session.current_level, 1.0) + est_total
            )
            # 실제 소모된 것: 직접 강화에 쓴 주문서 + 복구 아이템들에 쓰인 노강
            t1, t2 = st.columns(2)
            t1.metric("복구 소모 총 아이템 수", f"{sum(counts.values())}개")
            t2.metric("예상 노강 소모 (복구분)", f"≈{est_total:,.0f}개")

        # 최근 기록
        if session.history:
            st.markdown("#### 최근 시도 기록 (최근 10건)")
            recent = session.history[-10:][::-1]
            rows = []
            for r in recent:
                txt = "✅ 성공" if r["success"] else "❌ 실패"
                if r.get("ceiling_hit"):
                    txt += " (천장)"
                if r.get("restore"):
                    txt += f" [복구+{r['restore_level']}]"
                강화_txt = (
                    f"+{r['prev_level']}→+{r['new_level']}"
                    if r["success"]
                    else f"{r['enh_tried']} 실패(유지)"
                )
                rows.append({
                    "#"    : r["attempt_no"],
                    "강화" : 강화_txt,
                    "결과" : txt,
                    "확률" : f"{r['p_eff'] * 100:.0f}%",
                    "기운" : f"{r['energy_before']:.0f}%→{r['energy_after']:.0f}%",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
#  탭 2 — 배치 통계
# ═══════════════════════════════════════════════════════════════

def _render_batch(tier_idx: int, target: int, gold_per_attempt: int) -> None:
    c1, c2 = st.columns([3, 1])
    with c1:
        n_sim = st.number_input(
            "시뮬레이션 횟수", min_value=100, max_value=10000, value=1000, step=100
        )
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_clicked = st.button("▶ 실행", use_container_width=True, type="primary")

    if run_clicked:
        with st.spinner(f"{n_sim:,}회 시뮬레이션 실행 중..."):
            results = run_batch(tier_idx, target, int(n_sim), gold_per_attempt)

            tier_rows = []
            for ti in range(7):
                g  = default_gold(ti, target)
                tr = run_batch(ti, target, 200, g)
                att = [r["attempts"]      for r in tr]
                gld = [r["gold"]          for r in tr]
                rst = [r["restore_count"] for r in tr]
                tier_rows.append({
                    "티어"      : TIER_LABEL[ti],
                    "평균 시도"  : f"{np.mean(att):,.0f}",
                    "중앙값"    : f"{int(np.median(att)):,}",
                    "P90"       : f"{int(np.percentile(att, 90)):,}",
                    "평균 복구" : f"{np.mean(rst):.1f}회",
                    "평균 골드" : f"{np.mean(gld):,.0f}",
                })

            st.session_state["batch_data"] = {
                "results"  : results,
                "tier_rows": tier_rows,
                "key"      : (tier_idx, target, gold_per_attempt, int(n_sim)),
            }

    data = st.session_state.get("batch_data")
    if data is None:
        st.info("설정 후 [▶ 실행] 버튼을 눌러 시뮬레이션을 시작하세요.")
        return

    if data["key"] != (tier_idx, target, gold_per_attempt, int(n_sim)):
        st.warning("⚠ 설정이 변경되었습니다. [▶ 실행]으로 다시 시뮬레이션하세요.")

    results   = data["results"]
    tier_rows = data["tier_rows"]

    attempts   = [r["attempts"]      for r in results]
    golds      = [r["gold"]          for r in results]
    ceil_hits  = [r["ceiling_hits"]  for r in results]
    rest_cnts  = [r["restore_count"] for r in results]

    avg_att   = np.mean(attempts)
    med_att   = np.median(attempts)
    ceil_pct  = sum(1 for c in ceil_hits if c > 0) / len(ceil_hits) * 100
    avg_gold  = np.mean(golds)
    avg_rest  = np.mean(rest_cnts)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("평균 시도",   f"{avg_att:,.0f}회")
    m2.metric("중앙값",      f"{med_att:,.0f}회")
    m3.metric("천장 도달%",  f"{ceil_pct:.1f}%")
    m4.metric("평균 복구",   f"{avg_rest:.1f}회")
    m5.metric("평균 골드",   f"{avg_gold:,.0f}")

    # 히스토그램
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=attempts, nbinsx=50,
        marker_color=C["accent"], opacity=0.8,
        name="시도 횟수",
    ))
    fig.update_layout(
        **_dark_layout(
            title=f"{TIER_LABEL[tier_idx]} +{target} 목표 — 시도 횟수 분포 (n={len(attempts):,})"
        ),
        xaxis=dict(title="시도 횟수", gridcolor=C["border"]),
        yaxis=dict(title="빈도",      gridcolor=C["border"]),
        bargap=0.05,
    )
    st.plotly_chart(fig, use_container_width=True)

    # 분위수 테이블 + 티어별 비교
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### 분위수 분포")
        pcts     = [10, 25, 50, 75, 90, 99]
        att_pcts = [int(np.percentile(attempts, p)) for p in pcts]
        gld_pcts = [int(np.percentile(golds,    p)) for p in pcts]
        rst_pcts = [int(np.percentile(rest_cnts, p)) for p in pcts]
        df_pct = pd.DataFrame({
            "분위수"   : [f"P{p}" for p in pcts],
            "시도 횟수" : [f"{v:,}" for v in att_pcts],
            "복구 횟수" : [f"{v:,}" for v in rst_pcts],
            "골드"     : [f"{g:,}" for g in gld_pcts],
        })
        st.dataframe(df_pct, use_container_width=True, hide_index=True)

    with col_b:
        st.markdown(f"#### 티어별 비교 (목표: +{target})")
        df_tier = pd.DataFrame(tier_rows)
        st.dataframe(df_tier, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
#  탭 3 — 몬테카를로 테이블 (노강 소모 기댓값)
# ═══════════════════════════════════════════════════════════════

def _render_montecarlo(tier_idx: int = 3) -> None:
    st.markdown(
        "충전석 복구 메커니즘(3회 소진 → SC_LEVEL개 충전석 소모 → 1회 복구)을 포함한 "
        "**목표 강화 단계별 누적 충전석 소모 기댓값**을 Monte Carlo 시뮬레이션으로 계산합니다."
    )

    c1, c2 = st.columns([3, 1])
    with c1:
        n_sim = st.slider(
            "시뮬레이션 횟수 (높을수록 정확, 느림)",
            min_value=50, max_value=1000, value=200, step=50
        )
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_mc = st.button("🔬 실행", use_container_width=True, type="primary")

    if run_mc:
        prog = st.progress(0, text="계산 중...")
        all_pre: dict[int, dict[int, float]] = {}
        for ti in range(7):
            prog.progress((ti + 1) / 7, text=f"{TIER_LABEL[ti]} 계산 중...")
            all_pre[ti] = compute_expected_base_items(ti, n_sim=n_sim)
        prog.empty()
        st.session_state["mc_all_pre"] = all_pre
        st.session_state["mc_n_sim"]   = n_sim

    if "mc_all_pre" not in st.session_state:
        st.info("[🔬 실행] 버튼을 눌러 시뮬레이션을 시작하세요.")
        return

    all_pre = st.session_state["mc_all_pre"]
    n_used  = st.session_state.get("mc_n_sim", "?")
    targets = list(range(2, 11))

    st.markdown(f"**목표 강화 단계별 누적 충전석 소모 기댓값** (n={n_used}, +1은 100% 성공)")

    def _fmt(v: float) -> str:
        return f"{v:.1f}" if v < 10 else f"{int(v):,}"

    # ── 티어별 전체 테이블 ───────────────────────────────────────
    rows = []
    for t in targets:
        row: dict = {"강화 목표": f"+{t}"}
        for ti in range(7):
            val = all_pre[ti].get(t, 0.0)
            row[TIER_LABEL[ti]] = val
        rows.append(row)

    df_raw = pd.DataFrame(rows).set_index("강화 목표")
    df_disp = df_raw.copy()
    for col in df_disp.columns:
        df_disp[col] = df_disp[col].map(_fmt)
    st.dataframe(df_disp, use_container_width=True)

    # ── 히트맵 ──────────────────────────────────────────────────
    import math
    z_vals   = [[all_pre[ti].get(t, 0.0) for ti in range(7)] for t in targets]
    z_log    = [[math.log10(max(v, 1.0)) for v in row] for row in z_vals]
    txt_vals = [[_fmt(all_pre[ti].get(t, 0.0)) for ti in range(7)] for t in targets]

    fig = go.Figure(data=go.Heatmap(
        z=z_log,
        x=TIER_LABEL,
        y=[f"+{t}" for t in targets],
        colorscale=[[0, C["green"]], [0.5, C["accent"]], [1, C["danger"]]],
        text=txt_vals,
        texttemplate="%{text}",
        textfont=dict(size=11),
        showscale=False,
    ))
    fig.update_layout(
        **_dark_layout(title=f"예상 노강 소모 기댓값 (n={n_used} per tier)"),
        xaxis=dict(title="티어"),
        yaxis=dict(title="강화 목표", autorange="reversed"),
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "💡 값 = +0 노강 아이템 기준. 복구 시 소모된 아이템의 노강 비용이 재귀적으로 포함됩니다. "
        f"(n={n_used}회 시뮬, 변동 있음)"
    )

    # ── 장비 N개 오링 강화 후 분해 충전석 시뮬 ──────────────────
    st.divider()
    st.markdown("### 🔨 장비 N개 오링 강화 후 분해 — 충전석 수급 시뮬")
    st.markdown(
        "복구 **없이** 장비를 충전 횟수 0까지 강화한 뒤 전부 분해했을 때 "
        "획득하는 충전석 총량을 시뮬레이션합니다."
    )

    # 충전석 등급은 티어 기준 (TIER_GRADE[bd_tier])
    bd_c1, bd_c2, bd_c3 = st.columns([2, 2, 1])
    with bd_c1:
        bd_tier = st.selectbox(
            "티어", list(range(7)),
            format_func=lambda i: TIER_LABEL[i],
            index=tier_idx, key="bd_tier",
        )
    with bd_c2:
        bd_items = st.number_input(
            "장비 수량", min_value=10, max_value=10000,
            value=100, step=10, key="bd_items",
        )
    with bd_c3:
        bd_nsim = st.number_input(
            "시뮬 횟수", min_value=100, max_value=5000,
            value=500, step=100, key="bd_nsim",
        )

    run_bd = st.button("🔨 분해 시뮬 실행", key="bd_run",
                        use_container_width=False, type="primary")

    if run_bd:
        with st.spinner(f"{bd_items}개 × {bd_nsim}회 시뮬레이션 중..."):
            import math as _math
            from collections import Counter as _Counter

            sim_results = []
            rng_bd = random.Random(99 + bd_tier * 31)

            for _ in range(int(bd_nsim)):
                stones = {'하급': 0, '중급': 0, '상급': 0}
                lv_dist = _Counter()

                for _ in range(int(bd_items)):
                    level   = 0
                    charges = 3
                    pity    = {k: [0.0, 0.0] for k in range(4, 11)}

                    while charges > 0 and level < 10:
                        tlvl = level + 1
                        enh  = f'+{tlvl}'
                        pb   = PROBS[enh][bd_tier]
                        if tlvl >= 4 and enh in ENERGY:
                            b_acc, e_acc = pity[tlvl]
                            p_eff = 1.0 if e_acc >= 100.0 else min(1.0, pb + b_acc / 100.0)
                        else:
                            p_eff = pb

                        if rng_bd.random() < p_eff:
                            level += 1
                            if tlvl >= 4:
                                pity[tlvl] = [0.0, 0.0]
                        else:
                            if tlvl >= 4 and enh in ENERGY:
                                cfg = ENERGY[enh]
                                pity[tlvl][0] += cfg['boost']
                                pity[tlvl][1]  = min(100.0, pity[tlvl][1] + cfg['energy_per_fail'])
                            charges -= 1

                    grade = TIER_GRADE[bd_tier] if level > 0 else None
                    if grade:
                        stones[grade] += level   # 수량=단계 수 (미정 기획안)
                    lv_dist[level] += 1

                sim_results.append({'stones': stones, 'lv_dist': dict(lv_dist)})

            st.session_state["bd_results"] = {
                "data": sim_results,
                "tier": bd_tier, "items": int(bd_items), "nsim": int(bd_nsim),
            }

    bd_data = st.session_state.get("bd_results")
    if bd_data is None:
        st.info("[🔨 분해 시뮬 실행] 버튼을 눌러 시뮬레이션을 시작하세요.")
    else:
        bd_res   = bd_data["data"]
        bd_n     = bd_data["nsim"]
        bd_ni    = bd_data["items"]
        bd_t     = bd_data["tier"]

        # 충전석 평균
        avg = {g: np.mean([r['stones'][g] for r in bd_res]) for g in ['하급','중급','상급']}
        std = {g: np.std( [r['stones'][g] for r in bd_res]) for g in ['하급','중급','상급']}

        st.markdown(f"#### 결과 — {TIER_LABEL[bd_t]} {bd_ni}개 오링 후 분해 (n={bd_n}회)")
        m1, m2, m3 = st.columns(3)
        m1.metric("🔵 하급 충전석", f"{avg['하급']:.0f}개",
                  delta=f"±{std['하급']:.0f}", delta_color="off")
        m2.metric("🟡 중급 충전석", f"{avg['중급']:.0f}개",
                  delta=f"±{std['중급']:.0f}", delta_color="off")
        m3.metric("🔴 상급 충전석", f"{avg['상급']:.0f}개",
                  delta=f"±{std['상급']:.0f}", delta_color="off")

        # 강화 레벨 분포 (누적 평균)
        all_lv_totals = _Counter()
        for r in bd_res:
            for lv, cnt in r['lv_dist'].items():
                all_lv_totals[lv] += cnt
        avg_lv = {lv: cnt / bd_n for lv, cnt in sorted(all_lv_totals.items())}

        lvls   = list(range(0, 11))
        counts = [avg_lv.get(l, 0) for l in lvls]
        tier_grade = TIER_GRADE[bd_t]
        grade_color = {'하급': '#4FC3F7', '중급': '#FFD54F', '상급': '#EF9A9A'}
        bar_color   = grade_color.get(tier_grade, '#EF9A9A')
        colors = [bar_color if l > 0 else '#546E7A' for l in lvls]

        fig_bd = go.Figure()
        fig_bd.add_trace(go.Bar(
            x=[f"+{l}" for l in lvls],
            y=counts,
            marker_color=colors,
            text=[f"{c:.1f}" for c in counts],
            textposition="outside",
        ))
        fig_bd.update_layout(
            **_dark_layout(
                title=f"{TIER_LABEL[bd_t]} {bd_ni}개 — 강화 최종 레벨 분포 (평균, n={bd_n})"
            ),
            xaxis_title="최종 강화 레벨",
            yaxis=dict(title=f"평균 아이템 수 (/{bd_ni}개)", gridcolor=C["border"]),
            bargap=0.15,
        )
        st.plotly_chart(fig_bd, use_container_width=True)

        # 레벨별 상세 표
        detail_bd = []
        for l in lvls:
            avg_cnt = avg_lv.get(l, 0)
            grade   = TIER_GRADE[bd_t] if l > 0 else '-'
            qty     = l if l > 0 else 0
            detail_bd.append({
                "최종 레벨":     f"+{l}",
                "평균 아이템 수": f"{avg_cnt:.1f}개",
                "비율":          f"{avg_cnt / bd_ni * 100:.1f}%",
                "분해 충전석 등급": grade,
                "개당 획득":     f"{qty}개 (미정)" if qty > 0 else '-',
                "소계 (평균)":   f"{avg_cnt * qty:.1f}개" if qty > 0 else '-',
            })
        st.dataframe(pd.DataFrame(detail_bd).set_index("최종 레벨"),
                     use_container_width=True)

        st.caption("💡 충전석 획득 수량은 '강화 단계 수 = 획득량'으로 임시 적용 (기획 미정).")

    # ── 선택 티어 누적 충전석 상세 ───────────────────────────────
    if "mc_all_pre" in st.session_state:
        from simulator.enhance import SC_LEVEL
        st.divider()

        det_c1, det_c2 = st.columns([2, 5])
        with det_c1:
            det_tier = st.selectbox(
                "티어 선택", list(range(7)),
                format_func=lambda i: TIER_LABEL[i],
                index=tier_idx, key="det_tier",
            )
        st.markdown(f"#### 📦 누적 충전석 소모 — {TIER_LABEL[det_tier]} 상세")
        st.caption("각 강화 단계까지 도달하는 과정에서 복구에 소모된 충전석 누적 기댓값")

        detail_rows = []
        for t in range(1, 11):
            stones_cum  = all_pre[det_tier].get(t, 0.0)
            stones_step = max(0.0, stones_cum - all_pre[det_tier].get(t - 1, 0.0))
            sc_cost     = SC_LEVEL[t]
            detail_rows.append({
                "강화 단계":        f"+{t}",
                "복구 1회당 소모":   f"{sc_cost}개",
                "이 단계 추가 소모": _fmt(stones_step),
                "누적 소모 충전석":  _fmt(stones_cum),
            })

        df_detail = pd.DataFrame(detail_rows).set_index("강화 단계")
        st.dataframe(df_detail, use_container_width=True, height=len(detail_rows) * 38 + 42)

    # ── 내구도 회복 없이 몇 강까지? ─────────────────────────────
    st.divider()
    st.markdown("### 🛡️ 내구도 회복 없이 몇 강까지?")
    st.markdown(
        "복구(아이템 소모) **없이** 1개 아이템만으로 도달 가능한 최대 강화 레벨 분포. "
        "각 레벨에서 실패 **3회** 소진 시 아이템 소멸."
    )

    nd_c1, nd_c2, nd_c3 = st.columns([2, 2, 1])
    with nd_c1:
        nd_tier = st.selectbox(
            "티어", list(range(7)),
            format_func=lambda i: TIER_LABEL[i],
            index=3, key="nodur_tier",
        )
    with nd_c2:
        nd_nsim = st.number_input(
            "시뮬 횟수", min_value=1000, max_value=100_000,
            value=10_000, step=1000, key="nodur_nsim",
        )
    with nd_c3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_nodur = st.button("▶ 실행", key="nodur_run", use_container_width=True, type="primary")

    if run_nodur:
        with st.spinner("시뮬레이션 중..."):
            nd_result = simulate_max_level_without_restore(nd_tier, n_sim=int(nd_nsim))
            st.session_state["nodur_result"] = nd_result

    nd_data = st.session_state.get("nodur_result")
    if nd_data is None:
        st.info("[▶ 실행] 버튼을 눌러 시뮬레이션을 시작하세요.")
    else:
        rp   = nd_data["reach_prob"]
        n    = nd_data["n_sim"]
        exp  = nd_data["expected_max"]
        dist = nd_data["level_dist"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("평균 도달 레벨",  f"+{exp:.2f}")
        m2.metric("+5 도달 확률",   f"{rp.get(5,0)*100:.1f}%")
        m3.metric("+7 도달 확률",   f"{rp.get(7,0)*100:.1f}%")
        m4.metric("+10 도달 확률",  f"{rp.get(10,0)*100:.2f}%")

        # 도달 확률 바 차트
        lvls  = list(range(1, 11))
        probs = [rp.get(l, 0) * 100 for l in lvls]
        colors = [
            C["green"]  if p >= 50 else
            C["accent"] if p >= 10 else
            C["danger"]
            for p in probs
        ]
        fig_nd = go.Figure()
        fig_nd.add_trace(go.Bar(
            x=[f"+{l}" for l in lvls],
            y=probs,
            marker_color=colors,
            text=[f"{p:.1f}%" for p in probs],
            textposition="outside",
        ))
        fig_nd.update_layout(
            **_dark_layout(
                title=f"{TIER_LABEL[nd_tier]} "
                      f"— 내구도 소진 전 도달 확률 (n={n:,})"
            ),
            xaxis_title="강화 레벨",
            yaxis=dict(title="도달 확률 (%)", range=[0, 115], gridcolor=C["border"]),
            bargap=0.2,
        )
        st.plotly_chart(fig_nd, use_container_width=True)

        # 분포 테이블
        rows_nd = []
        for l in range(1, 11):
            stop_cnt = dist.get(l, 0)
            rows_nd.append({
                "강화 레벨"     : f"+{l}",
                "이 레벨 도달"  : f"{rp.get(l,0)*100:.1f}%",
                "이 레벨에서 종료": f"{stop_cnt:,}회 ({stop_cnt/n*100:.1f}%)",
            })
        st.dataframe(pd.DataFrame(rows_nd), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
#  탭 0 — 확률표
# ═══════════════════════════════════════════════════════════════

def _render_prob_table() -> None:
    import math

    st.subheader("강화 성공 확률표")
    st.caption("단계별·티어별 기본 성공 확률. 델피나드 기운 부스트 미적용 순수 기본값.")

    # ── 확률 테이블 ─────────────────────────────────────────────
    levels = ["+1", "+2", "+3", "+4", "+5", "+6", "+7", "+8", "+9", "+10"]
    rows = []
    for enh in levels:
        row = {}
        for ti, label in enumerate(TIER_LABEL):
            p = PROBS[enh][ti]
            row[label] = f"{p*100:.2f}%"
        rows.append(row)

    df_prob = pd.DataFrame(rows, index=levels)
    df_prob.index.name = "강화 단계"

    # 숫자 DataFrame (히트맵용)
    df_num = pd.DataFrame(
        [[PROBS[enh][ti] for ti in range(7)] for enh in levels],
        index=levels, columns=TIER_LABEL,
    )

    # Plotly 히트맵
    fig = go.Figure(go.Heatmap(
        z=df_num.values * 100,
        x=TIER_LABEL,
        y=levels,
        colorscale=[
            [0.0,  "#e84b4b"],
            [0.15, "#e8a04b"],
            [0.40, "#e8e84b"],
            [0.70, "#4be8a0"],
            [1.0,  "#4be84b"],
        ],
        zmin=0, zmax=100,
        text=[[f"{PROBS[enh][ti]*100:.2f}%" for ti in range(7)] for enh in levels],
        texttemplate="%{text}",
        textfont={"size": 13},
        showscale=True,
        colorbar=dict(title="확률 %", ticksuffix="%"),
    ))
    fig.update_layout(
        **_dark_layout(title="티어×강화 단계별 성공 확률 (%)"),
        xaxis=dict(title="티어"),
        yaxis=dict(title="강화 단계", autorange="reversed"),
        height=520,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 에너지/천장 테이블 ───────────────────────────────────────
    st.subheader("델피나드 에너지 / 천장 시스템")
    st.caption("실패 누적 시 기운 충전 → 100% 도달 시 다음 강화 100% 보장(천장). 부스트는 기운과 별도로 확률 상승.")

    enh_levels = ["+4", "+5", "+6", "+7", "+8", "+9", "+10"]
    e_rows = []
    for enh in enh_levels:
        cfg = ENERGY[enh]
        ceil_n = math.ceil(100 / cfg["energy_per_fail"])
        e_rows.append({
            "강화 단계": enh,
            "기운 충전(%/실패)": f"{cfg['energy_per_fail']:.1f}%",
            "확률 부스트(%p/실패)": f"{cfg['boost']:.1f}%p",
            "천장 횟수(회)": f"{ceil_n}회",
            "천장 도달 시": "100% 성공 보장",
        })
    df_energy = pd.DataFrame(e_rows).set_index("강화 단계")

    st.dataframe(
        df_energy,
        use_container_width=True,
        height=len(enh_levels) * 38 + 42,
    )

    # ── 노강 소모 기대값 요약 ────────────────────────────────────
    st.subheader("노강 기대 소모량 (참고값)")
    st.caption("MC 시뮬(n≈200) 기준. 복구 포함 — 실패 3회 소진 시 동일 강화 단계 아이템 1개 소모.")

    summary_rows = []
    for enh in ["+7", "+8", "+9", "+10"]:
        lvl = int(enh[1:])
        row = {"강화 목표": enh}
        for ti in range(7):
            pre = _get_pre_table(ti)
            row[TIER_LABEL[ti]] = f"~{pre.get(lvl, 0):,}개"
        summary_rows.append(row)

    df_sum = pd.DataFrame(summary_rows).set_index("강화 목표")
    st.dataframe(df_sum, use_container_width=True, height=len(summary_rows) * 38 + 42)


# ═══════════════════════════════════════════════════════════════
#  진입점
# ═══════════════════════════════════════════════════════════════

def render_enhance_sim() -> None:
    st.header("⚡ 강화 시뮬레이터")

    # ── 사이드바 설정 ────────────────────────────────────────────
    with st.sidebar:
        st.divider()
        st.subheader("⚡ 강화 설정")
        tier_idx = st.selectbox(
            "티어", list(range(7)),
            format_func=lambda i: TIER_LABEL[i],
            index=3,
        )
        target = st.selectbox(
            "목표 단계", list(range(4, 11)),
            format_func=lambda v: f"+{v}",
            index=3,
        )
        def_gold = default_gold(tier_idx, target)
        gold = st.number_input(
            "강화당 골드", min_value=0, value=def_gold, step=100,
            help="기본값은 티어·단계에 따라 자동 계산됩니다.",
        )
        st.caption("강화당 주문서: **1개** (고정)")

    # ── 탭 ──────────────────────────────────────────────────────
    tab0, tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 확률표", "🎮 인터랙티브", "🎒 인벤토리", "📊 배치 통계", "🔬 몬테카를로 테이블"]
    )

    with tab0:
        _render_prob_table()
    with tab1:
        _render_interactive(tier_idx, target, gold)
    with tab2:
        render_inventory_sim()
    with tab3:
        _render_batch(tier_idx, target, gold)
    with tab4:
        _render_montecarlo(tier_idx)
