import streamlit as st

def render_sidebar():
    st.sidebar.header("Configuration")
    
    # API Key Status
    keys_configured = True
    if not st.secrets.get("GEMINI_API_KEY"):
        st.sidebar.warning("Gemini API Key missing in secrets.")
        st.sidebar.text_input("Gemini API Key", type="password", key="gemini_api_key_local")
        keys_configured = False
    
    if not st.secrets.get("KEEPA_API_KEY"):
        st.sidebar.warning("Keepa API Key missing in secrets.")
        st.sidebar.text_input("Keepa API Key", type="password", key="keepa_api_key_local")
        keys_configured = False
        
    if keys_configured:
        st.sidebar.success("API Keys loaded from secrets.")

    st.sidebar.divider()
    
    if st.sidebar.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()
        
    st.sidebar.info("v2.0 - Refactored Architecture")
