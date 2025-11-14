import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import google.generativeai as genai

KEEPA_BASE_URL = "https://api.keepa.com"

def get_token_status(api_key):
    """Checks the status of the Keepa API key."""
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/token", params={'key': api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def convert_keepa_time(keepa_timestamp):
    """Converts a Keepa integer timestamp (minutes since 2000-01-01) to a formatted string."""
    try:
        ts = int(keepa_timestamp)
        return (datetime(2000, 1, 1) + timedelta(minutes=ts)).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return keepa_timestamp

def format_keepa_data(data):
    """Recursively formats Keepa data, converting integer dictionary keys to dates."""
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            new_key = k
            if isinstance(k, int):
                try:
                    new_key = convert_keepa_time(k)
                except (ValueError, TypeError):
                    pass
            new_dict[new_key] = format_keepa_data(v)
        return new_dict
    elif isinstance(data, list):
        return [format_keepa_data(item) if isinstance(item, (dict, list)) else item for item in data]
    else:
        return data

st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v2")

# --- API Key Management ---
GEMINI_API_KEY = ""
KEEPA_API_KEY = ""

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    st.sidebar.success("API keys loaded from secrets.")
except (FileNotFoundError, KeyError):
    st.sidebar.header("API Key Configuration")
    st.sidebar.info("Enter your API keys below. For deployed apps, use Streamlit Secrets.")
    GEMINI_API_KEY = st.sidebar.text_input("Gemini API Key", type="password", key="gemini_api_key_local")
    KEEPA_API_KEY = st.sidebar.text_input("Keepa API Key", type="password", key="keepa_api_key_local")

if not GEMINI_API_KEY or not KEEPA_API_KEY:
    st.info("Please add your API keys in the sidebar to begin.")
    st.stop()

# Define domain options globally
domain_options = {
    'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4,
    'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8,
    'Mexico (.com.mx)': 11
}

