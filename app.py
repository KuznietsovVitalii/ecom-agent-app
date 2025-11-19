import streamlit as st
from utils.config import load_api_keys
from ui.sidebar import render_sidebar
from ui.sales_estimator import render_sales_estimator_tab
from ui.chat import render_chat_interface
from services.keepa_service import KeepaService
from services.llm_service import LLMService

# --- Main App Configuration ---
st.set_page_config(layout="wide", page_title="E-commerce Agent v2")
st.title("E-commerce Analysis Agent v2.0")

# --- Initialization ---
api_keys = load_api_keys()
render_sidebar()

if not api_keys.get("GEMINI_API_KEY") or not api_keys.get("KEEPA_API_KEY"):
    st.warning("Please configure API keys in the sidebar to continue.")
    st.stop()

# Initialize Services
keepa_service = KeepaService(api_keys["KEEPA_API_KEY"])
llm_service = LLMService(api_keys["GEMINI_API_KEY"], keepa_service)

# --- Tabs Layout ---
tab1, tab2 = st.tabs(["🤖 AI Agent", "📊 Sales Estimator"])

with tab1:
    render_chat_interface(llm_service)

with tab2:
    render_sales_estimator_tab(api_keys["KEEPA_API_KEY"])