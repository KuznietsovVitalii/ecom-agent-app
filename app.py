import streamlit as st
from ui.sidebar import render_sidebar
from ui.sales_estimator import render_sales_estimator_tab
from ui.chat import render_chat_interface
from services.keepa_service import KeepaService
from services.llm_service import LLMService
import google.generativeai as genai

# --- Main App Configuration ---
st.set_page_config(layout="wide", page_title="E-commerce Agent v2")
st.title("E-commerce Analysis Agent v2.0")

# --- API Key Loading (ORIGINAL LOGIC) ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("API keys not found in Streamlit secrets. Please configure them.")
    st.stop()

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Services
keepa_service = KeepaService(KEEPA_API_KEY)
llm_service = LLMService(GEMINI_API_KEY, keepa_service)

# --- Render UI ---
render_sidebar()

# --- Tabs Layout ---
tab1, tab2 = st.tabs(["🤖 AI Agent", "📊 Sales Estimator"])

with tab1:
    render_chat_interface(llm_service)

with tab2:
    render_sales_estimator_tab(KEEPA_API_KEY)