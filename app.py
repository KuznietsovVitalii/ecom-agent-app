import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta

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
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("API keys (GEMINI_API_KEY, KEEPA_API_KEY) not found in Streamlit secrets. Please add them.")
    st.info('''
        To add secrets on Streamlit Community Cloud:
        1. Go to your app's dashboard.
        2. Click on 'Settings' > 'Secrets'.
        3. Add your keys in TOML format, e.g.:
           GEMINI_API_KEY = "your_gemini_key"
           KEEPA_API_KEY = "your_keepa_key"
    ''')
    st.stop()

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
        response = requests.get(f"{KEEPA_BASE_URL}/product", params={
            'key': api_key,
            'domain': domain_id,
            'asin': ','.join(asins),
            'stats': 90,
            'history': 1
        })
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

# --- Streamlit UI ---
tab1, tab2, tab3 = st.tabs(["Keepa Tools", "Chat with Agent", "Advanced Keepa Analysis"])

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

    # --- Product Lookup ---
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
                    # Format the data to convert Keepa timestamps
                    formatted_products = format_keepa_data(product_data.get('products'))
                    st.session_state.keepa_data = formatted_products
                    st.write("Data from the last product (with converted dates) is available in the chat agent for analysis.")
                    st.json(st.session_state.keepa_data)

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

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

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

                    system_prompt = """You are an expert e-commerce analyst specializing in Keepa data. 
                    - Answer concisely. 
                    - When data is available in the user's prompt, use it as the primary source for your analysis.
                    - Do not invent data. If the user asks a question that cannot be answered with the provided data, state that the information is missing."""

                    # Construct chat history
                    history = [{"role": "user", "parts": [{"text": system_prompt}]}, {"role": "model", "parts": [{"text": "Understood."}]}]
                    for msg in st.session_state.messages[-10:]: # Send last 10 messages
                        role = "model" if msg["role"] == "assistant" else "user"
                        history.append({"role": role, "parts": [{"text": msg["content"]}]})

                    # Add context from Keepa tools if it exists
                    if "keepa_data" in st.session_state and st.session_state.keepa_data:
                        context_data = json.dumps(st.session_state.keepa_data, indent=2)
                        # Find the last user message and append context to it
                        for item in reversed(history):
                            if item['role'] == 'user':
                                item['parts'][0]['text'] += f"\n\n--- Keepa Data Context ---\n{context_data}"
                                break
                        # Clean up session state after using it
                        del st.session_state.keepa_data

                    data = {"contents": history}
                    
                    response = requests.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    
                    response_json = response.json()
                    full_response = response_json['candidates'][0]['content']['parts'][0]['text']
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})

                except requests.exceptions.RequestException as e:
                    error_message = f"API Error: {e}\n\nResponse: {response.text if 'response' in locals() else 'N/A'}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})
                except (KeyError, IndexError) as e:
                    error_message = f"Could not parse AI response: {e}\n\nResponse JSON: {response_json}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})

