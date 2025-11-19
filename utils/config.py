import streamlit as st

def load_api_keys():
    """
    Loads API keys from Streamlit secrets or session state.
    Returns a dictionary with keys.
    """
    keys = {}
    
    # Try loading from secrets
    try:
        keys["GEMINI_API_KEY"] = st.secrets.get("GEMINI_API_KEY")
        keys["KEEPA_API_KEY"] = st.secrets.get("KEEPA_API_KEY")
    except FileNotFoundError:
        pass

    # Fallback to sidebar inputs if not found (handled in sidebar UI, but we check here)
    if not keys.get("GEMINI_API_KEY") and "gemini_api_key_local" in st.session_state:
        keys["GEMINI_API_KEY"] = st.session_state["gemini_api_key_local"]
        
    if not keys.get("KEEPA_API_KEY") and "keepa_api_key_local" in st.session_state:
        keys["KEEPA_API_KEY"] = st.session_state["keepa_api_key_local"]
        
    return keys
