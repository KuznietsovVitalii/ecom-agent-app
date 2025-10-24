import streamlit as st
import pandas as pd
import requests
import json
import time
from io import StringIO
import keepa
import re # Added re import

st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent")

# --- API Key & Secrets Instructions ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
except (FileNotFoundError, KeyError) as e:
    st.error(f"Missing secret: {e}. Please add your API keys to the Streamlit Cloud secrets.")
    st.info('''
        To add your secrets:
        1. Go to your app's dashboard on share.streamlit.io.
        2. Click on 'Settings'.
        3. Go to the 'Secrets' tab.
        4. Add your keys in TOML format, like this:

           GEMINI_API_KEY = "your_gemini_key_here"
           KEEPA_API_KEY = "your_keepa_key_here"
    ''')
    st.stop()

# --- Keepa API Logic (using keepa library) ---
api = keepa.Keepa(KEEPA_API_KEY, timeout=40) # Initialize Keepa API client

# --- Utility functions and data from keepa_competitor_research.py ---
sales_tiers = {
    -1:0, 0: 50, 50: 100, 100: 200, 200: 300, 300: 400, 400: 500, 500: 600,
    600: 700, 700: 800, 800: 900, 900: 1000, 1000: 2000, 2000: 3000, 3000: 4000,
    4000: 5000, 5000: 6000, 6000: 7000, 7000: 8000, 8000: 9000, 9000: 10000,
    10000: 20000, 20000: 30000, 30000: 40000, 40000: 50000, 50000: 60000,
    60000: 70000, 70000: 80000, 80000: 90000, 90000:100000, 100000: 150000
}

def convert_time(keepa_time:int) -> pd.Timestamp:
    if keepa_time == 0:
        return 'unknown'
    converted = (keepa_time + 21564000) * 60000
    converted = pd.to_datetime(converted, unit = 'ms').date()
    return converted

