import streamlit as st
import requests
import pandas as pd
import json

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
            'history': 0
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
                    st.session_state.keepa_data = product_data.get('products')
                    st.write("Data from the last product is available in the chat agent for analysis.")
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