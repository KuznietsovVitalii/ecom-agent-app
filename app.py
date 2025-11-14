import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Constants and API Key Management ---
KEEPA_BASE_URL = "https://api.keepa.com"

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

# --- Helper & Tool Functions ---
def google_web_search(query: str) -> str:
    """
    Performs a web search for the given query. Use this to get current information, like today's date.
    """
    if "current date" in query.lower() or "today" in query.lower() or "date" in query.lower():
        return datetime.now().strftime("%Y-%m-%d")
    # In a real scenario, this would call a real search API.
    return f"Simulated web search results for '{query}': No real-time data available for this query."

def convert_keepa_time(keepa_timestamp):
    try:
        ts = int(keepa_timestamp)
        return (datetime(2000, 1, 1) + timedelta(minutes=ts)).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return keepa_timestamp

def format_keepa_data(data):
    if isinstance(data, dict):
        return {convert_keepa_time(k) if isinstance(k, int) else k: format_keepa_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [format_keepa_data(item) for item in data]
    else:
        return data

# --- Keepa API Functions ---
def get_token_status(api_key):
    if not api_key: return {"error": "Keepa API Key not provided."}
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/token", params={'key': api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def get_product_info(api_key, asins, domain_id=1, **kwargs):
    if not api_key: return {"error": "Keepa API Key not provided."}
    if isinstance(asins, str):
        asins = [asin.strip() for asin in asins.split(',')]
    
    params = {'key': api_key, 'domain': domain_id, 'asin': ','.join(asins)}
    if kwargs.get('stats_days'): params['stats'] = kwargs['stats_days']
    if kwargs.get('include_history'): params['history'] = 1
    if kwargs.get('limit_days'): params['days'] = kwargs['limit_days']
    if kwargs.get('include_offers'): params['offers'] = 100
    if kwargs.get('include_buybox'): params['buybox'] = 1
    if kwargs.get('include_rating'): params['rating'] = 1
    if kwargs.get('force_update_hours') is not None: params['update'] = kwargs['force_update_hours']

    try:
        response = requests.get(f"{KEEPA_BASE_URL}/product", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def get_best_sellers(api_key, category_id, domain_id=1):
    if not api_key: return {"error": "Keepa API Key not provided."}
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/bestsellers", params={'key': api_key, 'domain': domain_id, 'category': category_id})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

# --- Main App Layout ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v4")

if not GEMINI_API_KEY or not KEEPA_API_KEY:
    st.error("API keys are not configured. Please add them in the sidebar.")
    st.stop()

domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

# --- Keepa Tools Tab ---
with tab1:
    st.header("Keepa Tools")
    st.write("Direct access to Keepa API functions to load data for the agent.")

    with st.expander("Check API Token Status"):
        if st.button("Check Tokens"):
            with st.spinner("Checking..."):
                status = get_token_status(KEEPA_API_KEY)
                if "error" in status: st.error(f"Error: {status['error']}")
                else:
                    st.success(f"Tokens remaining: {status.get('tokensLeft')}")
                    st.json(status)

    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s) (comma-separated)", "B00NLLUMOE,B07W7Q3G5R")
        selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0)
        
        st.subheader("Optional Parameters:")
        c1, c2, c3 = st.columns(3)
        with c1:
            p_stats = st.checkbox("Include Stats (90 days)", True)
            p_history = st.checkbox("Include History", False)
            p_offers = st.checkbox("Include Offers", False)
        with c2:
            p_days = st.number_input("Limit History (days, 0=all)", 0, 1000, 0)
            p_update = st.number_input("Force Refresh (hours, -1=no)", -1, 24, 1)
        with c3:
            p_buybox = st.checkbox("Include Buy Box", False)
            p_rating = st.checkbox("Include Rating/Reviews", True)

        if st.button("Get Product Info"):
            with st.spinner("Fetching product data..."):
                product_data = get_product_info(
                    KEEPA_API_KEY, asins_input, domain_options[selected_domain],
                    stats_days=90 if p_stats else 0, include_history=p_history,
                    limit_days=p_days, include_offers=p_offers, include_buybox=p_buybox,
                    include_rating=p_rating, force_update_hours=p_update
                )
                if "error" in product_data: st.error(f"Error: {product_data['error']}")
                elif not product_data.get('products'): st.warning("No products found.")
                else:
                    st.success("Data fetched! It's now available for the chat agent.")
                    st.session_state.keepa_data = format_keepa_data(product_data.get('products'))

# --- Chat Agent Tab ---
with tab2:
    st.header("Chat with E-commerce Expert")
    st.info("Ask for analysis on the data you fetched, or ask for the current date.")

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

    if prompt := st.chat_input("Ask a question or upload an image...", accept_file=True, file_type=["jpg", "jpeg", "png"]):
        
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

        try:
            system_instruction = "You are an expert e-commerce analyst. Your own knowledge is outdated. To get the current date or any real-time information, you MUST use the 'google_web_search' tool. Do not rely on your internal knowledge for dates."
            model = genai.GenerativeModel(
                'gemini-flash-latest',
                tools=[google_web_search],
                system_instruction=system_instruction
            )
            
            context_prompt = ""
            if "keepa_data" in st.session_state and st.session_state.keepa_data:
                context_data = json.dumps(st.session_state.keepa_data, indent=2)
                MAX_CONTEXT_CHARS = 50000
                if len(context_data) > MAX_CONTEXT_CHARS:
                    context_data = context_data[:MAX_CONTEXT_CHARS] + "\n... (context truncated)"
                context_prompt = f"Use the following Keepa data as context for your analysis:\n\n--- Keepa Data Context ---\n{context_data}\n\n"
                del st.session_state.keepa_data

            final_prompt = [context_prompt] + user_message_for_api
            
            response = model.generate_content(final_prompt)
            
            assistant_response = response.text
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            st.rerun()

        except Exception as e:
            error_message = f"An unexpected error occurred with the AI model: {e}"
            st.session_state.messages.append({"role": "assistant", "content": error_message})
            st.rerun()