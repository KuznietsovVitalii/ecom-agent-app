import streamlit as st
import requests
import pandas as pd
import json
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v3 (with Memory)")

# --- API Key Management ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    # Load the GCP credentials from the TOML format
    gcp_creds_dict = json.loads(st.secrets["GCP_CREDS"])
except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
    st.error(f"An error occurred with your secret keys: {e}")
    st.info('''
        Please ensure you have the following secrets in your Streamlit Cloud settings in TOML format:
        1.  `GEMINI_API_KEY = "your_gemini_key"`
        2.  `KEEPA_API_KEY = "your_keepa_key"`
        3.  `GCP_CREDS = """{\'type\': \'service_account\', ...}"""`
    ''')
    st.stop()

# --- Google Sheets Persistence ---
SHEET_NAME = "ecom_agent_chat_history" # The name of the Google Sheet file
WORKSHEET_NAME = "history_log" # The name of the worksheet (tab) inside the file

@st.cache_resource
def get_gspread_client():
    """Connects to Google Sheets using service account credentials."""
    try:
        creds = Credentials.from_service_account_info(gcp_creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        st.stop()

def get_worksheet(client):
    """Gets or creates the specific worksheet for storing history."""
    try:
        spreadsheet = client.open(SHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        spreadsheet = client.create(SHEET_NAME)
        # Share with the user's email if you want them to see it easily
        # You can manually add your own email here for convenience
        # spreadsheet.share('your-email@gmail.com', perm_type='user', role='writer')
    
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows="100", cols="1")
        worksheet.update_acell('A1', '[]') # Initialize with empty JSON array
    return worksheet

def load_history_from_sheet(worksheet):
    """Loads chat history from a cell in the worksheet."""
    try:
        history_json = worksheet.acell('A1').value
        return json.loads(history_json or '[]')
    except (json.JSONDecodeError, TypeError):
        return [] # Return empty list if cell is empty or corrupt

def save_history_to_sheet(worksheet, history):
    """Saves chat history as a JSON string to a cell."""
    try:
        worksheet.update_acell('A1', json.dumps(history, indent=2))
    except Exception as e:
        st.warning(f"Could not save history to Google Sheets: {e}")

# --- Keepa API Logic (Ported from keepa_mcp_server) ---
KEEPA_BASE_URL = 'https://api.keepa.com'

def get_token_status(api_key):
    """Checks the remaining Keepa API tokens."""
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/token", params={'key': api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def get_product_info(api_key, asins, domain_id=1):
    """Looks up detailed product information by ASINs."""
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
    st.info("Your conversation is now saved automatically.")

    # Initialize Gspread client and worksheet
    client = get_gspread_client()
    worksheet = get_worksheet(client)

    # Initialize chat history from Google Sheet
    if "messages" not in st.session_state:
        st.session_state.messages = load_history_from_sheet(worksheet)

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask for analysis on the data you fetched..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
                    headers = {'Content-Type': 'application/json'}

                    system_instruction = {
                        "parts": [{"text": '''You are an expert e-commerce analyst specializing in Keepa data. 
- You have a persistent memory. Acknowledge previous conversations if relevant.
- Answer concisely. 
- When Keepa data is provided in the user's prompt, use it as the primary source for your analysis.
- Do not invent data. If the user asks a question that cannot be answered with the provided data, state that the information is missing.'''}]
                    }

                    api_history = []
                    for msg in st.session_state.messages:
                        role = "model" if msg["role"] == "assistant" else "user"
                        api_history.append({"role": role, "parts": [{"text": msg["content"]}]})

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