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
st.title("E-commerce Analysis Agent v12 (File Upload Test)")

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
            "private_key": GCP_PRIVATE_KEY.replace('\n', '\n'),
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
def get_product_info(asins: str):
    """Fetches product info from Keepa for a list of ASINs. Returns a JSON string."""
    try:
        if isinstance(asins, list):
            asins = ','.join(asins)
        
        params = {
            'key': KEEPA_API_KEY,
            'domain': 1, # Hardcoded to USA
            'asin': asins,
            'stats': 90,
            'history': 1
        }
        response = requests.get("https://api.keepa.com/product", params=params)
        response.raise_for_status()
        return response.text
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
                    'asins': genai.protos.Schema(type=genai.protos.Type.STRING, description='A comma-separated string of ASINs.')
                },
                required=['asins']
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

system_instruction = """You are an expert e-commerce analyst for the USA market. Your knowledge is limited to data before 2023. You do not know the current date.

**Your instructions are:**

1.  **CRITICAL: ALWAYS USE TOOLS FOR CURRENT DATE:** If the user asks about the current date, today's date, or any other date-related question that implies currency, you **MUST** call the `google_search` tool with the query "current date". Do not make up a date. Do not respond with a date directly.
2.  **CRITICAL: PRIORITIZE KEEPA FOR AMAZON-RELATED QUERIES:** For *any* query related to Amazon products, sales, prices, or any other e-commerce data, you **MUST** use Keepa tools.
    *   If the user provides ASINs, use `get_product_info`.
    *   If the user asks a general question about products (e.g., "find best selling electronics"), use `google_search` *only* to find potential ASINs, and then immediately use `get_product_info` with those ASINs. Do not provide information directly from Google Search if Keepa can provide it.
3.  **Use Web Search for General Information:** Only use `google_search` for non-Amazon related queries, current events, or general knowledge questions.
4.  **Be Honest:** If you cannot find information, state that clearly.
"""

model = genai.GenerativeModel(
    model_name='models/gemini-2.5-pro-preview-06-05', 
    tools=tools,
    system_instruction=system_instruction
)

# --- Streamlit UI ---
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

with tab1:
    st.header("Keepa Tools")
    if st.button("Check Token Status"):
        with st.spinner("Checking..."):
            response = requests.get("https://api.keepa.com/token", params={'key': KEEPA_API_KEY})
            st.json(response.json())

    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s)", "B00NLLUMOE")
        if st.button("Get Product Info from Keepa"):
            with st.spinner("Fetching..."):
                data = get_product_info(asins_input)
                st.session_state.keepa_data = json.loads(data)
                st.write("Data is now available in the chat agent.")
                st.json(st.session_state.keepa_data)

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

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Say something and/or attach a file", accept_file=True, file_type=["jpg", "jpeg", "png", "csv", "txt", "pdf", "json"]):
        
        user_message_content = ""
        if prompt.text:
            user_message_content += prompt.text

        uploaded_files = prompt.files
        if uploaded_files:
            user_message_content += f"\n\n--- Attached Files ---\n"
            for uploaded_file in uploaded_files:
                user_message_content += f"- {uploaded_file.name}\n"

        st.session_state.messages.append({"role": "user", "content": user_message_content})
        
        with st.chat_message("user"):
            st.markdown(user_message_content)
            if uploaded_files:
                for uploaded_file in uploaded_files:
                    if uploaded_file.type in ["image/jpeg", "image/png"]:
                        st.image(uploaded_file)


        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                
                try:
                    history = []
                    for msg in st.session_state.messages[:-1]:
                        role = "model" if msg["role"] == "assistant" else "user"
                        history.append({'role': role, 'parts': [msg['content']]})

                    # Process uploaded files
                    file_context = ""
                    if uploaded_files:
                        for uploaded_file in uploaded_files:
                            if uploaded_file.type == "application/pdf":
                                pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.getvalue()))
                                for page in pdf_reader.pages:
                                    file_context += page.extract_text() + "\n"
                            elif uploaded_file.type in ["image/jpeg", "image/png"]:
                                # The model can't process images directly in this implementation
                                # I will just acknowledge the image
                                file_context += f"[Image attached: {uploaded_file.name}]\n"
                            else:
                                file_context += uploaded_file.getvalue().decode("utf-8") + "\n"

                    final_prompt = f"{file_context}\n\n{prompt.text}"

                    chat = model.start_chat(history=history)
                    response = chat.send_message(final_prompt)
                    
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