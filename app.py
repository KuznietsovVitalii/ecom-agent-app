import streamlit as st
import requests
import json

st.title("Gemini Chat")

# Get the Gemini API key from the secrets
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    st.error("Secrets file not found. Please add your GEMINI_API_KEY to the Streamlit Cloud secrets.")
    st.stop()

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
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
                headers = {'Content-Type': 'application/json'}
                
                # Limit the history and map roles for the API
                max_history = 10
                history_to_send = st.session_state.messages[-max_history:]
                
                model_history = []
                for msg in history_to_send:
                    role = "model" if msg["role"] == "assistant" else "user"
                    model_history.append({"role": role, "parts": [{"text": msg["content"]}]})

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