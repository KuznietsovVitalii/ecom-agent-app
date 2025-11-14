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

# --- Keepa API Functions (used by tools) ---
def get_product_info(api_key, asins, domain_id=1, stats_days=None, include_rating=False):
    if not api_key: return {"error": "Keepa API Key not provided."}
    
    # Ensure asins is a list of strings
    if isinstance(asins, str):
        asins = [s.strip() for s in asins.split(',') if s.strip()]
    
    if not asins:
        return {"error": "ASIN parameter is empty."}

    params = {'key': api_key, 'domain': domain_id, 'asin': ','.join(asins)}
    if stats_days:
        params['stats'] = stats_days
    if include_rating:
        params['rating'] = 1
    
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/product", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        error_detail = f"API request failed with status {e.response.status_code if e.response else 'N/A'}. Reason: {e}"
        return {"error": error_detail}

# --- Agent Tools ---
def google_web_search(query: str) -> str:
    """
    Use this ONLY when asked for today's date or similar real-time date/time questions.
    """
    if "current date" in query.lower() or "today" in query.lower() or "date" in query.lower():
        return datetime.now().strftime("%Y-%m-%d")
    return f"This tool can only fetch the current date. It cannot perform a general web search for '{query}'."

def get_amazon_product_details(asin: str, domain_id: int = 1) -> dict:
    """
    Fetches detailed information for a given Amazon product ASIN. 
    Use this tool if the user asks a question about a specific product and you don't have the information.
    """
    if not asin or not isinstance(asin, str) or len(asin) < 10:
        return {"error": f"Invalid ASIN provided: '{asin}'. Please provide a valid 10-character ASIN."}
        
    product_data = get_product_info(
        api_key=KEEPA_API_KEY,
        asins=asin,
        domain_id=domain_id,
        stats_days=None,
        include_rating=False # Make the most basic request possible
    )
    return product_data

# --- Main App Layout ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v8")

if not GEMINI_API_KEY or not KEEPA_API_KEY:
    st.error("API keys are not configured. Please add them in the sidebar.")
    st.stop()

domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}
tab1, tab2 = st.tabs(["Manual Keepa Tools", "Autonomous Agent"])

with tab1:
    st.header("Manual Data Fetching")
    st.info("Use these tools to manually fetch data from Keepa. The fetched data will be available as context for the Autonomous Agent.")
    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s)", "B00NLLUMOE,B07W7Q3G5R")
        selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0)
        if st.button("Fetch Product Info for Agent"):
            with st.spinner("Fetching..."):
                product_data = get_product_info(
                    KEEPA_API_KEY, asins_input, domain_options[selected_domain],
                    stats_days=90, include_rating=True
                )
                if "error" in product_data: st.error(f"Error: {product_data['error']}")
                elif not product_data.get('products'): st.warning("No products found.")
                else:
                    st.success("Data fetched and available to the chat agent.")
                    st.session_state.keepa_data = product_data.get('products')

with tab2:
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
            system_instruction = """You are an expert e-commerce analyst. You have two tools available:
1. `google_web_search`: Use this ONLY to get the current date.
2. `get_amazon_product_details`: Use this to get detailed data for a specific Amazon product ASIN.

Your own knowledge is outdated. Follow these rules:
- If the user asks for the current date, you MUST use the `google_web_search` tool.
- If the user asks a question about a specific product (e.g., 'price of B00NLLUMOE', 'rating for B01N42S24C'), you MUST use the `get_amazon_product_details` tool to fetch the data. Do not answer from memory.
- If context data from a manual fetch is provided, use it for your analysis. If the user asks about a product not in the context, use your tool to fetch it.
"""
            model = genai.GenerativeModel(
                'gemini-flash-latest',
                tools=[google_web_search, get_amazon_product_details],
                system_instruction=system_instruction
            )
            
            context_prompt = ""
            if "keepa_data" in st.session_state and st.session_state.keepa_data:
                context_data = json.dumps(st.session_state.keepa_data)
                context_prompt = f"CONTEXT: The user has pre-loaded the following data from a manual fetch. Use this for analysis if relevant, but prefer to use your tools if the user asks for a new product:\n{context_data}\n\n"
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