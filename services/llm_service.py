import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import datetime
import json
import streamlit as st
import time

class LLMService:
    def __init__(self, api_key, keepa_service):
        self.api_key = api_key
        self.keepa_service = keepa_service
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = self._setup_model()

    def _setup_model(self):
        system_instruction = """You are an expert e-commerce analyst and assistant. 
        You help users analyze Amazon products using Keepa data.
        
        TOOLS:
        1. `get_amazon_product_details(asin, domain_id)`: Use this to fetch REAL-TIME price, sales, and rating data for a product. 
           - ALWAYS use this if the user asks about a specific product (e.g., "How is B00... doing?", "Price of iPhone 13?").
           - If the user provides an ASIN, use it directly.
        2. `google_web_search(query)`: Use this for:
           - Getting the current date (query="current date").
           - Finding ASINs if the user only gives a product name (e.g., "Find ASIN for Sony WH-1000XM5").
        
        ANALYSIS RULES:
        - When analyzing sales, look at 'Avg Monthly Sales' and 'BSR' (Best Sellers Rank).
        - If data is missing, say so honestly.
        - Be concise but professional.
        """
        return genai.GenerativeModel(
            'gemini-1.5-flash-latest',
            tools=[self.google_web_search_tool, self.get_amazon_product_details_tool],
            system_instruction=system_instruction
        )

    # --- Tool Definitions ---
    def google_web_search_tool(self, query: str) -> str:
        """Performs a web search. Use for finding ASINs or checking current date."""
        pass 

    def get_amazon_product_details_tool(self, asin: str, domain_id: int = 1) -> dict:
        """Fetches detailed Keepa/Amazon data for a specific ASIN."""
        pass 

    # --- Tool Execution ---
    def _execute_tool(self, function_call):
        name = function_call.name
        args = function_call.args
        
        if name == "google_web_search_tool" or name == "google_web_search":
            query = args.get("query", "")
            # Simple mock for date, can be expanded
            if "date" in query.lower() or "today" in query.lower():
                return datetime.now().strftime("%Y-%m-%d")
            return f"Search functionality is limited. Current date is {datetime.now().strftime('%Y-%m-%d')}."
            
        elif name == "get_amazon_product_details_tool" or name == "get_amazon_product_details":
            return self.keepa_service.get_product_info(
                asins=args.get("asin"),
                domain_id=int(args.get("domain_id", 1)),
                stats_days=None,
                include_rating=True
            )
            
        return f"Error: Unknown tool '{name}'"

    def generate_response(self, messages, context_data=None):
        if not self.api_key:
            return "Gemini API Key is missing."

        # Build history for the model
        chat_history = []
        
        # Add context as a system-like user message at the start if exists
        if context_data:
            context_str = json.dumps(context_data)
            MAX_CONTEXT_CHARS = 30000 
            if len(context_str) > MAX_CONTEXT_CHARS:
                context_str = context_str[:MAX_CONTEXT_CHARS] + "\n... (truncated)"
            chat_history.append({
                "role": "user",
                "parts": [f"SYSTEM CONTEXT (Pre-loaded Data):\n{context_str}"]
            })
            chat_history.append({
                "role": "model",
                "parts": ["Understood. I will use this context for my analysis."]
            })

        # Convert Streamlit messages to Gemini format
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            content = msg["content"]
            
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict) and "data" in item:
                        # Image data
                        parts.append(genai.protos.Part(
                            inline_data=genai.protos.Blob(
                                mime_type=item["mime_type"],
                                data=item["data"]
                            )
                        ))
            
            if parts:
                chat_history.append({"role": role, "parts": parts})

        if not chat_history:
            return "Please ask a question."

        # Start chat session
        # If history is empty (first message), start_chat(history=[])
        # If history has items, we pass all but the last one as history, and send the last one.
        
        history_for_session = chat_history[:-1] if len(chat_history) > 1 else []
        last_message = chat_history[-1]

        chat = self.model.start_chat(history=history_for_session)

        try:
            response = chat.send_message(last_message["parts"])
            
            # Tool Loop (Simple 1-step recursion for now)
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                
                if part.function_call:
                    # st.toast(f"🤖 Agent is using tool: {part.function_call.name}...", icon="🛠️")
                    
                    tool_result = self._execute_tool(part.function_call)
                    
                    # Send result back
                    response = chat.send_message(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=part.function_call.name,
                                response={"result": tool_result}
                            )
                        )
                    )
            
            return response.text

        except Exception as e:
            return f"AI Error: {str(e)}"
