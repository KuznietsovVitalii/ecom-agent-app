import streamlit as st
from services.llm_service import LLMService

def render_chat_interface(llm_service: LLMService):
    st.header("Autonomous E-commerce Agent")
    st.info("Ask about a product by ASIN, and the agent will fetch the data itself if needed.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if isinstance(message["content"], list):
                for part in message["content"]:
                    if isinstance(part, str): st.markdown(part)
                    elif isinstance(part, dict) and "data" in part: st.image(part["data"])
            else:
                st.markdown(message["content"])

    # Chat Input
    if prompt := st.chat_input("e.g., 'What is the rating for B00NLLUMOE?'", accept_file=True, file_type=["jpg", "jpeg", "png"]):
        
        user_message_for_history = []
        user_message_for_api = [] # Simplified for now, assuming text mostly
        
        if prompt.text:
            user_message_for_history.append(prompt.text)
            user_message_for_api.append(prompt.text)
            
        if prompt.files:
            for uploaded_file in prompt.files:
                image_bytes = uploaded_file.getvalue()
                # For history display
                user_message_for_history.append({"mime_type": uploaded_file.type, "data": image_bytes})
                # For API (Gemini expects specific format)
                user_message_for_api.append({"mime_type": uploaded_file.type, "data": image_bytes})
        
        # Add to history
        st.session_state.messages.append({"role": "user", "content": user_message_for_history})
        
        # Display user message immediately
        with st.chat_message("user"):
             for part in user_message_for_history:
                if isinstance(part, str): st.markdown(part)
                elif isinstance(part, dict) and "data" in part: st.image(part["data"])

        # Generate Response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Determine context (if any Keepa data was manually fetched)
                context_data = st.session_state.get('keepa_data')
                
                # Call LLM Service
                # We pass the last message content for now as per simplified logic
                response_text = llm_service.generate_response(
                    messages=[{"role": "user", "content": user_message_for_api}], 
                    context_data=context_data
                )
                
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