with tab3:
    st.header("Advanced Keepa Analysis")
    st.write("Perform in-depth analysis using Keepa historical data.")

    if "keepa_data" in st.session_state and st.session_state.keepa_data:
        product_asins = list(st.session_state.keepa_data.keys())
        selected_asin = st.selectbox("Select ASIN for analysis", product_asins)

        if selected_asin:
            product_info = st.session_state.keepa_data[selected_asin]

            st.subheader("Advanced Price History Analysis")
            st.write("Analyzing price trends, volatility, and optimal pricing points.")
            
            if 'csv' in product_info and product_info['csv']:
                # Keepa's 'csv' array is interleaved. We need to know the order from product.csvType
                # For simplicity, let's assume a common structure for now:
                # [timestamp, AMAZON, NEW, USED, SALES_RANK, LIST_PRICE, COLLECTIBLE, REFURBISHED, NEW_FBM_SHIPPING, USED_SHIPPING, COLLECTIBLE_SHIPPING, REFURBISHED_SHIPPING, TRADE_IN]
                # We'll extract NEW price (index 2) and SALES_RANK (index 4)
                
                # Find the indices for NEW price and SALES_RANK from product_info['csvType']
                # This is a more robust way to parse the CSV data
                csv_types = product_info.get('csvType', [])
                new_price_index = -1
                sales_rank_index = -1
                
                for i, type_val in enumerate(csv_types):
                    if type_val == 1: # Keepa's code for NEW price
                        new_price_index = i
                    elif type_val == 3: # Keepa's code for SALES_RANK
                        sales_rank_index = i
                
                if new_price_index != -1 and sales_rank_index != -1:
                    timestamps = []
                    new_prices = []
                    sales_ranks = []

                    # The 'csv' array is flat: [timestamp1, val1_type1, val1_type2, ..., timestamp2, val2_type1, ...]
                    # The number of values per timestamp is len(csv_types)
                    values_per_timestamp = len(csv_types)
                    
                    for i in range(0, len(product_info['csv']), values_per_timestamp + 1):
                        timestamp_keepa = product_info['csv'][i]
                        timestamps.append(convert_keepa_time(timestamp_keepa))
                        
                        # Extract values based on their indices
                        if new_price_index != -1:
                            new_prices.append(product_info['csv'][i + 1 + new_price_index])
                        if sales_rank_index != -1:
                            sales_ranks.append(product_info['csv'][i + 1 + sales_rank_index])

                    df_price_history = pd.DataFrame({
                        'Date': pd.to_datetime(timestamps),
                        'New Price': new_prices
                    })
                    df_price_history.set_index('Date', inplace=True)
                    
                    # Filter out -1 values (Keepa's way of indicating no data)
                    df_price_history = df_price_history[df_price_history['New Price'] != -1]
                    
                    if not df_price_history.empty:
                        st.line_chart(df_price_history['New Price'])
                        
                        st.write("Price Statistics (New Price):")
                        st.write(f"Min Price: {df_price_history['New Price'].min() / 100.0:.2f}")
                        st.write(f"Max Price: {df_price_history['New Price'].max() / 100.0:.2f}")
                        st.write(f"Average Price: {df_price_history['New Price'].mean() / 100.0:.2f}")
                        st.write(f"Std Dev Price: {df_price_history['New Price'].std() / 100.0:.2f}")
                    else:
                        st.info("No valid 'New Price' data found for this ASIN.")
                else:
                    st.info("Could not find 'New Price' or 'Sales Rank' indices in Keepa data.")
            else:
                st.info("No historical 'csv' data available for this ASIN.")

            st.subheader("Sales Rank Trend Analysis")
            st.write("Analyzing sales velocity, rank stability, and seasonal patterns.")
            
            if 'csv' in product_info and product_info['csv']:
                csv_types = product_info.get('csvType', [])
                sales_rank_index = -1
                
                for i, type_val in enumerate(csv_types):
                    if type_val == 3: # Keepa's code for SALES_RANK
                        sales_rank_index = i
                
                if sales_rank_index != -1:
                    timestamps = []
                    sales_ranks = []

                    values_per_timestamp = len(csv_types)
                    
                    for i in range(0, len(product_info['csv']), values_per_timestamp + 1):
                        timestamp_keepa = product_info['csv'][i]
                        timestamps.append(convert_keepa_time(timestamp_keepa))
                        
                        if sales_rank_index != -1:
                            sales_ranks.append(product_info['csv'][i + 1 + sales_rank_index])

                    df_sales_rank_history = pd.DataFrame({
                        'Date': pd.to_datetime(timestamps),
                        'Sales Rank': sales_ranks
                    })
                    df_sales_rank_history.set_index('Date', inplace=True)
                    
                    # Filter out -1 values (Keepa's way of indicating no data)
                    df_sales_rank_history = df_sales_rank_history[df_sales_rank_history['Sales Rank'] != -1]
                    
                    if not df_sales_rank_history.empty:
                        st.line_chart(df_sales_rank_history['Sales Rank'])
                        
                        st.write("Sales Rank Statistics:")
                        st.write(f"Min Sales Rank: {df_sales_rank_history['Sales Rank'].min()}")
                        st.write(f"Max Sales Rank: {df_sales_rank_history['Sales Rank'].max()}")
                        st.write(f"Average Sales Rank: {df_sales_rank_history['Sales Rank'].mean():.0f}")
                        st.write(f"Std Dev Sales Rank: {df_sales_rank_history['Sales Rank'].std():.0f}")
                    else:
                        st.info("No valid 'Sales Rank' data found for this ASIN.")
                else:
                    st.info("Could not find 'Sales Rank' index in Keepa data.")
            else:
                st.info("No historical 'csv' data available for this ASIN.")
    else:
        st.info("Please fetch product data using the 'Keepa Tools' tab first.")