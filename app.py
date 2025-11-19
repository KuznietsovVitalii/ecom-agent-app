import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Import new services
from services.keepa_service import KeepaService
from services.llm_service import LLMService

# --- Constants ---
KEEPA_BASE_URL = "https://api.keepa.com"

# --- API Key Management (PRESERVED ORIGINAL LOGIC) ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    st.sidebar.success("API keys loaded from secrets.")
except (FileNotFoundError, KeyError):
    st.sidebar.header("API Key Configuration")
    st.sidebar.info("Enter your API keys below. For deployed apps, use Streamlit Secrets.")
    GEMINI_API_KEY = st.sidebar.text_input("Gemini API Key", type="password", key="gemini_api_key_local")
    KEEPA_API_KEY = st.sidebar.text_input("Keepa API Key", type="password", key="keepa_api_key_local")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize services
keepa_service = KeepaService(KEEPA_API_KEY)
llm_service = LLMService(GEMINI_API_KEY, keepa_service) if GEMINI_API_KEY else None

# --- Keepa API Functions (for manual fetching) ---
def get_product_info(api_key, asins, domain_id=1, **kwargs):
    return keepa_service.get_product_info(asins, domain_id, **kwargs)

# --- UI Functions ---
def clear_chat_history():
    st.session_state.messages = []

# --- Main App Layout ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v2.0 (Fixed)")

if not GEMINI_API_KEY or not KEEPA_API_KEY:
    st.error("API keys are not configured. Please add them in the sidebar.")
    st.stop()

st.sidebar.button("Clear Chat History", on_click=clear_chat_history)
domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}

# --- UI Components ---
st.header("Manual Data Fetching (Optional)")
st.info("Use this to pre-load data with specific parameters for the agent.")
with st.expander("Product Lookup"):
    asins_input = st.text_input("Enter ASIN(s)", "B00NLLUMOE,B07W7Q3G5R", key="manual_asin_input")
    selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0, key="manual_domain_select")
    
    st.subheader("Optional Parameters:")
    c1, c2, c3 = st.columns(3)
    with c1:
        p_stats = st.checkbox("Stats (90 days)", True, key="p_stats")
        p_history = st.checkbox("Sales Rank History", False, key="p_history")
        p_offers = st.checkbox("Offers", False, key="p_offers")
    with c2:
        p_days = st.number_input("History (days)", 0, 1000, 0, key="p_days")
        p_update = st.number_input("Refresh (hours)", -1, 24, 1, key="p_update")
    with c3:
        p_buybox = st.checkbox("Buy Box", False, key="p_buybox")
        p_rating = st.checkbox("Rating/Reviews", True, key="p_rating")

    if st.button("Fetch Product Info for Agent"):
        with st.spinner("Fetching..."):
            product_data = get_product_info(
                KEEPA_API_KEY, asins_input, domain_options[selected_domain],
                stats_days=90 if p_stats else 0, include_history=p_history,
                limit_days=p_days, include_offers=p_offers, include_buybox=p_buybox,
                include_rating=p_rating, force_update_hours=p_update
            )
            if "error" in product_data: 
                st.error(f"Error: {product_data['error']}")
            elif not product_data.get('products'): 
                st.warning("No products found.")
            else:
                st.success("Data fetched and available to the chat agent.")
                st.session_state.keepa_data = product_data.get('products')

st.divider()

st.header("Autonomous E-commerce Agent")
st.info("Ask about a product by ASIN, and the agent will fetch the data itself if needed.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if isinstance(message["content"], list):
            for part in message["content"]:
                if isinstance(part, str): st.markdown(part)
                elif isinstance(part, dict) and "data" in part: st.image(part["data"])
        else:
            st.markdown(message["content"])

if prompt := st.chat_input("e.g., 'What is the rating for B00NLLUMOE?'", accept_file=True, file_type=["jpg", "jpeg", "png"]):
    
    user_message_for_api = []
    user_message_for_history = []
    if prompt.text:
        user_message_for_api.append(prompt.text)
        user_message_for_history.append(prompt.text)
    if prompt.files:
        for uploaded_file in prompt.files:
            image_bytes = uploaded_file.getvalue()
            user_message_for_api.append({"mime_type": uploaded_file.type, "data": image_bytes})
            user_message_for_history.append({"mime_type": uploaded_file.type, "data": image_bytes})
    
    st.session_state.messages.append({"role": "user", "content": user_message_for_history})

    with st.chat_message("user"):
        for part in user_message_for_history:
            if isinstance(part, str): st.markdown(part)
            elif isinstance(part, dict) and "data" in part: st.image(part["data"])

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            context_data = st.session_state.get('keepa_data')
            assistant_response = llm_service.generate_response(user_message_for_api, context_data)
            st.markdown(assistant_response)
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})