import streamlit as st
import pandas as pd
import requests
import json
import time
from io import StringIO
import keepa # Added keepa import

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
           KEEPA_API_KEY = "icj30t3ms9osic264u5e1cqed0a2gl1gh33jb5k1eq0qmeo462qnfhb2b86rrfms"
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

def perform_keepa_analysis(asins):
    all_results = []
    
    # Keep track of processed ASINs to avoid duplicates if variations are pulled
    processed_asins = set()

    # Query Keepa API in batches
    for i in range(0, len(asins), 100): # Keepa API limit is 100 ASINs per request
        batch = asins[i:i+100]
        st.info(f"Fetching data for ASIN batch {i//100 + 1}...")
        
        try:
            products = api.query(batch, rating=True, domain=1) # domain 1 for US
        except Exception as e:
            st.error(f"Error querying Keepa API for batch {i//100 + 1}: {e}")
            continue

        if not products:
            st.warning(f"No products found for batch starting with {batch[0]}.")
            continue

        for product in products:
            asin = product.get('asin')
            if not asin or asin in processed_asins:
                continue
            processed_asins.add(asin)

            title = product.get('title')
            brand = product.get('brand')
            listed_since = convert_time(product.get('listedSince'))

            # Monthly Sales
            monthly_sales = product.get('monthlySold', -1)
            monthly_sales_max = sales_tiers.get(monthly_sales, 0) # assess max monthly sales based on sales tiers
            if monthly_sales == -1:
                monthly_sales = 0
            avg_monthly_sales = int(round(monthly_sales * 0.9 + monthly_sales_max * 0.1, 0))

            # Price and Discount
            price = 0
            try:
                # Assuming 'df_NEW' is the latest new price
                price_data = product.get('data', {}).get('df_NEW', [])
                if price_data:
                    # Find the last valid price
                    for p_val in reversed(price_data):
                        if isinstance(p_val, list) and len(p_val) > 1 and p_val[1] is not None:
                            price = p_val[1] / 100.0 # Keepa prices are in cents
                            break
            except Exception:
                price = 0

            coupon = product.get('coupon')
            discount = 0
            if coupon:
                discount_value = coupon[0]
                if discount_value <= 0: # Negative value means percentage
                    discount = round(price * abs(discount_value) / 100, 2)
                else: # Positive value means absolute discount in cents
                    discount = discount_value / 100.0
            final_price = price - discount

            # FBA Fees
            fees = 0
            try:
                fees = product.get('fbaFees', {}).get('pickAndPackFee', 0) / 100.0
            except Exception:
                fees = 0

            # Reviews and Rating
            reviews = None
            try:
                reviews_data = product.get('data', {}).get('COUNT_REVIEWS', [])
                if reviews_data:
                    reviews = reviews_data[-1][1] # Last value
            except Exception:
                reviews = None

            rating = None
            try:
                rating_data = product.get('data', {}).get('RATING', [])
                if rating_data:
                    rating = rating_data[-1][1] / 100.0 # Last value, Keepa rating is * 100
            except Exception:
                rating = None

            # Best Sellers Rank (BSR)
            bsr = None
            top_category = product.get('salesRankReference')
            if top_category and top_category != -1:
                bsr_history = product.get('salesRanks')
                if bsr_history:
                    # Get the last BSR for the top category
                    bsr_list = bsr_history.get(str(top_category), [])
                    if bsr_list:
                        bsr = bsr_list[-1][1] # Last value
            
            parent_asin = product.get('parentAsin')
            
            # Image and Product Links
            images = str(product.get('imagesCSV', '')).split(',')
            main_image_link = f'https://m.media-amazon.com/images/I/{images[0]}' if images and images[0] else ''
            product_link = f'https://www.amazon.com/dp/{asin}'

            all_results.append({
                'ASIN': asin,
                'Title': title,
                'Brand': brand,
                'Listed Since': listed_since,
                'Min Monthly Sales': monthly_sales,
                'Max Monthly Sales': monthly_sales_max,
                'Avg Monthly Sales': avg_monthly_sales,
                'Price': f"${price:.2f}",
                'Discount': f"${discount:.2f}",
                'Final Price': f"${final_price:.2f}",
                'FBA Fees': f"${fees:.2f}",
                'Reviews': reviews,
                'Rating': rating,
                'BSR': bsr,
                'Parent ASIN': parent_asin,
                'Main Image Link': main_image_link,
                'Product Link': product_link
            })
        
        if i + 100 < len(asins):
            st.write("Waiting 1 second before next batch to avoid rate limiting...")
            time.sleep(1) # Small delay to be safe, Keepa library handles rate limits but good practice

    return pd.DataFrame(all_results)

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
            if "analyze" in prompt.lower() and "asin" in prompt.lower():
                # A simple way to extract ASINs (can be improved with regex)
                asins_in_prompt = [word for word in prompt.replace(",", " ").split() if len(word) == 10 and word.startswith('B') and word.isupper()]
                
                if asins_in_prompt:
                    message_placeholder.info(f"Found ASINs: {', '.join(asins_in_prompt)}. Fetching detailed data from Keepa...")
                    
                    # Call the new advanced analysis function
                    keepa_df = perform_keepa_analysis(asins_in_prompt)
                    
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
            else:
                # Default to Gemini for general queries
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
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