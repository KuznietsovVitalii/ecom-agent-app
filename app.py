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

# --- Keepa API Functions ---
def get_product_info(api_key, asins, domain_id=1, **kwargs):
    if not api_key: return {"error": "Keepa API Key not provided."}
    if isinstance(asins, str):
        asins = [s.strip() for s in asins.split(',') if s.strip()]
    if not asins:
        return {"error": "ASIN parameter is empty."}

    params = {'key': api_key, 'domain': domain_id, 'asin': ','.join(asins)}
    # Add optional params from kwargs
    if kwargs.get('stats_days'): params['stats'] = kwargs.get('stats_days')
    if kwargs.get('include_rating'): params['rating'] = 1
    if kwargs.get('include_history'): params['history'] = 1
    if kwargs.get('limit_days'): params['days'] = kwargs.get('limit_days')
    if kwargs.get('include_offers'): params['offers'] = 100
    if kwargs.get('include_buybox'): params['buybox'] = 1
    if kwargs.get('force_update_hours') is not None: params['update'] = kwargs.get('force_update_hours')
    
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/product", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": f"API request failed with status {e.response.status_code if e.response else 'N/A'}. Reason: {e}"}

# --- Agent Tools ---
def google_web_search(query: str) -> str:
    """Use this ONLY when asked for today's date or similar real-time date/time questions."""
    if "current date" in query.lower() or "today" in query.lower() or "date" in query.lower():
        return datetime.now().strftime("%Y-%m-%d")
    return f"This tool can only fetch the current date. It cannot perform a general web search for '{query}'."

def get_amazon_product_details(asin: str, domain_id: int = 1) -> dict:
    """Fetches detailed information for a given Amazon product ASIN. Use this tool if the user asks a question about a specific product and you don't have the information."""
    if not asin or not isinstance(asin, str) or len(asin) < 10:
        return {"error": f"Invalid ASIN provided: '{asin}'. Please provide a valid 10-character ASIN."}
    
    # Let's try the minimal request again as it's the most likely to succeed
    product_data = get_product_info(
        api_key=KEEPA_API_KEY,
        asins=asin,
        domain_id=domain_id,
        stats_days=None,
        include_rating=True # Rating is usually available
    )
    return product_data

# --- UI Functions ---
def clear_chat_history():
    st.session_state.messages = []

# --- Main App Layout ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v9")

if not GEMINI_API_KEY or not KEEPA_API_KEY:
    st.error("API keys are not configured. Please add them in the sidebar.")
    st.stop()

# Add Clear Chat button to sidebar
st.sidebar.button("Clear Chat History", on_click=clear_chat_history)

domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}

# --- UI Components - No more tabs ---

st.header("Manual Data Fetching (Optional)")
st.info("Use this to pre-load data for the agent. The agent can also fetch data itself.")
with st.expander("Product Lookup"):
    asins_input = st.text_input("Enter ASIN(s)", "B00NLLUMOE,B07W7Q3G5R", key="manual_asin_input")
    selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0, key="manual_domain_select")
    if st.button("Fetch Product Info for Agent"):
        with st.spinner("Fetching..."):
            product_data = get_product_info(
                KEEPA_API_KEY, asins_input, domain_options[selected_domain],
                stats_days=90, include_rating=True, include_history=True # Fetch more data in manual mode
            )
            if "error" in product_data: st.error(f"Error: {product_data['error']}")
            elif not product_data.get('products'): st.warning("No products found.")
            else:
                st.success("Data fetched and available to the chat agent.")
                st.session_state.keepa_data = product_data.get('products')

st.divider()

st.header("Autonomous E-commerce Agent")
st.info("Ask about a product by ASIN, and the agent will fetch the data itself if needed. You can also ask for the current date.")

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

if prompt := st.chat_input("e.g., 'What is the rating for B00NLLUMOE?' or 'What is today's date?'", accept_file=True, file_type=["jpg", "jpeg", "png"]):
    
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
        system_instruction = """You are an expert e-commerce analyst...""" # Same as before
        model = genai.GenerativeModel(
            'gemini-flash-latest',
            tools=[google_web_search, get_amazon_product_details],
            system_instruction=system_instruction
        )
        
        context_prompt = ""
        if "keepa_data" in st.session_state and st.session_state.keepa_data:
            context_data = json.dumps(st.session_state.keepa_data)
            context_prompt = f"CONTEXT: ...\n{context_data}\n\n"
            del st.session_state.keepa_data

        final_prompt = [context_prompt] + user_message_for_api
        
        response = model.generate_content(final_prompt)
        
        if not response.candidates:
             assistant_response = "I'm sorry, I couldn't generate a response. Please try again."
        else:
            candidate = response.candidates[0]
            if not candidate.content.parts:
                assistant_response = "I'm sorry, I received an empty response. Please try again."
            else:
                if candidate.content.parts[0].function_call:
                    function_call = candidate.content.parts[0].function_call
                    function_name = function_call.name
                    
                    if function_name == "google_web_search":
                        function_args = {key: value for key, value in function_call.args.items()}
                        tool_result = google_web_search(**function_args)
                    elif function_name == "get_amazon_product_details":
                        function_args = {key: value for key, value in function_call.args.items()}
                        tool_result = get_amazon_product_details(**function_args)
                    else:
                        tool_result = f"Error: Unknown tool '{function_name}'"

                    second_response = model.generate_content(
                        final_prompt + [
                            genai.protos.Part(function_call=function_call),
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=function_name,
                                    response={"result": tool_result},
                                )
                            ),
                        ]
                    )
                    assistant_response = second_response.text
                else:
                    assistant_response = response.text

        st.session_state.messages.append({"role": "assistant", "content": assistant_response})
        st.rerun()

    except Exception as e:
        error_message = f"An unexpected error occurred with the AI model: {e}"
        st.session_state.messages.append({"role": "assistant", "content": error_message})
        st.rerun()
