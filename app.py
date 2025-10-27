import streamlit as st
import requests
import pandas as pd
import json
import io
import PyPDF2
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")

# --- Custom CSS to pin chat input to the bottom ---
st.markdown("""
<style>
    .stChatInputContainer {
        position: fixed;
        bottom: 0;
        width: 100%;
        background-color: #0e1117; /* Match Streamlit's dark theme background */
        padding: 10px 1rem 10px 1rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
        z-index: 999;
    }
    /* Add padding to the bottom of the main container to avoid overlap */
    .main .block-container {
        padding-bottom: 6rem; 
    }
</style>
""", unsafe_allow_html=True)

st.title("E-commerce Analysis Agent v4 (with Memory Fix)")

# --- API Key Management ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    GCP_PROJECT_ID = st.secrets["GCP_PROJECT_ID"]
    GCP_CLIENT_EMAIL = st.secrets["GCP_CLIENT_EMAIL"]
    GCP_PRIVATE_KEY = st.secrets["GCP_PRIVATE_KEY"]
except KeyError as e:
    st.error(f"A required secret is missing: {e}. Please check your Streamlit Cloud secrets and ensure you have added GCP_PROJECT_ID, GCP_CLIENT_EMAIL, and GCP_PRIVATE_KEY.")
    st.stop()

# --- Google Sheets Persistence ---
SHEET_NAME = "ecom_agent_chat_history"
WORKSHEET_NAME = "history_log"

@st.cache_resource
def get_gspread_client():
    """Connects to Google Sheets using service account credentials built from individual secrets."""
    try:
        creds_dict = {
            "type": "service_account",
            "project_id": GCP_PROJECT_ID,
            "private_key_id": "72121b20078a955bd2ff628a3184d5e7e66275de",
            "private_key": GCP_PRIVATE_KEY,
            "client_email": GCP_CLIENT_EMAIL,
            "client_id": "100512556019710416916",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{GCP_CLIENT_EMAIL.replace('@', '%40')}"
        }
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets. Please ensure your GCP secrets are correct. Error: {e}")
        st.stop()

def get_worksheet(client):
    """Gets the specific worksheet, assuming the spreadsheet is pre-created and shared."""
    try:
        spreadsheet = client.open(SHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet named '{SHEET_NAME}' not found. Please create it manually and share it with the service account email.")
        st.stop()
    
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows="100", cols="1")
        worksheet.update_acell('A1', '[]')
    return worksheet

def load_history_from_sheet(worksheet):
    """Loads chat history from a cell in the worksheet with extra debugging."""
    try:
        st.info("Attempting to load history from sheet...")
        history_json = worksheet.acell('A1').value
        st.info(f"Type of data from sheet: {type(history_json)}")
        st.text_area("Raw data from sheet", str(history_json), height=100)

        if not history_json or history_json.strip() == "":
            st.warning("Sheet cell is empty. Initializing.")
            worksheet.update_acell('A1', '[]')
            return []
        
        st.success("Data loaded from sheet. Attempting to parse JSON...")
        history = json.loads(history_json)
        st.success("JSON parsed successfully!")
        return history
    except Exception as e:
        st.error(f"CRITICAL ERROR loading history: {e}")
        return []

def save_history_to_sheet(worksheet, history):
    """Saves chat history as a JSON string to a cell."""
    try:
        worksheet.update_acell('A1', json.dumps(history, indent=2))
    except Exception as e:
        st.error(f"ERROR saving history: {e}")

# --- Keepa API Logic ---
KEEPA_BASE_URL = 'https://api.keepa.com'

def get_token_status(api_key):
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/token", params={'key': api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def get_product_info(api_key, asins, domain_id=1):
    if isinstance(asins, str):
        asins = [asin.strip() for asin in asins.split(',')]
    
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/product", params={'key': api_key, 'domain': domain_id, 'asin': ','.join(asins), 'stats': 90, 'history': 0})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

# --- Streamlit UI ---
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

