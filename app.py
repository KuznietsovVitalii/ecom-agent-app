import streamlit as st
import requests
import pandas as pd
import json
import io
import PyPDF2
import uuid
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import keepa

# --- Configuration ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v7 (Domain Selector)")

# --- Domain Selector ---
domain_options = {
    'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 
    'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 
    'Mexico (.com.mx)': 11
}
selected_domain_name = st.selectbox(
    "Select Amazon Domain", 
    options=list(domain_options.keys()),
    index=0 # Default to USA
)
st.session_state.domain_id = domain_options[selected_domain_name]
st.info(f"Selected Domain: **{selected_domain_name}**")

# --- Session ID ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
st.info(f"Your session ID: {st.session_state.session_id}")

# --- API Key Management ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    GCP_PROJECT_ID = st.secrets["GCP_PROJECT_ID"]
    GCP_CLIENT_EMAIL = st.secrets["GCP_CLIENT_EMAIL"]
    GCP_PRIVATE_KEY = st.secrets["GCP_PRIVATE_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"A required secret is missing: {e}. Please check your Streamlit Cloud secrets.")
    st.stop()

@st.cache_resource
def get_keepa_api():
    try:
        return keepa.Keepa(st.secrets["KEEPA_API_KEY"])
    except Exception as e:
        st.error(f"Failed to initialize Keepa API. Error: {e}")
        st.stop()

keepa_api = get_keepa_api()

# --- Google Sheets Persistence ---
SHEET_NAME = "ecom_agent_chat_history"
WORKSHEET_NAME = f"history_log_{st.session_state.session_id}"

@st.cache_resource
def get_gspread_client():
    try:
        creds_dict = {
            "type": "service_account",
            "project_id": GCP_PROJECT_ID,
            "private_key": GCP_PRIVATE_KEY.replace('\\n', '\n'),
            "client_email": GCP_CLIENT_EMAIL,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{GCP_CLIENT_EMAIL.replace('@', '%40')}"
        }
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets. Error: {e}")
        st.stop()

def get_worksheet(client):
    try:
        spreadsheet = client.open(SHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet '{SHEET_NAME}' not found. Please create it and share it with {GCP_CLIENT_EMAIL}.")
        st.stop()
    try:
        return spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="2")
        worksheet.update('A1:B1', [['Role', 'Content']])
        return worksheet

@st.cache_data(ttl="5m")
def load_history_from_sheet(_worksheet):
    """Loads chat history from a cell in the worksheet."""
    records = _worksheet.get_all_records()
    return [{"role": r['Role'], "content": r['Content']} for r in records]

def save_history_to_sheet(worksheet, history):
    data = [[msg['role'], msg['content']] for msg in history]
    worksheet.clear()
    worksheet.update('A1:B1', [['Role', 'Content']])
    if data:
        worksheet.append_rows(data, table_range='A2')

# --- Tool Functions ---
def get_product_info(asins: str, domain_id: int, limit: int = 10):
    """
    Fetches product info from Keepa for a list of ASINs.
    Limits the number of ASINs to process to keep the request fast.
    Returns a JSON string.
    """
    try:
        if isinstance(asins, str):
            asins = asins.split(',')
        
        # Limit the number of ASINs to process
        asins_to_query = asins[:limit]
        
        products = keepa_api.query(asins_to_query, domain=domain_id, stats=90, history=True)
        return json.dumps(products)
    except Exception as e:
        return json.dumps({"error": str(e)})

def search_for_categories(search_term: str, domain_id: int):
    """Searches for Keepa category IDs. Returns a JSON string of matching categories."""
    try:
        categories = keepa_api.search_for_categories(search_term, domain=domain_id)
        return json.dumps(categories)
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_best_sellers(category_id: str, domain_id: int):
    """Gets the list of best seller ASINs for a given Keepa category ID. Returns a JSON string."""
    try:
        asins = keepa_api.best_sellers_query(category_id, domain=domain_id)
        return json.dumps(asins)
    except Exception as e:
        return json.dumps({"error": str(e)})

def google_search(query: str):
    """Performs a Google search."""
    return f"Performing Google search for: {query}"

# --- Gemini Model and Tools ---
tools = [
    Tool(function_declarations=[
        genai.protos.FunctionDeclaration(
            name='get_product_info',
            description='Fetches detailed product information from Keepa for a list of ASINs.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    'asins': genai.protos.Schema(type=genai.protos.Type.STRING, description='A comma-separated string of ASINs.'),
                    'domain_id': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The Amazon domain ID. Get this from the user context.'),
                    'limit': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The maximum number of ASINs to look up. Defaults to 10.')
                },
                required=['asins', 'domain_id']
            )
        ),
        genai.protos.FunctionDeclaration(
            name='search_for_categories',
            description='Searches for Keepa category IDs by a search term.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    'search_term': genai.protos.Schema(type=genai.protos.Type.STRING, description='The category to search for (e.g., "electronics").'),
                    'domain_id': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The Amazon domain ID. Get this from the user context.')
                },
                required=['search_term', 'domain_id']
            )
        ),
        genai.protos.FunctionDeclaration(
            name='get_best_sellers',
            description='Gets the list of best seller ASINs for a given Keepa category ID.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    'category_id': genai.protos.Schema(type=genai.protos.Type.STRING, description='The Keepa category ID.'),
                    'domain_id': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The Amazon domain ID. Get this from the user context.')
                },
                required=['category_id', 'domain_id']
            )
        ),
        genai.protos.FunctionDeclaration(
            name='google_search',
            description='Performs a Google search for general queries.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={'query': genai.protos.Schema(type=genai.protos.Type.STRING, description='The search query.')},
                required=['query']
            )
        )
    ])
]

