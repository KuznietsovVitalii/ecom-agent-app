import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import datetime
import json
import streamlit as st

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
        You have access to tools to fetch real-time data. 
        Always use the 'get_amazon_product_details' tool when asked about a specific product's current data if you don't have it in context.
        Use 'google_web_search' for current dates or general web info.
        """
        return genai.GenerativeModel(
            'gemini-1.5-flash-latest',
            tools=[self.google_web_search_tool, self.get_amazon_product_details_tool],
            system_instruction=system_instruction
        )

    # --- Tool Definitions (for the model to see) ---
    def google_web_search_tool(self, query: str) -> str:
        """Use this ONLY when asked for today's date or similar real-time date/time questions."""
        pass # Implementation is handled in execution logic

    def get_amazon_product_details_tool(self, asin: str, domain_id: int = 1) -> dict:
        """Fetches detailed information for a given Amazon product ASIN. Use this tool if the user asks a question about a specific product and you don't have the information."""
        pass # Implementation is handled in execution logic

    # --- Tool Execution Logic ---
    def _execute_google_web_search(self, query: str) -> str:
        if "current date" in query.lower() or "today" in query.lower() or "date" in query.lower():
            return datetime.now().strftime("%Y-%m-%d")
        return f"This tool can only fetch the current date. It cannot perform a general web search for '{query}'."

    def _execute_get_amazon_product_details(self, asin: str, domain_id: int = 1) -> dict:
        if not asin or not isinstance(asin, str) or len(asin) < 10:
            return {"error": f"Invalid ASIN provided: '{asin}'. Please provide a valid 10-character ASIN."}
        
        # Use the injected keepa_service
        return self.keepa_service.get_product_info(
            asins=asin,
            domain_id=domain_id,
            stats_days=None,
            include_rating=True
        )

    def generate_response(self, messages, context_data=None):
        if not self.api_key:
            return "Gemini API Key is missing."

        # Prepare prompt
        final_prompt = []
        
        # Add context if available
        if context_data:
            context_str = json.dumps(context_data)
            MAX_CONTEXT_CHARS = 50000 
            if len(context_str) > MAX_CONTEXT_CHARS:
                context_str = context_str[:MAX_CONTEXT_CHARS] + "\n... (context truncated)"
            final_prompt.append(f"CONTEXT: The user has pre-loaded the following data. Use this for analysis:\n{context_str}\n\n")

        # Add chat history (simplified for now, just taking the last user message or full history if needed)
        # In this simplified version, we pass the full history as 'contents' to generate_content if we were using chat session,
        # but the original code used a list of parts.
        # Let's stick to the original approach: passing the last message + context.
        # Wait, the original code appended history to `messages` list and then constructed `final_prompt`.
        
        # We will assume 'messages' contains the history in a format we can use, 
        # but for `generate_content` with tools, it's often better to use `start_chat`.
        # However, to minimize changes to logic, I'll replicate the single-turn generation with history if possible,
        # OR just use the last message + context as the prompt.
        
        # The original code: `final_prompt = [context_prompt] + user_message_for_api`
        # It seems it was stateless per request regarding the model object, but passed history?
        # No, `user_message_for_api` was just the *current* prompt. History was stored in `st.session_state.messages` for display.
        # So the model only saw the *current* prompt + context. It didn't see previous turns?
        # Wait, `st.session_state.messages` is for UI.
        # `final_prompt` only included `context_prompt` and `user_message_for_api`.
        # So yes, it was stateless. I should probably improve this to include history, but let's stick to working logic first.
        
        last_user_message = messages[-1]['content'] # Assuming standard format
        # If content is list (text + image), handle it.
        
        current_prompt_parts = []
        if isinstance(last_user_message, list):
             current_prompt_parts.extend(last_user_message)
        else:
             current_prompt_parts.append(last_user_message)

        final_prompt.extend(current_prompt_parts)

        try:
            response = self.model.generate_content(final_prompt)
            
            if not response.candidates:
                return "I'm sorry, I couldn't generate a response. Please try again."
            
            candidate = response.candidates[0]
            if not candidate.content.parts:
                return "I'm sorry, I received an empty response."

            # Handle Function Call
            if candidate.content.parts[0].function_call:
                function_call = candidate.content.parts[0].function_call
                function_name = function_call.name
                function_args = {key: value for key, value in function_call.args.items()}
                
                tool_result = None
                if function_name == "google_web_search":
                    tool_result = self._execute_google_web_search(**function_args)
                elif function_name == "get_amazon_product_details":
                    tool_result = self._execute_get_amazon_product_details(**function_args)
                else:
                    tool_result = f"Error: Unknown tool '{function_name}'"

                # Send result back to model
                second_response = self.model.generate_content(
                    final_prompt + [
                        genai.protos.Part(function_call=function_call),
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=function_name,
                                response={"result": tool_result},
                            )
                        ),
                    ]
                )
                return second_response.text
            
            return response.text

        except Exception as e:
            return f"An unexpected error occurred with the AI model: {e}"
