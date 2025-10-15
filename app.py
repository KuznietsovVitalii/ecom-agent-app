import streamlit as st
import pandas as pd
import requests
import json

st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent")

# --- API Key & Secrets Instructions ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    st.error("Secrets file not found. Please add your GEMINI_API_KEY to the Streamlit Cloud secrets.")
    st.info("""
        To add your secrets:
        1. Go to your app's dashboard on share.streamlit.io.
        2. Click on 'Settings'.
        3. Go to the 'Secrets' tab.
        4. Add your key in TOML format, like this:
           GEMINI_API_KEY = "your_gemini_key_here"
    """)
    st.stop()


# --- Core Logic Function ---
def get_ai_analysis_from_csv(df):
    """
    Gets a per-row AI analysis from Gemini for a DataFrame.
    Returns a DataFrame with the analysis.
    """
    # 1. Call Gemini for analysis
    prompt = f"""
    You are an expert e-commerce analyst.
    Analyze the following product data from a CSV file.
    For each row, provide a concise, one-sentence insight in a new 'analysis' field.
    Focus on whether the product seems promising or risky, based on its data.
    Return the analysis as a clean JSON array of objects, where each object has two keys: "row_index" and "analysis". Do not include any other text or formatting outside of the JSON array.

    Data:
    {df.to_json(orient="records", indent=2)}

    Example of desired output format:
    [
      {{
        "row_index": 0,
        "analysis": "This product seems promising due to its low price and good sales rank."
      }},
      {{
        "row_index": 1,
        "analysis": "This product might be risky due to its high price despite a good sales rank."
      }}
    ]
    """

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        response_json = response.json()
        
        if 'candidates' not in response_json or not response_json['candidates']:
            st.error("Failed to get analysis from AI: No candidates in response.")
            st.text("AI Response was:")
            st.json(response_json)
            return None

        if 'content' not in response_json['candidates'][0] or 'parts' not in response_json['candidates'][0]['content'] or not response_json['candidates'][0]['content']['parts']:
            st.error("Failed to get analysis from AI: No content in candidate.")
            st.text("AI Response was:")
            st.json(response_json)
            return None
            
        cleaned_response = response_json['candidates'][0]['content']['parts'][0]['text'].strip().replace('```json', '').replace('```', '')
        analysis_data = json.loads(cleaned_response)
        analysis_df = pd.DataFrame(analysis_data)
        
        return analysis_df

    except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
        st.error(f"Failed to get or parse analysis from AI. Error: {e}")
        if 'response' in locals():
            st.text("AI Response was:")
            st.text(response.text)
        return None


st.header("CSV File Analysis")
st.info("Upload a CSV file for AI analysis.")

uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)
        st.write("### Original Data:")
        st.dataframe(df)

        analyze_button = st.button("Analyze CSV with AI")

        if analyze_button:
            with st.spinner('Analyzing CSV data with AI...'):
                analysis_df = get_ai_analysis_from_csv(df)

            if analysis_df is not None and not analysis_df.empty:
                # Merge analysis back to original DataFrame
                # Assuming 'row_index' in analysis_df corresponds to df.index
                df_indexed = df.reset_index().rename(columns={'index': 'row_index'})
                merged_df = pd.merge(df_indexed, analysis_df, on="row_index", how="left")
                merged_df = merged_df.drop(columns=['row_index'])

                st.success("Analysis complete!")
                st.write("### Analyzed Data:")
                st.dataframe(merged_df)

                @st.cache_data
                def convert_df_to_csv(df_to_convert):
                    return df_to_convert.to_csv(index=False).encode('utf-8')

                csv = convert_df_to_csv(merged_df)

                st.download_button(
                    label="Download Analyzed Data as CSV",
                    data=csv,
                    file_name='analyzed_data.csv',
                    mime='text/csv',
                )
            else:
                st.error("Could not retrieve any analysis for the CSV data.")

    except Exception as e:
        st.error(f"Error reading or processing CSV file: {e}")