system_instruction = """You are an expert e-commerce analyst. Your primary goal is to provide accurate, data-driven insights based on the Keepa API.

**Your instructions are:**

1.  **Get the Domain ID:** The user's prompt will always start with a "CONTEXT" line that contains the `domain_id`. You **must** use this `domain_id` for all Keepa API calls. For example, if the context says `domain_id: 1`, you must use `1` for the `domain_id` parameter in your tool calls.
2.  **Find ASINs:** If the user asks for best sellers or products in a category, first use the `search_for_categories` tool to find the correct category ID. Then, use the `get_best_sellers` tool with that ID to get a list of ASINs.
3.  **Get Product Data (Top 10):** When you get a list of best seller ASINs, use the `get_product_info` tool on the **top 10 ASINs only** to keep the response fast. Inform the user that you are only showing the top 10.
4.  **Prioritize Keepa:** Always prefer using the Keepa tools (`search_for_categories`, `get_best_sellers`, `get_product_info`) for any product-related query.
5.  **Use Google Search Sparingly:** Only use `google_search` if the user explicitly asks, or for non-product related questions.
6.  **Be Honest and Accurate:** If you cannot find information, state that clearly. Do not invent data.
"""

model = genai.GenerativeModel(
    model_name='models/gemini-2.5-pro', 
    tools=tools,
    system_instruction=system_instruction
)

# --- Streamlit UI ---
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

with tab1:
    st.header("Keepa Tools")
    if st.button("Check Token Status"):
        with st.spinner("Checking..."):
            st.json(keepa_api.token_status)

    if st.button("List Available Gemini Models"):
        with st.spinner("Fetching models..."):
            try:
                st.info("Found the following models that support 'generateContent':")
                st.json([m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods])
            except Exception as e:
                st.error(f"Could not list models: {e}")

with tab2:
    st.header("Chat with Agent")
    
    client = get_gspread_client()
    worksheet = get_worksheet(client)

    if "messages" not in st.session_state:
        with st.spinner("Loading chat history..."):
            st.session_state.messages = load_history_from_sheet(worksheet)

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        save_history_to_sheet(worksheet, [])
        st.rerun()

    chat_container = st.container(height=500)
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("Ask the agent..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                
                try:
                    history = []
                    for msg in st.session_state.messages[:-1]:
                        role = "model" if msg["role"] == "assistant" else "user"
                        history.append({'role': role, 'parts': [msg['content']]})
                    
                    # Add domain context to the user's prompt
                    user_prompt = f"CONTEXT: You are currently operating in the {selected_domain_name} domain (domain_id: {st.session_state.domain_id}).\n\nUSER PROMPT: {st.session_state.messages[-1]['content']}"

                    chat = model.start_chat(history=history)
                    response = chat.send_message(user_prompt)
                    
                    while response.candidates[0].content.parts[0].function_call.name:
                        function_call = response.candidates[0].content.parts[0].function_call
                        function_name = function_call.name
                        args = {key: value for key, value in function_call.args.items()}
                        
                        if function_name == "get_product_info":
                            tool_result = get_product_info(**args)
                        elif function_name == "search_for_categories":
                            tool_result = search_for_categories(**args)
                        elif function_name == "get_best_sellers":
                            tool_result = get_best_sellers(**args)
                        elif function_name == "google_search":
                            tool_result = google_search(**args)
                        else:
                            raise ValueError(f"Unknown function call: {function_name}")

                        response = chat.send_message(
                            genai.protos.Part(function_response=genai.protos.FunctionResponse(name=function_name, response={'result': tool_result}))
                        )

                    final_response = response.candidates[0].content.parts[0].text
                    message_placeholder.markdown(final_response)
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                    save_history_to_sheet(worksheet, st.session_state.messages)

                except Exception as e:
                    error_message = f"An error occurred: {e}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})
                    save_history_to_sheet(worksheet, st.session_state.messages)