with tab1:
    st.header("Keepa Tools")
    st.write("Direct access to Keepa API functions. Load data here to analyze it in the chat.")

    with st.expander("Check API Token Status"):
        if st.button("Check Tokens"):
            with st.spinner("Checking..."):
                status = get_token_status(KEEPA_API_KEY)
                if "error" in status:
                    st.error(f"Error: {status['error']}")
                else:
                    st.success(f"Tokens remaining: {status.get('tokensLeft')}")
                    st.json(status)

    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s) (comma-separated)", "B00NLLUMOE,B07W7Q3G5R")
        domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}
        selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0)
        
        if st.button("Get Product Info"):
            with st.spinner("Fetching product data..."):
                domain_id = domain_options[selected_domain]
                product_data = get_product_info(KEEPA_API_KEY, asins_input, domain_id)
                if "error" in product_data:
                    st.error(f"Error: {product_data['error']}")
                elif not product_data.get('products'):
                    st.warning("No products found for the given ASINs.")
                else:
                    st.success("Data fetched successfully!")
                    st.session_state.keepa_data = product_data.get('products')
                    st.write("Data is now available in the chat agent for analysis.")
                    st.json(st.session_state.keepa_data)

with tab2:
    st.header("Chat with Keepa Expert Agent")

    if st.button("Очистить чат"):
        st.session_state.messages = []
        # Also clear the persisted history
        client = get_gspread_client()
        worksheet = get_worksheet(client)
        save_history_to_sheet(worksheet, [])
        st.rerun()

    st.info("Your conversation is now saved automatically.")

    # Initialize Gspread client and worksheet
    client = get_gspread_client()
    worksheet = get_worksheet(client)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = load_history_from_sheet(worksheet)

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # New integrated chat input
    prompt = st.chat_input(
        "Input chat...", 
        accept_file=True, 
        file_type=["txt", "pdf", "csv", "json", "md"]
    )

    if prompt:
        user_prompt_text = prompt.text if prompt.text else " " # Use a space if no text
        st.session_state.messages.append({"role": "user", "content": user_prompt_text})
        with st.chat_message("user"):
            if prompt.text:
                st.markdown(prompt.text)
            if prompt.files:
                st.markdown(f"_{len(prompt.files)} file(s) attached for analysis._")

        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
                    headers = {'Content-Type': 'application/json'}

                    # --- File Processing Logic ---
                    file_context = ""
                    if prompt.files:
                        st.info(f"Processing {len(prompt.files)} uploaded file(s)...")
                        for uploaded_file in prompt.files:
                            try:
                                file_context += f"--- Content from {uploaded_file.name} ---\n"
                                if uploaded_file.type == "application/pdf":
                                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.getvalue()))
                                    for page in pdf_reader.pages:
                                        file_context += page.extract_text() + "\n"
                                else: # Assume text-based
                                    file_context += uploaded_file.getvalue().decode('utf-8') + "\n"
                                file_context += f"--- End of {uploaded_file.name} ---\n\n"
                            except Exception as e:
                                st.error(f"Error processing file {uploaded_file.name}: {e}")
                    # --- End of File Processing ---

                    system_instruction = {
                        "parts": [{"text": '''You are an expert e-commerce analyst specializing in Keepa data. 
- You have a persistent memory. Acknowledge previous conversations if relevant.
- Answer concisely. 
- When context from Keepa data or attached files is provided, use it as the primary source for your analysis.
- Do not invent data. If the user asks a question that cannot be answered with the provided data, state that the information is missing.'''}]}

                    api_history = []
                    for msg in st.session_state.messages:
                        role = "model" if msg["role"] == "assistant" else "user"
                        api_history.append({"role": role, "parts": [{"text": msg["content"]}]})

                    # Inject file context into the last user message
                    if file_context:
                        api_history[-1]['parts'][0]['text'] = f"CONTEXT FROM ATTACHED FILES:\n{file_context}\n\nUSER PROMPT: {api_history[-1]['parts'][0]['text']}"

                    if "keepa_data" in st.session_state and st.session_state.keepa_data:
                        context_data = json.dumps(st.session_state.keepa_data, indent=2)
                        api_history[-1]['parts'][0]['text'] += f"\n\n--- Keepa Data Context ---\n{context_data}"
                        del st.session_state.keepa_data
                    
                    data = {
                        "contents": api_history,
                        "system_instruction": system_instruction
                    }
                    
                    response = requests.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    
                    response_json = response.json()
                    full_response = response_json['candidates'][0]['content']['parts'][0]['text']
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                    save_history_to_sheet(worksheet, st.session_state.messages)

                except requests.exceptions.RequestException as e:
                    error_message = f"API Error: {e}\n\nResponse: {response.text if 'response' in locals() else 'N/A'}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})
                except (KeyError, IndexError) as e:
                    error_message = f"Could not parse AI response: {e}\n\nResponse JSON: {response_json}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})