"""강화 시뮬레이터 Streamlit UI
탭 구성: 🎮 인터랙티브 / 📊 배치 통계 / 🔬 몬테카를로 테이블
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
    step_once,
)
from simulator.constants import C
from charts.plotly_charts import _dark_layout


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

            st.caption(f"복구까지 {session.restore_counter}회 남음")

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
                st.error(f"❌ **실패 하락!** `+{last['prev_level']}` → `+{last['new_level']}`")

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
                rows.append({
                    "#"    : r["attempt_no"],
                    "강화" : f"+{r['prev_level']}→+{r['new_level']}",
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

def _render_montecarlo() -> None:
    st.markdown(
        "복구 메커니즘(3회 소진 → 동일 단계 아이템 소모)을 포함한 **예상 노강 아이템 소모량**을 "
        "Monte Carlo 시뮬레이션으로 계산합니다."
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
    targets = list(range(4, 11))

    st.markdown(f"**예상 노강 소모량** (n={n_used}, +1~+3은 항상 성공이므로 노강 1개 = 해당 단계 아이템 1개)")

    # ── 테이블 ──────────────────────────────────────────────────
    rows = []
    for t in targets:
        row: dict = {"강화 목표": f"+{t}"}
        for ti in range(7):
            val = all_pre[ti].get(t, 0.0)
            row[TIER_LABEL[ti]] = val
        rows.append(row)

    df_raw = pd.DataFrame(rows).set_index("강화 목표")

    # 포맷된 표시용 DataFrame
    df_disp = df_raw.copy()
    for col in df_disp.columns:
        df_disp[col] = df_disp[col].map(lambda v: f"{v:,.1f}")
    st.dataframe(df_disp, use_container_width=True)

    # ── 히트맵 ──────────────────────────────────────────────────
    import math
    z_vals   = [[all_pre[ti].get(t, 0.0) for ti in range(7)] for t in targets]
    z_log    = [[math.log10(max(v, 1.0)) for v in row] for row in z_vals]
    txt_vals = [[f"{all_pre[ti].get(t, 0):.0f}" for ti in range(7)] for t in targets]

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
        height=380,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "💡 값 = +0 노강 아이템 기준. 복구 시 소모된 아이템의 노강 비용이 재귀적으로 포함됩니다. "
        f"(n={n_used}회 시뮬, 변동 있음)"
    )


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
    tab1, tab2, tab3 = st.tabs(
        ["🎮 인터랙티브", "📊 배치 통계", "🔬 몬테카를로 테이블"]
    )

    with tab1:
        _render_interactive(tier_idx, target, gold)
    with tab2:
        _render_batch(tier_idx, target, gold)
    with tab3:
        _render_montecarlo()