def get_product_info(api_key, asins, domain_id=1, stats_days=90, include_history=False, limit_days=None, include_offers=False, include_buybox=False, include_rating=False, force_update_hours=1):
    """Looks up detailed product information by ASINs with configurable parameters."""
    if isinstance(asins, str):
        asins = [asin.strip() for asin in asins.split(',')]

    params = {
        'key': api_key,
        'domain': domain_id,
        'asin': ','.join(asins),
    }

    if stats_days is not None and stats_days > 0:
        params['stats'] = stats_days
    params['history'] = 1 if include_history else 0
    if limit_days is not None and limit_days > 0:
        params['days'] = limit_days
    if include_offers:
        params['offers'] = 100
    if include_buybox:
        params['buybox'] = 1
    if include_rating:
        params['rating'] = 1
    if force_update_hours is not None and force_update_hours >= -1:
        params['update'] = force_update_hours

    try:
        response = requests.get(f"{KEEPA_BASE_URL}/product", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def get_best_sellers(api_key, category_id, domain_id=1):
    """Fetches best sellers for a given category ID."""
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/bestsellers", params={
            'key': api_key,
            'domain': domain_id,
            'category': category_id
        })
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def find_products(api_key, domain_id=1, selection_params={}):
    """Finds products based on various criteria."""
    try:
        params = {
            'key': api_key,
            'domain': domain_id,
            'selection': json.dumps(selection_params)
        }
        response = requests.get(f"{KEEPA_BASE_URL}/query", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def call_keepa_product_finder(query_json: dict, domain_id: int = 1):
    """Calls the Keepa Product Finder API."""
    return find_products(KEEPA_API_KEY, domain_id, query_json)

def google_web_search(query: str) -> str:
    """Performs a web search."""
    if "current date" in query.lower() or "current time" in query.lower() or "today's date" in query.lower():
        return datetime.now().strftime("%Y-%m-%d")
    return f"Web search results for '{query}': [Simulated search result for real-time data]"

tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

with tab1:
    st.header("Keepa Tools")
    st.write("Direct access to Keepa API functions.")

    with st.expander("Check API Token Status"):
        if st.button("Check Tokens"):
            with st.spinner("Checking..."):
                status = get_token_status(KEEPA_API_KEY)
                if "error" in status:
                    st.error(f"Error: {status['error']}")
                else:
                    st.success(f"Tokens remaining: {status.get('tokensLeft')}")
                    st.json(status)

    with st.expander("Best Sellers"):
        category_id_input = st.text_input("Enter Category ID", "281052")
        bs_domain = st.selectbox("Amazon Domain (Best Sellers)", options=list(domain_options.keys()), index=0)
        if st.button("Find Best Sellers"):
            with st.spinner("Finding best sellers..."):
                domain_id = domain_options[bs_domain]
                bs_data = get_best_sellers(KEEPA_API_KEY, category_id_input, domain_id)
                if "error" in bs_data:
                    st.error(f"Error: {bs_data['error']}")
                elif not bs_data.get('bestSellersList'):
                    st.warning("No best sellers found for this category.")
                else:
                    st.success(f"Found {len(bs_data['bestSellersList'])} best sellers.")
                    df = pd.DataFrame(bs_data['bestSellersList'])
                    st.dataframe(df)
                    st.session_state.keepa_data = df.to_dict('records')
                    st.write("Best seller list is available in the chat agent for analysis.")

with tab2:
    st.header("Chat with Keepa Expert Agent")
    st.info("Ask the AI agent anything. Use the 'Keepa Tools' tab to load data, then ask for analysis here.")

    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s) (comma-separated)", "B00NLLUMOE,B07W7Q3G5R")
        selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0)

        st.subheader("Optional Keepa API Parameters:")
        col1, col2, col3 = st.columns(3)
        with col1:
            include_stats = st.checkbox("Include Stats (last 90 days)", value=True)
            include_history = st.checkbox("Include History (csv, salesRanks, etc.)", value=False)
            include_offers = st.checkbox("Include Offers (additional token cost)", value=False)
        with col2:
            limit_days = st.number_input("Limit History to last X days (0 for all)", min_value=0, value=0)
            force_update_hours = st.number_input("Force Refresh if older than X hours (0 for always live, -1 for no update)", min_value=-1, value=1)
        with col3:
            include_buybox = st.checkbox("Include Buy Box data (additional token cost)", value=False)
            include_rating = st.checkbox("Include Rating & Review Count History (may consume extra token)", value=False)

        if st.button("Get Product Info"):
            with st.spinner("Fetching product data..."):
                domain_id = domain_options[selected_domain]
                stats_param = 90 if include_stats else None
                product_data = get_product_info(
                    KEEPA_API_KEY,
                    asins_input,
                    domain_id,
                    stats_days=stats_param,
                    include_history=include_history,
                    limit_days=limit_days,
                    include_offers=include_offers,
                    include_buybox=include_buybox,
                    include_rating=include_rating,
                    force_update_hours=force_update_hours
                )

                if "error" in product_data:
                    st.error(f"Error: {product_data['error']}")
                elif not product_data.get('products'):
                    st.warning("No products found for the given ASINs.")
                else:
                    st.success("Data fetched successfully! Data is now available for the chat agent.")
                    formatted_products = format_keepa_data(product_data.get('products'))
                    st.session_state.keepa_data = formatted_products

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask for analysis on the data you fetched..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel(
                        'gemini-flash-latest',
                        tools=[call_keepa_product_finder]
                    )

                    system_prompt = """You are an expert e-commerce analyst...""" # Truncated for brevity

                    history_for_gemini = [
                        {"role": "user", "parts": [{"text": system_prompt}]},
                        {"role": "model", "parts": [{"text": "Understood."}]}
                    ]
                    for msg in st.session_state.messages[-10:]:
                        role = "user" if msg["role"] == "user" else "model"
                        history_for_gemini.append({"role": role, "parts": [{"text": msg["content"]}]})

                    if "keepa_data" in st.session_state and st.session_state.keepa_data:
                        context_data = json.dumps(st.session_state.keepa_data, indent=2)
                        MAX_CONTEXT_CHARS = 50000
                        if len(context_data) > MAX_CONTEXT_CHARS:
                            context_data = context_data[:MAX_CONTEXT_CHARS] + "\n... (context truncated)"
                        for item in reversed(history_for_gemini):
                            if item['role'] == 'user':
                                item['parts'][0]['text'] += f"\n\n--- Keepa Data Context ---\n{context_data}"
                                break
                        del st.session_state.keepa_data

                    response = model.generate_content(history_for_gemini)

                    if response.candidates[0].content.parts[0].function_call:
                        function_call = response.candidates[0].content.parts[0].function_call
                        function_name = function_call.name
                        function_args = {k: v for k, v in function_call.args.items()}

                        if function_name == "call_keepa_product_finder":
                            st.info(f"Agent is calling tool: {function_name} with args: {function_args}")
                            tool_output = call_keepa_product_finder(**function_args)
                            st.session_state.keepa_query_results = tool_output
                            
                            tool_response = model.generate_content(
                                history_for_gemini + [
                                    {"role": "model", "parts": [function_call]},
                                    {"role": "tool", "parts": [{"text": json.dumps(tool_output)}]}
                                ]
                            )
                            full_response = tool_response.candidates[0].content.parts[0].text
                        else:
                            full_response = f"Agent tried to call an unknown tool: {function_name}"
                    else:
                        full_response = response.candidates[0].content.parts[0].text
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})

                except Exception as e:
                    error_message = f"An unexpected error occurred: {e}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})