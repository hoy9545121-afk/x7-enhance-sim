"""X7 강화 시뮬레이터 — 단독 실행 앱
실행: streamlit run enhance_app.py
"""
import streamlit as st

st.set_page_config(layout="wide", page_title="X7 강화 시뮬레이터")

st.markdown("""
<style>
  .stApp { background-color: #060b14; color: #c8d8e8; }
  [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    color: #e8b84b !important;
  }
  [data-baseweb="select"] > div {
    background: #0d1a28 !important;
    border-color: #1e3048 !important;
  }
  [data-baseweb="select"] span {
    color: #dce8f5 !important;
    background-color: transparent !important;
  }
</style>
""", unsafe_allow_html=True)

from ui.enhance_sim import render_enhance_sim
render_enhance_sim()
