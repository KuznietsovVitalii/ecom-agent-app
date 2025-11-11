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

# --- Configuration ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v5 (Tools+Memory)")

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

# --- Google Sheets Persistence ---
SHEET_NAME = "ecom_agent_chat_history"
WORKSHEET_NAME = f"history_log_{st.session_state.session_id}"

@st.cache_resource
def get_gspread_client():
    try:
        creds_dict = {
            "type": "service_account",
            "project_id": GCP_PROJECT_ID,
            "private_key_id": "your_private_key_id", # This can be found in your GCP service account JSON
            "private_key": GCP_PRIVATE_KEY.replace('\n', '\n'),
            "client_email": GCP_CLIENT_EMAIL,
            "client_id": "your_client_id", # This can be found in your GCP service account JSON
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

def load_history_from_sheet(worksheet):
    records = worksheet.get_all_records()
    return [{"role": r['Role'], "content": r['Content']} for r in records]

def save_history_to_sheet(worksheet, history):
    data = [[msg['role'], msg['content']] for msg in history]
    worksheet.clear()
    worksheet.update('A1:B1', [['Role', 'Content']])
    if data:
        worksheet.append_rows(data, table_range='A2')


# --- Keepa Time Conversion ---
def convert_keepa_time(keepa_timestamp):
    try:
        ts = int(keepa_timestamp)
        return (datetime(2000, 1, 1) + timedelta(minutes=ts)).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OverflowError):
        return keepa_timestamp

def format_keepa_data(data):
    if isinstance(data, dict):
        return {k: format_keepa_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], list) and len(data[0]) > 0 and (isinstance(data[0][0], int) or str(data[0][0]).isdigit()):
             return [[convert_keepa_time(item[0])] + item[1:] for item in data]
        return [format_keepa_data(item) for item in data]
    else:
        return data

# --- Tool Functions ---
def get_product_info(asins: str, domain_id: int = 1):
    """Fetches product info from Keepa. Returns a JSON string."""
    if isinstance(asins, list):
        asins = ','.join(asins)
    try:
        response = requests.get(f"https://api.keepa.com/product", params={'key': KEEPA_API_KEY, 'domain': domain_id, 'asin': asins, 'stats': 90, 'history': 1})
        response.raise_for_status()
        product_data = response.json()
        formatted_data = format_keepa_data(product_data)
        return json.dumps(formatted_data)
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})

def google_search(query: str):
    """Performs a Google search."""
    # This is a placeholder. The CLI environment intercepts this.
    return f"Performing Google search for: {query}"

# --- Gemini Model and Tools ---
tools = [
    Tool(function_declarations=[
        genai.protos.FunctionDeclaration(
            name='get_product_info',
            description='Fetches product information from Keepa for a list of ASINs.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    'asins': genai.protos.Schema(type=genai.protos.Type.STRING, description='A comma-separated string of ASINs.'),
                    'domain_id': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The Amazon domain ID (e.g., 1 for .com).')
                },
                required=['asins']
            )
        ),
        genai.protos.FunctionDeclaration(
            name='google_search',
            description='Performs a Google search.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={'query': genai.protos.Schema(type=genai.protos.Type.STRING, description='The search query.')},
                required=['query']
            )
        )
    ])
]
model = genai.GenerativeModel(model_name='gemini-pro', tools=tools)

# --- Streamlit UI ---
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

with tab1:
    st.header("Keepa Tools")
    if st.button("Check Token Status"):
        with st.spinner("Checking..."):
            st.json(requests.get(f"https://api.keepa.com/token", params={'key': KEEPA_API_KEY}).json())

    if st.button("List Available Gemini Models"):
        with st.spinner("Fetching models..."):
            try:
                models = genai.list_models()
                model_info = []
                for m in models:
                    if 'generateContent' in m.supported_generation_methods:
                        model_info.append(f"**Model name:** {m.name}")
                st.info("Found the following models that support 'generateContent':")
                st.markdown("\n\n".join(model_info))
            except Exception as e:
                st.error(f"Could not list models: {e}")

    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s)", "B00NLLUMOE")
        if st.button("Get Product Info from Keepa"):
            with st.spinner("Fetching..."):
                data_str = get_product_info(asins_input)
                data = json.loads(data_str)
                if "error" in data:
                    st.error(data['error'])
                else:
                    st.success("Data fetched and formatted!")
                    st.session_state.keepa_data = data.get('products')
                    st.write("Data is now available in the chat agent.")
                    st.json(st.session_state.keepa_data)

with tab2:
    st.header("Chat with Agent")
    
    client = get_gspread_client()
    worksheet = get_worksheet(client)

    if "messages" not in st.session_state:
        st.session_state.messages = load_history_from_sheet(worksheet)

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        save_history_to_sheet(worksheet, [])
        st.rerun()

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
                    chat = model.start_chat(history=history)
                    response = chat.send_message(st.session_state.messages[-1]['content'])
                    
                    while response.candidates[0].content.parts[0].function_call.name:
                        function_call = response.candidates[0].content.parts[0].function_call
                        function_name = function_call.name
                        args = {key: value for key, value in function_call.args.items()}
                        
                        if function_name == "get_product_info":
                            tool_result = get_product_info(**args)
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