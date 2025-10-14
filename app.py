import streamlit as st
import pandas as pd
import keepa
import google.generativeai as genai
import json

# --- Page Configuration ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent")

# --- API Key & Secrets Instructions ---
# Use st.secrets to securely access API keys
try:
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    st.error("Secrets file not found. Please add your API keys to the Streamlit Cloud secrets.")
    st.info("""
        To add your secrets:
        1. Go to your app's dashboard on share.streamlit.io.
        2. Click on 'Settings'.
        3. Go to the 'Secrets' tab.
        4. Add your keys in TOML format, like this:
           KEEPA_API_KEY = "your_keepa_key_here"
           GEMINI_API_KEY = "your_gemini_key_here"
    """)
    st.stop()

# --- Core Logic Function ---
def get_ai_analysis(asins):
    """
    Fetches data from Keepa and gets a per-ASIN AI analysis from Gemini.
    Returns a DataFrame with the analysis.
    """
    # 1. Configure APIs
    try:
        api = keepa.Keepa(KEEPA_API_KEY)
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"Failed to configure APIs. Please check your keys. Error: {e}")
        return None

    # 2. Fetch data from Keepa
    try:
        products = api.query(asins, stats=90) # Get 90-day stats
    except Exception as e:
        st.error(f"Failed to fetch data from Keepa. Error: {e}")
        return None

    if not products:
        st.warning("No product data returned from Keepa for the given ASINs.")
        return None

    # 3. Format Keepa data for the AI and for the raw data table
    product_data_for_ai = []
    raw_data_for_table = []
    for product in products:
        asin = product.get('asin', 'N/A')
        title = product.get('title', 'N/A')
        avg_rank = product.get('stats', {}).get('avg', [{}])[0].get('90', 'N/A')
        current_price = product.get('data', {}).get('NEW', [-1])[-1] / 100.0 if product.get('data', {}).get('NEW') else 'N/A'

        product_data_for_ai.append({
            "asin": asin,
            "title": title,
            "90_day_avg_sales_rank": avg_rank,
            "current_new_price": current_price
        })
        raw_data_for_table.append({
            "ASIN": asin,
            "Title": title,
            "90-Day Avg. Rank": avg_rank,
            "Current Price": current_price
        })
    
    raw_df = pd.DataFrame(raw_data_for_table)

    # 4. Call Gemini for analysis
    prompt = f"""
    You are an expert e-commerce analyst.
    Analyze the following product data retrieved from Keepa.
    For each product, provide a concise, one-sentence insight in a new 'analysis' field.
    Focus on whether the product seems promising or risky, based on its sales rank and price.
    Return the analysis as a clean JSON array of objects, where each object has two keys: "asin" and "analysis". Do not include any other text or formatting outside of the JSON array.

    Data:
    {json.dumps(product_data_for_ai, indent=2)}

    Example of desired output format:
    [
      {{
        "asin": "B004IPRQGE",
        "analysis": "This product seems promising due to its low price and good sales rank."
      }},
      {{
        "asin": "B09JBGR1XW",
        "analysis": "This product might be risky due to its high price despite a good sales rank."
      }}
    ]
    """

    try:
        response = model.generate_content(prompt)
        # Clean up the response to get only the JSON part
        cleaned_response = response.text.strip().replace('```json', '').replace('```', '')
        analysis_data = json.loads(cleaned_response)
        analysis_df = pd.DataFrame(analysis_data)
        # Rename 'asin' to 'ASIN' to match the other dataframe
        if 'asin' in analysis_df.columns:
            analysis_df = analysis_df.rename(columns={'asin': 'ASIN'})

    except (json.JSONDecodeError, Exception) as e:
        st.error(f"Failed to get or parse analysis from AI. Error: {e}")
        st.text("AI Response was:")
        st.text(response.text)
        # If AI fails, we still return the raw data
        return raw_df

    # 5. Merge raw data with analysis
    if not analysis_df.empty:
        merged_df = pd.merge(raw_df, analysis_df, on="ASIN", how="left")
        return merged_df
    else:
        return raw_df

