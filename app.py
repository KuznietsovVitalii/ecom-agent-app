import streamlit as st
import pandas as pd
import requests
import json
import time
from io import StringIO

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

# --- Keepa API Logic ---
def get_product_data(asins):
    url = "https://api.keepa.com/product"
    params = {
        "key": KEEPA_API_KEY,
        "domain": 1,  # 1 for .com (US)
        "asin": ",".join(asins),
        "stats": 90,  # Include 90-day average stats
        "offers": 20
    }
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while True:
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            status_text.success("Successfully fetched data from Keepa.")
            progress_bar.progress(100)
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                status_text.warning("Keepa rate limit hit. Waiting 60 seconds to retry...")
                for i in range(60):
                    time.sleep(1)
                    progress_bar.progress((i + 1) / 60)
                continue
            else:
                st.error(f"An unrecoverable error occurred with Keepa API: {e}")
                return None

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
                    message_placeholder.info(f"Found ASINs: {', '.join(asins_in_prompt)}. Fetching data from Keepa...")
                    keepa_data = get_product_data(asins_in_prompt)
                    if keepa_data and 'products' in keepa_data:
                        # For now, just show the raw JSON. This can be improved to be a table or a summary.
                        st.session_state.messages.append({"role": "assistant", "content": f"Here is the Keepa data for the requested ASINs:\n\n```json\n{json.dumps(keepa_data['products'], indent=2)}\n```"})
                        st.rerun()
                    else:
                        message_placeholder.error("Could not retrieve data from Keepa for the specified ASINs.")
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
                        current_user_message_text += f"

Uploaded CSV Data:
{st.session_state.uploaded_file_data}"

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