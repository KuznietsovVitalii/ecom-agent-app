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
    Fetches data from Keepa and gets an AI analysis from Gemini.
    """
    # 1. Configure APIs
    try:
        api = keepa.Keepa(KEEPA_API_KEY)
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"Failed to configure APIs. Please check your keys. Error: {e}")
        return None, None

    # 2. Fetch data from Keepa
    try:
        products = api.query(asins, stats=90) # Get 90-day stats
    except Exception as e:
        st.error(f"Failed to fetch data from Keepa. Error: {e}")
        return None, None

    if not products:
        st.warning("No product data returned from Keepa for the given ASINs.")
        return None, None

    # 3. Format Keepa data for the AI
    product_data_for_ai = []
    raw_data_for_table = []
    for product in products:
        # Ensure data exists before accessing
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

    # 4. Call Gemini for analysis
    prompt = f"""
    You are an expert e-commerce analyst.
    Analyze the following product data retrieved from Keepa.
    Provide a concise, insightful summary for a business owner.
    Focus on which products seem promising, which are risky, and why, based on sales rank and price.
    Do not just list the data; provide actionable insights.

    Data:
    {json.dumps(product_data_for_ai, indent=2)}
    """

    try:
        response = model.generate_content(prompt)
        ai_summary = response.text
    except Exception as e:
        st.error(f"Failed to get analysis from AI. Error: {e}")
        return None, pd.DataFrame(raw_data_for_table) # Return raw data even if AI fails

    # 5. Return results
    df = pd.DataFrame(raw_data_for_table)
    return ai_summary, df

# --- Streamlit UI ---
st.info("This app analyzes ASIN data from Keepa using an AI agent.")

st.subheader("1. Input Your ASINs")
asin_input = st.text_area("Paste one ASIN per line:", height=150, key="asin_input")

analyze_button = st.button("Analyze ASINs")

st.subheader("2. Analysis Results")

if analyze_button:
    if asin_input.strip() == "":
        st.error("Please paste at least one ASIN.")
    else:
        # Split by newline and remove any empty strings
        asins = [asin.strip() for asin in asin_input.split('\n') if asin.strip()]
        st.write(f"Found {len(asins)} ASINs to analyze.")

        with st.spinner('Fetching data from Keepa and analyzing with AI...'):
            ai_summary, data_df = get_ai_analysis(asins)

        if ai_summary:
            st.success("Analysis complete!")
            st.write("### AI-Generated Summary:")
            st.markdown(ai_summary) # Use markdown to render formatting from the AI
        
        if data_df is not None and not data_df.empty:
            st.write("### Raw Data Table:")
            st.dataframe(data_df, use_container_width=True)
        elif ai_summary is None:
            st.error("Could not retrieve any data or analysis.")
