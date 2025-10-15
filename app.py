import streamlit as st
import pandas as pd
import requests
import json

st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent")

# --- API Key & Secrets Instructions ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    KEEPA_API_KEY = st.secrets["KEEPA_API_KEY"]
except FileNotFoundError:
    st.error("Secrets file not found. Please add your GEMINI_API_KEY and KEEPA_API_KEY to the Streamlit Cloud secrets.")
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


# --- Core Logic Function (Keepa related, currently not used in chat directly) ---
# This function is kept for future integration if needed, but not directly called by the chat agent yet.
# It would need to be adapted to be called by the agent based on user's request.
sales_tiers = {
    -1:0, 0: 50, 50: 100, 100: 200, 200: 300, 300: 400, 400: 500, 500: 600,
    600: 700, 700: 800, 800: 900, 900: 1000, 1000: 2000, 2000: 3000, 3000: 4000,
    4000: 5000, 5000: 6000, 6000: 7000, 7000: 8000, 8000: 9000, 9000: 10000,
    10000: 20000, 20000: 30000, 30000: 40000, 40000: 50000, 50000: 60000,
    60000: 70000, 70000: 80000, 80000: 90000, 90000:100000, 100000: 150000
}

def get_ai_analysis(asins):
    # This function is currently not directly used by the chat agent.
    # It would need to be adapted to be called by the agent based on user's request.
    st.warning("Keepa analysis function is not directly integrated into chat yet.")
    return None


# --- Chat with Agent ---
st.header("Chat with Keepa Expert Agent")
st.info("Upload a CSV file or ask the AI agent anything about e-commerce and Keepa data.")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# File uploader for CSV within the chat context
uploaded_file = st.file_uploader("Upload a CSV file for analysis", type="csv", key="chat_file_uploader")

# Process uploaded file if any
if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        st.session_state.uploaded_data = df.to_json(orient="records", indent=2)
        st.success("CSV file uploaded successfully!")
        st.session_state.messages.append({"role": "assistant", "content": "CSV file received. What would you like to analyze or ask about this data?"})
        # Display the first few rows of the uploaded CSV
        with st.expander("View uploaded CSV data"):
            st.dataframe(df.head())
        # Clear the uploaded file widget after processing to prevent re-processing on rerun
        uploaded_file = None # This might not visually clear the widget, but prevents re-reading
    except Exception as e:
        st.error(f"Error reading CSV file: {e}")

# Accept user input
if prompt := st.chat_input("What is up?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Construct the full prompt for the AI
    full_ai_prompt = "You are an expert e-commerce analyst with deep knowledge of Keepa data. "
    if "uploaded_data" in st.session_state and st.session_state.uploaded_data:
        full_ai_prompt += f"The user has provided the following CSV data for analysis: {st.session_state.uploaded_data}. "
    full_ai_prompt += f"The user's question is: {prompt}"

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        with st.spinner("Agent is thinking..."):
            message_placeholder = st.empty()
            full_response = ""
            
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
                headers = {'Content-Type': 'application/json'}
                
                # Limit the history and map roles for the API
                max_history = 10
                history_to_send = st.session_state.messages[-max_history:]
                
                model_history = []
                for msg in history_to_send:
                    role = "model" if msg["role"] == "assistant" else "user"
                    model_history.append({"role": role, "parts": [{"text": msg["content"]}]})

                # Add the current user prompt to the model history
                model_history.append({"role": "user", "parts": [{"text": full_ai_prompt}]})

                data = {"contents": model_history}
                
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()

                response_json = response.json()

                if 'candidates' not in response_json or not response_json['candidates']:
                    full_response = "I'm sorry, I don't have a response for that."
                else:
                    full_response = response_json['candidates'][0]['content']['parts'][0]['text']

                message_placeholder.markdown(full_response)

            except (requests.exceptions.RequestException, Exception) as e:
                full_response = f"An error occurred: {e}"
                if 'response' in locals():
                    full_response += f"\n\nRaw API Response: {response.text}"
                message_placeholder.markdown(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})