# --- Streamlit UI ---
st.info("This is a multi-functional e-commerce agent.")

tab1, tab2 = st.tabs(["ASIN Analysis", "Chat with Agent"])

with tab1:
    st.header("ASIN Analysis")
    st.info("This tool analyzes ASINs from a list or a CSV file.")
    
    st.subheader("1. Choose Input Method")
    input_method = st.radio("Select input method:", ("Paste ASINs", "Upload CSV file"))

    asins = []
    original_df = None

    if input_method == "Paste ASINs":
        asin_input = st.text_area("Paste one ASIN per line:", height=150, key="asin_input")
        if asin_input:
            asins = [asin.strip() for asin in asin_input.split('\n') if asin.strip()]
    else:
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        if uploaded_file:
            asin_column = st.text_input("Enter the name of the column containing ASINs:", "ASIN")
            try:
                original_df = pd.read_csv(uploaded_file)
                if asin_column in original_df.columns:
                    asins = original_df[asin_column].dropna().astype(str).tolist()
                else:
                    st.error(f"Column '{asin_column}' not found. Please check the column name.")
            except Exception as e:
                st.error(f"Error reading CSV: {e}")

    analyze_button = st.button("Analyze")

    st.subheader("2. Analysis Results")

    if analyze_button:
        if not asins:
            st.warning("Please provide ASINs to analyze.")
        else:
            st.write(f"Found {len(asins)} ASINs to analyze.")
            with st.spinner('Fetching data from Keepa and analyzing with AI...'):
                result_df = get_ai_analysis(asins)

            st.success("Analysis complete!")

            if result_df is not None and not result_df.empty:
                if original_df is not None:
                    # File upload workflow
                    st.write("### Analyzed Data:")
                    # Ensure the ASIN column in original_df is string type for merging
                    original_df[asin_column] = original_df[asin_column].astype(str)
                    merged_df = pd.merge(original_df, result_df, left_on=asin_column, right_on="ASIN", how="left")
                    # Drop the extra 'ASIN' column from the merge if it exists
                    if 'ASIN' in merged_df.columns and asin_column != 'ASIN':
                         merged_df = merged_df.drop(columns=['ASIN'])
                    st.dataframe(merged_df, use_container_width=True)

                    @st.cache_data
                    def convert_df_to_csv(df):
                        return df.to_csv(index=False).encode('utf-8')

                    csv = convert_df_to_csv(merged_df)

                    st.download_button(
                        label="Download Analyzed Data as CSV",
                        data=csv,
                        file_name='analyzed_products.csv',
                        mime='text/csv',
                    )
                else:
                    # Paste ASINs workflow
                    st.write("### Analysis Results:")
                    st.dataframe(result_df, use_container_width=True)
            else:
                st.error("Could not retrieve any data or analysis.")

with tab2:
    st.header("Chat with Agent")
    st.info("Ask the AI agent anything.")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("What is up?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)

        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                full_response = ""
                
                try:
                    chat_model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # Limit the history and map roles for the API
                    max_history = 10
                    history_to_send = st.session_state.messages[-max_history:]
                    
                    model_history = []
                    for msg in history_to_send:
                        role = "model" if msg["role"] == "assistant" else "user"
                        model_history.append({"role": role, "parts": [msg["content"]]})

                    # Use generate_content with the history
                    response = chat_model.generate_content(model_history, stream=True)

                    for chunk in response:
                        full_response += (chunk.text or "")
                        message_placeholder.markdown(full_response + "▌")
                    
                    if not full_response.strip():
                        full_response = "I'm sorry, I don't have a response for that."

                    message_placeholder.markdown(full_response)

                except Exception as e:
                    full_response = f"An error occurred: {e}"
                    message_placeholder.markdown(full_response)

        st.session_state.messages.append({"role": "assistant", "content": full_response})
