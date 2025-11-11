import streamlit as st
import requests
import pandas as pd
import json
import io
import PyPDF2
import uuid
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool

# --- Configuration ---
st.set_page_config(layout="wide")
st.title("E-commerce Analysis Agent")

# --- API Keys ---
# It's recommended to use st.secrets for production
KEEPA_API_KEY = "icj30t3ms9osic264u5e1cqed0a2gl1gh33jb5k1eq0qmeo462qnfhb2b86rrfms" # From memory
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE") # Replace with your key or use secrets

if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
    st.error("Please provide your Gemini API key in the code or using Streamlit secrets.")

genai.configure(api_key=GEMINI_API_KEY)

# --- Keepa API Logic ---
KEEPA_BASE_URL = 'https://api.keepa.com'

def get_token_status(api_key: str):
    """Checks the status of your Keepa API token."""
    try:
        response = requests.get(f"{KEEPA_BASE_URL}/token", params={'key': api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def get_product_info(asins: str, domain_id: int = 1):
    """
    Fetches product information from Keepa for a list of ASINs.
    
    Args:
        asins: A comma-separated string of ASINs.
        domain_id: The Amazon domain ID (e.g., 1 for .com).
    """
    if isinstance(asins, list):
        asins = ','.join(asins)
        
    try:
        response = requests.get(
            f"{KEEPA_BASE_URL}/product",
            params={'key': KEEPA_API_KEY, 'domain': domain_id, 'asin': asins, 'stats': 90, 'history': 0}
        )
        response.raise_for_status()
        # We return the JSON string directly as the model expects that
        return json.dumps(response.json())
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})

# --- Google Search Tool ---
def google_search(query: str):
    """
    Performs a Google search for the given query.
    
    Args:
        query: The search query.
    """
    # This is a placeholder for the actual tool call.
    # The Gemini CLI environment will intercept this and execute the real search.
    return f"Performing Google search for: {query}"

# --- Gemini Model and Tools ---
tools = [
    Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name='get_product_info',
                description='Fetches product information from Keepa for a list of ASINs.',
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        'asins': genai.protos.Schema(type=genai.protos.Type.STRING, description='A comma-separated string of ASINs.'),
                        'domain_id': genai.protos.Schema(type=genai.protos.Type.INTEGER, description='The Amazon domain ID (e.g., 1 for .com).')
                    },
                    required=['asins']
                )
            ),
            genai.protos.FunctionDeclaration(
                name='google_search',
                description='Performs a Google search.',
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        'query': genai.protos.Schema(type=genai.protos.Type.STRING, description='The search query.')
                    },
                    required=['query']
                )
            )
        ]
    )
]

model = genai.GenerativeModel(
    model_name='gemini-1.5-flash-latest',
    generation_config=GenerationConfig(temperature=0.2),
    tools=tools
)

# --- Streamlit UI ---
tab1, tab2 = st.tabs(["Keepa Tools", "Chat with Agent"])

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

with tab1:
    st.header("Keepa Tools")
    st.write("Direct access to Keepa API functions. Load data here to analyze it in the chat.")

    with st.expander("Check API Token Status"):
        if st.button("Check Tokens"):
            with st.spinner("Checking..."):
                status = get_token_status(KEEPA_API_KEY)
                if "error" in status:
                    st.error(f"Error: {status['error']}")
                else:
                    st.success(f"Tokens remaining: {status.get('tokensLeft')}")
                    st.json(status)

    with st.expander("Product Lookup", expanded=True):
        asins_input = st.text_input("Enter ASIN(s) (comma-separated)", "B00NLLUMOE,B07W7Q3G5R")
        domain_options = {'USA (.com)': 1, 'Germany (.de)': 3, 'UK (.co.uk)': 2, 'Canada (.ca)': 4, 'France (.fr)': 5, 'Spain (.es)': 6, 'Italy (.it)': 7, 'Japan (.co.jp)': 8, 'Mexico (.com.mx)': 11}
        selected_domain = st.selectbox("Amazon Domain", options=list(domain_options.keys()), index=0)
        
        if st.button("Get Product Info"):
            with st.spinner("Fetching product data..."):
                domain_id = domain_options[selected_domain]
                # We get a JSON string back
                product_data_str = get_product_info(asins_input, domain_id)
                product_data = json.loads(product_data_str)

                if "error" in product_data:
                    st.error(f"Error: {product_data['error']}")
                elif not product_data.get('products'):
                    st.warning("No products found for the given ASINs.")
                else:
                    st.success("Data fetched successfully!")
                    st.session_state.keepa_data = product_data.get('products')
                    st.write("Data is now available in the chat agent for analysis.")
                    st.json(st.session_state.keepa_data)

with tab2:
    st.header("Chat with Agent")

    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help you with your e-commerce analysis today?"}]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask the agent..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                message_placeholder = st.empty()
                
                try:
                    chat = model.start_chat()
                    response = chat.send_message(prompt)
                    
                    while response.candidates[0].content.parts[0].function_call.name:
                        function_call = response.candidates[0].content.parts[0].function_call
                        function_name = function_call.name
                        args = {key: value for key, value in function_call.args.items()}
                        
                        if function_name == "get_product_info":
                            tool_result = get_product_info(**args)
                        elif function_name == "google_search":
                            # This is where the CLI's google_web_search would be called
                            # For now, we'll just return a placeholder
                            tool_result = google_search(**args)
                        else:
                            raise ValueError(f"Unknown function call: {function_name}")

                        response = chat.send_message(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=function_name,
                                    response={'result': tool_result}
                                )
                            )
                        )

                    final_response = response.candidates[0].content.parts[0].text
                    message_placeholder.markdown(final_response)
                    st.session_state.messages.append({"role": "assistant", "content": final_response})

                except Exception as e:
                    error_message = f"An error occurred: {e}"
                    message_placeholder.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})
