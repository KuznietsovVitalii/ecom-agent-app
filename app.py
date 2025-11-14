import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import google.generativeai as genai

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
            # Attempt to convert key if it's an integer (potential Keepa timestamp)
            if isinstance(k, int):
                try:
                    new_key = convert_keepa_time(k)
                except (ValueError, TypeError):
                    pass # Keep original key if conversion fails
            new_dict[new_key] = format_keepa_data(v) # Recursively call for values
        return new_dict
    elif isinstance(data, list):
        # For lists, recursively process elements only if they are dicts or lists.
        # Do NOT attempt to convert timestamps here with item[0], as it's handled elsewhere
        # or is not a generic list of [timestamp, value] pairs.
        return [format_keepa_data(item) if isinstance(item, (dict, list)) else item for item in data]
    else:
        return data

st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent v2")

# --- API Key Management ---
GEMINI_API_KEY = ""
KEEPA_API_KEY = ""

try:
    # Try to get keys from Streamlit secrets (for cloud deployment)
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    st.sidebar.success("API keys loaded from secrets.")
except (FileNotFoundError, KeyError):
    # Fallback for local development
    st.sidebar.header("API Key Configuration")
    st.sidebar.info("Enter your API keys below. For deployed apps, use Streamlit Secrets.")
    GEMINI_API_KEY = st.sidebar.text_input("Gemini API Key", type="password", key="gemini_api_key_local")
    KEEPA_API_KEY = st.sidebar.text_input("Keepa API Key", type="password", key="keepa_api_key_local")

if not GEMINI_API_KEY or not KEEPA_API_KEY:
    st.info("Please add your API keys in the sidebar to begin.")
    st.stop()

# Define domain options globally
domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}



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
        params['offers'] = 100 # Request max offers
    
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
    """
    Calls the Keepa Product Finder API to search for products based on various criteria.
    Args:
        query_json (dict): The query JSON containing all request parameters for the Keepa /query API.
        domain_id (int): Integer value for the Amazon locale (e.g., 1 for .com).
    Returns:
        dict: The JSON response from the Keepa /query API.
    """
    # Assuming KEEPA_API_KEY is accessible globally
    return find_products(KEEPA_API_KEY, domain_id, query_json)

def google_web_search(query: str) -> str:
    """
    Performs a web search for the given query.
    If the query is related to the current date or time, it returns the current date.
    Otherwise, it returns a placeholder web search result.
    """
    if "current date" in query.lower() or "current time" in query.lower() or "today's date" in query.lower():
        return datetime.now().strftime("%Y-%m-%d")
    return f"Web search results for '{query}': [Simulated search result for real-time data]"

# --- Gemini Model and Tools ---

# --- Streamlit UI ---
# This is a test comment to force a new commit.
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

with tab1:
    st.header("Keepa Tools")
    st.write("Direct access to Keepa API functions.")

    # --- Token Status ---
    with st.expander("Check API Token Status"):
        if st.button("Check Tokens"):
            with st.spinner("Checking..."):
                status = get_token_status(KEEPA_API_KEY)
                if "error" in status:
                    st.error(f"Error: {status['error']}")
                else:
                    st.success(f"Tokens remaining: {status.get('tokensLeft')}")
                    st.json(status)

    

    # --- Best Sellers ---
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

    # --- Product Lookup (Moved from tab1) ---
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
                
                stats_param = 90 if include_stats else None # Default to 90 days if stats is included
                
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
                    # Format the data to convert Keepa timestamps
                    formatted_products = format_keepa_data(product_data.get('products'))
                    st.session_state.keepa_data = formatted_products
                    # Removed st.json and st.dataframe output as requested.

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask for analysis on the data you fetched...", accept_file=True, file_type=["jpg", "jpeg", "png", "csv", "txt"]):
        st.session_state.messages.append({"role": "user", "content": prompt.text if prompt.text else "File uploaded"})
        with st.chat_message("user"):
            if prompt.text:
                st.markdown(prompt.text)
            if prompt.files:
                for uploaded_file in prompt.files:
                    st.write(f"Uploaded file: {uploaded_file.name} ({uploaded_file.size} bytes)")
                    # You can add logic here to process the uploaded file, e.g., read its content
                    # For now, just acknowledging the upload.

        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                
                try:
                    # Configure the Gemini API with the key
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel(
                        'gemini-flash-latest',
                        tools=[call_keepa_product_finder] # Register the tool
                    )

                    system_prompt = """You are an expert e-commerce analyst specializing in Keepa data. 
                    - Answer concisely. 
                    - When data is available in the user's prompt, use it as the primary source for your analysis.
                    - Do not invent data. If the user asks a question that cannot be answered with the provided data, state that the information is missing.
                    - You have access to a tool called `call_keepa_product_finder` to search for products. Use it when the user asks to find products based on criteria.
                    - The `call_keepa_product_finder` tool requires a `query_json` dictionary and a `domain_id`.
                    - The `query_json` can contain various filters as described in the Keepa Product Finder documentation.
                    - Always specify the `domain_id` when calling `call_keepa_product_finder`. Default to 1 for Amazon.com if not specified by the user.
                    - After calling the tool, summarize the results (e.g., number of ASINs found) and offer further analysis."""

                    # Construct chat history
                    history_for_gemini = [{"role": "user", "parts": [{"text": system_prompt}]}, {"role": "model", "parts": [{"text": "Understood."}]}]
                    for msg in st.session_state.messages[-10:]: # Send last 10 messages
                        role = "user" if msg["role"] == "user" else "model" # Gemini expects 'user' and 'model' roles
                        history_for_gemini.append({"role": role, "parts": [{"text": msg["content"]}]})

                    # Add context from Keepa tools if it exists
                    if "keepa_data" in st.session_state and st.session_state.keepa_data:
                        context_data = json.dumps(st.session_state.keepa_data, indent=2)
                        
                        # Truncate context_data if it's too large to avoid token limit errors
                        MAX_CONTEXT_CHARS = 50000 # Approximately 12500 tokens (4 chars/token)
                        if len(context_data) > MAX_CONTEXT_CHARS:
                            context_data = context_data[:MAX_CONTEXT_CHARS] + "\n... (context truncated due to size limit)"

                        # Find the last user message and append context to it
                        for item in reversed(history_for_gemini):
                            if item['role'] == 'user':
                                item['parts'][0]['text'] += f"\n\n--- Keepa Data Context ---\n{context_data}"
                                break
                        # Clean up session state after using it
                        del st.session_state.keepa_data

                    # Make the initial generateContent call
                    response = model.generate_content(history_for_gemini)
                    
                    # Handle potential function calls
                    if response.candidates[0].content.parts[0].function_call:
                        function_call = response.candidates[0].content.parts[0].function_call
                        function_name = function_call.name
                        function_args = {k: v for k, v in function_call.args.items()} # Convert to dict

                        if function_name == "call_keepa_product_finder":
                            st.info(f"Agent is calling tool: {function_name} with args: {function_args}")
                            tool_output = call_keepa_product_finder(**function_args)
                            st.session_state.keepa_query_results = tool_output # Store results
                            st.write("Product Finder results stored in session for analysis.")
                            
                            # Send tool output back to Gemini
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

                except Exception as e: # Catch broader exceptions for debugging
                    error_message = f"An unexpected error occurred: {e}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})

