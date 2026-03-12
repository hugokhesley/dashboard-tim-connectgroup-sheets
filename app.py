import streamlit as st

st.set_page_config(
    page_title="Connect Group",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.switch_page("pages/01_Tramitacao_Atual.py")
