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

# File uploader for CSV
uploaded_file = st.file_uploader("Upload a CSV file for analysis", type="csv")

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
    if "uploaded_data" in st.session_state:
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