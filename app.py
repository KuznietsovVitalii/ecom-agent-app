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
st.title("E-commerce Analysis Agent v10 (MCP Logic)")

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

# --- Keepa MCP Logic ---
VERIFIED_AMAZON_CATEGORIES = {
    'Alexa Skills': 96814, 'Amazon Autos': 32373, 'Amazon Devices & Accessories': 402,
    'Appliances': 2619525011, 'Apps & Games': 2350149011, 'Arts, Crafts & Sewing': 2617941011,
    'Audible Books & Originals': 18145289011, 'Automotive': 15684181, 'Baby Products': 165796011,
    'Beauty & Personal Care': 3760911, 'Books': 283155, 'CDs & Vinyl': 5174,
    'Cell Phones & Accessories': 2335752011, 'Clothing, Shoes & Jewelry': 7141123011,
    'Collectibles & Fine Art': 4991425011, 'Credit & Payment Cards': 3561432011,
    'Digital Music': 163856011, 'Electronics': 172282, 'Everything Else': 10272111,
    'Gift Cards': 2238192011, 'Grocery & Gourmet Food': 16310101, 'Handmade Products': 11260432011,
    'Health & Household': 3760901, 'Home & Kitchen': 1055398, 'Industrial & Scientific': 16310091,
    'Kindle Store': 133140011, 'Luxury Stores': 18981045011, 'Magazine Subscriptions': 599858,
    'Movies & TV': 2625373011, 'Musical Instruments': 11091801, 'Office Products': 1064954,
    'Patio, Lawn & Garden': 2972638011, 'Pet Supplies': 2619533011, 'Prime Video': 2858778011,
    'Software': 229534, 'Sports & Outdoors': 3375251, 'Tools & Home Improvement': 228013,
    'Toys & Games': 165793011, 'Video Games': 468642, 'Video Shorts': 9013971011
}

def get_category_id(category_name: str):
    """Gets the Keepa category ID for a given category name."""
    return VERIFIED_AMAZON_CATEGORIES.get(category_name)

def search_products(
    category_id: int, min_price: int = None, max_price: int = None, 
    min_rating: float = None, sort_by: str = 'monthlySold', sort_order: str = 'desc', 
    per_page: int = 10
):
    """Searches for products on Keepa using various criteria."""
    try:
        selection = {
            "rootCategory": [str(category_id)],
            "productType": ["0"],
            "sort": [[sort_by, sort_order]]
        }
        if min_price is not None:
            selection["current_AMAZON"] = {"gte": min_price * 100}
        if max_price is not None:
            if "current_AMAZON" not in selection:
                selection["current_AMAZON"] = {}
            selection["current_AMAZON"]["lte"] = max_price * 100
        if min_rating is not None:
            selection["current_RATING_gte"] = int(min_rating * 10)

        params = {
            'key': KEEPA_API_KEY,
            'domain': 1, # Hardcoded to USA
            'selection': json.dumps(selection),
            'page': 0,
            'perPage': per_page
        }
        response = requests.post("https://api.keepa.com/query", params=params)
        response.raise_for_status()
        query_response = response.json()
        
        if query_response.get("asinList"):
            return get_product_info(query_response["asinList"])
        else:
            return json.dumps({"error": "No products found for the given criteria."})

    except Exception as e:
        return json.dumps({"error": str(e)})

def get_product_info(asins: list):
    """Fetches product info from Keepa for a list of ASINs."""
    try:
        if isinstance(asins, str):
            asins = asins.split(',')
        
        params = {
            'key': KEEPA_API_KEY,
            'domain': 1, # Hardcoded to USA
            'asin': ','.join(asins),
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
            name='get_category_id',
            description='Gets the Keepa category ID for a given category name.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    'category_name': genai.protos.Schema(type=genai.protos.Type.STRING, description='The name of the category (e.g., "Electronics").')
                },
                required=['category_name']
            )
        ),
        genai.protos.FunctionDeclaration(
            name='search_products',
            description='Searches for products on Keepa using various criteria.',
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    'category_id': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The Keepa category ID.'),
                    'min_price': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The minimum price in USD.'),
                    'max_price': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The maximum price in USD.'),
                    'min_rating': genai.protos.Schema(type=genai.protos.Type.NUMBER, description='The minimum rating (e.g., 4.5).'),
                    'sort_by': genai.protos.Schema(type=genai.protos.Type.STRING, description='The field to sort by (e.g., "monthlySold").'),
                    'sort_order': genai.protos.Schema(type=genai.protos.Type.STRING, description='The sort order ("asc" or "desc").'),
                    'per_page': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The number of products to return.')
                },
                required=['category_id']
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

system_instruction = """You are an expert e-commerce analyst for the USA market. Your primary goal is to provide accurate, data-driven insights based on the Keepa API.

**Your instructions are:**

1.  **Find Category ID:** If the user asks to find products in a category, you must first use the `get_category_id` tool to get the numerical ID for the category name.
2.  **Search for Products:** Once you have the category ID, use the `search_products` tool to find products. You can also use other filters like price and rating if the user specifies them.
3.  **Use Google Search as a last resort:** Only use `google_search` if you cannot find the information using the Keepa tools.
4.  **Be Honest and Accurate:** If you cannot find information, state that clearly. Do not invent data.
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
            response = requests.get("https://api.keepa.com/token", params={'key': KEEPA_API_KEY})
            st.json(response.json())

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
                    
                    chat = model.start_chat(history=history)
                    response = chat.send_message(st.session_state.messages[-1]['content'])
                    
                    while response.candidates[0].content.parts[0].function_call.name:
                        function_call = response.candidates[0].content.parts[0].function_call
                        function_name = function_call.name
                        args = {key: value for key, value in function_call.args.items()}
                        
                        if function_name == "get_category_id":
                            tool_result = get_category_id(**args)
                        elif function_name == "search_products":
                            tool_result = search_products(**args)
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