def perform_keepa_analysis(asins, api_client):
    all_results = []
    processed_asins = set()

    # Fetch raw product data using get_products from keepa_modules
    products_data = get_products(asins, api_client=api_client)
    st.info(f"Raw products_data received: {products_data}")

    if not products_data:
        st.warning(f"No products data found for the given ASINs.")
        return pd.DataFrame()

    for asin_item in asins:
        if asin_item in processed_asins:
            continue
        
        product = KeepaProduct(asin_item, domain="US", api_client=api_client) # Assuming US domain for now
        product.extract_from_products(products_data)
        product.get_last_days(days=90) # Call this to populate sales and price data

        if not product.exists:
            st.warning(f"Product data not found for ASIN: {asin_item}")
            continue
        
        processed_asins.add(asin_item)

        # Extract data using KeepaProduct methods
        title = product.title
        brand = product.brand
        listed_since = product.listed_since
        
        # Monthly Sales
        monthly_sales = product.min_sales # Using min_sales from KeepaProduct as a proxy for monthlySold
        monthly_sales_max = product.max_sales # Using max_sales from KeepaProduct
        avg_monthly_sales = product.avg_sales

        # Prices
        # Use raw product data for more accurate parsing as KeepaProduct might abstract too much
        raw_product_data = [p for p in products_data if p.get('asin') == asin_item]
        stats = raw_product_data[0].get('stats', {}) if raw_product_data else {}

        current_buybox_price = stats.get('buyBoxPrice', -1)
        if current_buybox_price != -1:
            current_buybox_price /= 100.0
        else:
            current_buybox_price = None

        # For avg_buybox_price_90, we need to check stats['avg'] list
        avg_buybox_price_90 = stats.get('avg', [])[1] if len(stats.get('avg', [])) > 1 else -1
        if avg_buybox_price_90 != -1:
            avg_buybox_price_90 /= 100.0
        else:
            avg_buybox_price_90 = None

        # Amazon Price - often not directly available as 'amazonPrice' dict in stats
        # We'll try to get it from the 'current' and 'avg' lists if possible, or use buybox as fallback
        current_amazon_price = None # Placeholder, needs more specific parsing if required
        avg_amazon_price_90 = None # Placeholder, needs more specific parsing if required

        # Sales Rank (BSR)
        current_bsr = stats.get('current', [])[2] if len(stats.get('current', [])) > 2 else None
        avg_bsr_90 = stats.get('avg', [])[2] if len(stats.get('avg', [])) > 2 else None

        # Amazon OOS percentage (KeepaProduct doesn't directly expose this, need to check raw data if available)
        amazon_oos_90 = "N/A" # Placeholder for now, as KeepaProduct doesn't directly expose

        price_drop_30_days = "N/A" # KeepaProduct doesn't directly expose this

        new_offer_count = product.new_offer_count
        sellers_new_fba_fbm = new_offer_count

        discount = product.coupon_amount
        final_price = product.final_price

        fees = product.fba_fees

        reviews = product.reviews
        rating = product.rating

        parent_asin = product.parent_asin
        main_image_link = product.image
        product_link = f'https://www.amazon.com/dp/{asin_item}'

        all_results.append({
            'ASIN': asin_item,
            'Title': title,
            'Brand': brand,
            'Listed Since': listed_since,
            'Min Monthly Sales': monthly_sales,
            'Max Monthly Sales': monthly_sales_max,
            'Avg Monthly Sales': avg_monthly_sales,
            'Current Amazon Price': f"${current_amazon_price:.2f}" if current_amazon_price is not None else 'N/A',
            'Avg 90-day Amazon Price': f"${avg_amazon_price_90:.2f}" if avg_amazon_price_90 is not None else 'N/A',
            'Current Buy Box Price': f"${current_buybox_price:.2f}" if current_buybox_price is not None else 'N/A',
            'Avg 90-day Buy Box Price': f"${avg_buybox_price_90:.2f}" if avg_buybox_price_90 is not None else 'N/A',
            'Current BSR': current_bsr if current_bsr is not None else 'N/A',
            'Avg 90-day BSR': avg_bsr_90 if avg_bsr_90 is not None else 'N/A',
            'Amazon OOS 90-day %': amazon_oos_90,
            'Price Drop 30-day %': price_drop_30_days,
            'New Seller Count': sellers_new_fba_fbm if sellers_new_fba_fbm is not None else 'N/A',
            'Discount': f"${discount:.2f}",
            'Final Price': f"${final_price:.2f}",
            'FBA Fees': f"${fees:.2f}",
            'Reviews': reviews if reviews is not None else 'N/A',
            'Rating': rating if rating is not None else 'N/A',
            'Parent ASIN': parent_asin,
            'Main Image Link': main_image_link,
            'Product Link': product_link
        })
    
    return pd.DataFrame(all_results)

def get_bestsellers(category_id: str, domain_id: int, sales_range: int = 0):
    """
    Retrieves a list of best-selling ASINs from Keepa based on category and sales range.
    """
    try:
        # Keepa API for bestsellers is different from product query
        # It returns a list of ASINs directly
        bestsellers_data = api.query_bestsellers(category=category_id, domain=domain_id, sales_range=sales_range)
        
        if bestsellers_data and 'bestSellersList' in bestsellers_data:
            # The 'bestSellersList' contains a list of ASINs
            return bestsellers_data['bestSellersList']['asinList']
        else:
            st.warning(f"No bestsellers found for category {category_id} in domain {domain_id}.")
            return []
    except Exception as e:
        st.error(f"Error fetching bestsellers from Keepa API: {e}")
        return []

def get_deals(query_json: dict):
    """
    Retrieves deals from Keepa based on a query JSON.
    """
    try:
        # Keepa API for deals uses a POST request with queryJSON in the payload
        # The keepa library handles the URL encoding for GET or payload for POST
        deals_data = api.query_deals(query_json)
        
        if deals_data and 'dr' in deals_data:
            # 'dr' contains a list of deal objects
            return deals_data['dr']
        else:
            st.warning(f"No deals found for the specified criteria.")
            return []
    except Exception as e:
        st.error(f"Error fetching deals from Keepa API: {e}")
        return []

# --- Chat with Agent ---
st.header("Chat with Keepa Expert Agent")
st.info("Ask the AI agent anything about e-commerce and Keepa data.")

