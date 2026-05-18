"""X7 강화 시뮬레이터 — 단독 실행 앱
실행: streamlit run enhance_app.py
"""
import streamlit as st

st.set_page_config(layout="wide", page_title="X7 강화 시뮬레이터")

st.markdown("""
<style>
  .stApp { background-color: #060b14; color: #c8d8e8; }

  /* 사이드바 배경 */
  [data-testid="stSidebar"] { background-color: #0b1220; }

  /* 사이드바 모든 텍스트·레이블 밝게 */
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stNumberInput label,
  [data-testid="stSidebar"] .stRadio label,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span {
    color: #c8d8e8 !important;
  }

  /* 사이드바 서브헤더 */
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {
    color: #e8b84b !important;
  }

  /* 셀렉트박스 */
  [data-baseweb="select"] > div {
    background: #0d1a28 !important;
    border-color: #1e3048 !important;
  }
  [data-baseweb="select"] span {
    color: #dce8f5 !important;
    background-color: transparent !important;
  }

  /* 메트릭 */
  [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    color: #e8b84b !important;
  }
  [data-testid="stMetricLabel"] {
    color: #7a9ab8 !important;
  }
</style>
""", unsafe_allow_html=True)

from ui.enhance_sim import render_enhance_sim
render_enhance_sim()