# Initialize uploaded_file_data in session state
if "uploaded_file_data" not in st.session_state:
    st.session_state.uploaded_file_data = None

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt_obj := st.chat_input("Ask me about ASINs, products, or e-commerce strategy...", accept_file=True, file_type="csv"):
    # Extract text and files from the prompt object
    prompt = prompt_obj.text if prompt_obj.text else ""
    uploaded_files = prompt_obj.files if prompt_obj.files else []

    # Process uploaded files if any
    if uploaded_files:
        for uploaded_file in uploaded_files:
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            df = pd.read_csv(stringio)
            st.session_state.uploaded_file_data = df.to_json(orient="records", indent=2)
            st.session_state.messages.append({"role": "assistant", "content": f"CSV файл '{uploaded_file.name}' загружен и готов к анализу."})
            # If there's only a file and no text, we might want to rerun or just process the file.
            # For now, let's just add a message and continue with the text prompt if any.

    # Add user message (text part) to chat history
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)
    elif uploaded_files and not prompt: # If only files were uploaded without text
        # Add a placeholder message to history if only files were uploaded
        st.session_state.messages.append({"role": "user", "content": f"Uploaded {len(uploaded_files)} file(s)."})
        with st.chat_message("user"):
            st.markdown(f"Uploaded {len(uploaded_files)} file(s).")

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        with st.spinner("Agent is thinking..."):
            message_placeholder = st.empty()

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        with st.spinner("Agent is thinking..."):
            message_placeholder = st.empty()
            
            # Basic tool use: Check if the user wants to analyze ASINs
            if "analyze" in prompt.lower() and ("asin" in prompt.lower() or "amazon.com/dp" in prompt.lower()):
                # Improved ASIN extraction using regex to find 10-character ASINs (B00...)
                # This regex looks for patterns like B00... or B0... in words or URLs
                asin_pattern = re.compile(r'(B[0-9A-Z]{9})')
                found_asins = asin_pattern.findall(prompt)
                
                # Remove duplicates and ensure they are valid ASINs
                asins_in_prompt = list(set([asin for asin in found_asins if len(asin) == 10 and asin.startswith('B') and asin.isupper()]))
                
                if asins_in_prompt:
                    message_placeholder.info(f"Found ASINs: {', '.join(asins_in_prompt)}. Fetching detailed data from Keepa...")
                    
                    # Call the new advanced analysis function
                    keepa_df = perform_keepa_analysis(asins_in_ins_in_prompt, api)
                    
                    if not keepa_df.empty:
                        # Display results in a more readable format (e.g., a table)
                        st.session_state.messages.append({"role": "assistant", "content": "Here is the detailed Keepa analysis for the requested ASINs:"})
                        st.session_state.messages.append({"role": "assistant", "content": keepa_df.to_markdown(index=False)})
                        
                        # Also store the data in session state for potential AI analysis
                        st.session_state.keepa_analysis_data = keepa_df.to_json(orient="records", indent=2)
                        st.rerun()
                    else:
                        message_placeholder.error("Could not retrieve detailed data from Keepa for the specified ASINs.")
                else:
                    message_placeholder.warning("You mentioned analyzing ASINs, but I couldn't find any valid ASINs in your message. Please provide 10-character ASINs starting with 'B'.")
            elif "best sellers" in prompt.lower() or "top products" in prompt.lower():
                # Extract category and domain from prompt (simplified for now)
                # This part needs to be more robust, potentially using Gemini to extract entities
                category_id = "0" # Default to root category for now, or try to extract from prompt
                domain_id = 1 # Default to .com (US)
                sales_range = 90 # Default to 90-day average

                message_placeholder.info(f"Fetching best sellers for category {category_id} (domain {domain_id}, {sales_range}-day average)...")
                bestseller_asins = get_bestsellers(category_id, domain_id, sales_range)

                if bestseller_asins:
                    message_placeholder.success(f"Found {len(bestseller_asins)} best-selling ASINs. Analyzing the top 5...")
                    # Analyze the top few bestsellers for detailed data
                    top_bestsellers_df = perform_keepa_analysis(bestseller_asins[:5], api) # Analyze top 5
                    if not top_bestsellers_df.empty:
                        st.session_state.messages.append({"role": "assistant", "content": "Here is a detailed analysis of the top 5 best-selling ASINs:"})
                        st.session_state.messages.append({"role": "assistant", "content": top_bestsellers_df.to_markdown(index=False)})
                        st.session_state.keepa_analysis_data = top_bestsellers_df.to_json(orient="records", indent=2)
                        st.rerun()
                    else:
                        message_placeholder.error("Could not retrieve detailed data for the top best-selling ASINs.")
                else:
                    message_placeholder.warning("Could not find best sellers for the specified criteria. Please try a different category or refine your request.")
            elif "deals" in prompt.lower() or "price drops" in prompt.lower() or "discounts" in prompt.lower():
                # Simplified deal query for now. Needs robust parsing of user intent.
                # Default to a simple query for price drops in US, last 24 hours, new FBA price
                deal_query_json = {
                    "page": 0,
                    "domainId": 1, # US
                    "priceTypes": [10], # New FBA price
                    "dateRange": 0, # Last 24 hours
                    "deltaPercentRange": [10, -1], # At least 10% drop
                    "isFilterEnabled": True,
                    "sortType": 4 # Sort by percentage delta
                }
                message_placeholder.info("Fetching deals with significant price drops...")
                deals = get_deals(deal_query_json)

                if deals:
                    message_placeholder.success(f"Found {len(deals)} deals. Analyzing the top 5...")
                    # Extract ASINs from deals
                    deal_asins = [deal.get('asin') for deal in deals if deal.get('asin')]
                    if deal_asins:
                        top_deals_df = perform_keepa_analysis(deal_asins[:5], api) # Analyze top 5 deals
                        if not top_deals_df.empty:
                            st.session_state.messages.append({"role": "assistant", "content": "Here is a detailed analysis of the top 5 deals:"})
                            st.session_state.messages.append({"role": "assistant", "content": top_deals_df.to_markdown(index=False)})
                            st.session_state.keepa_analysis_data = top_deals_df.to_json(orient="records", indent=2)
                            st.rerun()
                        else:
                            message_placeholder.error("Could not retrieve detailed data for the top deals.")
                    else:
                        message_placeholder.error("No ASINs found in the fetched deals.")
                else:
                    message_placeholder.warning("Could not find any deals for the specified criteria. Try refining your request.")
            else:
                # Default to Gemini for general queries
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
                    headers = {'Content-Type': 'application/json'}

                    # 1. Define the system prompt for concise, data-driven answers
                    system_prompt_text = """You are an expert e-commerce analyst with deep knowledge of Keepa data.
- Answer the user's question directly and concisely.
- When asked for specific data (like price, rank, etc.), provide just that data without conversational filler.
- Avoid unnecessary explanations.
- Be brief and to the point."""

                    # 2. Construct chat history for the API
                    max_history = 10 # Remember the last 10 messages
                    history_to_send = st.session_state.messages[-max_history:]

                    # Map roles for the Gemini API (user and model)
                    model_contents = []
                    # Add system prompt as the first user message
                    model_contents.append({"role": "user", "parts": [{"text": system_prompt_text}]})
                    # Add a few-shot example response from the model
                    model_contents.append({"role": "model", "parts": [{"text": "Understood. I will be a direct and concise e-commerce expert."}]})

                    for msg in history_to_send:
                        role = "model" if msg["role"] == "assistant" else "user"
                        # Ensure we don't add the user's latest prompt twice
                        if msg["content"] != prompt: # This check is important to avoid duplicating the current prompt
                            model_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
                    
                    # Add uploaded file data to the current user prompt if available
                    current_user_message_text = prompt # This 'prompt' is the text part from prompt_obj
                    if st.session_state.uploaded_file_data:
                        current_user_message_text += f"""

Uploaded CSV Data:
{st.session_state.uploaded_file_data}"""
                    
                    if "keepa_analysis_data" in st.session_state and st.session_state.keepa_analysis_data:
                        current_user_message_text += f"""

Keepa Analysis Data:
{st.session_state.keepa_analysis_data}"""

                    # Add the current user prompt (potentially with file data)
                    model_contents.append({"role": "user", "parts": [{"text": current_user_message_text}]})

                    data = {"contents": model_contents}
                    
                    response = requests.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    response_json = response.json()

                    if 'candidates' not in response_json or not response_json['candidates']:
                        full_response = "I'm sorry, I don't have a response for that."
                    else:
                        full_response = response_json['candidates'][0]['content']['parts'][0]['text']
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})

                except (requests.exceptions.RequestException, Exception) as e:
                    error_message = f"An error occurred: {e}"
                    if 'response' in locals():
                        error_message += f"\n\nRaw API Response: {response.text}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})