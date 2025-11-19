import google.generativeai as genai
from datetime import datetime
import json

class LLMService:
    def __init__(self, api_key, keepa_service):
        self.api_key = api_key
        self.keepa_service = keepa_service
        if self.api_key:
            self.model = self._setup_model()

    def _setup_model(self):
        system_instruction = """You are an expert e-commerce analyst. 
        Use get_amazon_product_details(asin, domain_id) to fetch product data when asked.
        Use google_web_search(query) for current date or finding ASINs."""
        
        return genai.GenerativeModel(
            'gemini-flash-latest',  # Using the ORIGINAL model name from the working version
            tools=[self.google_web_search_tool, self.get_amazon_product_details_tool],
            system_instruction=system_instruction
        )

    def google_web_search_tool(self, query: str) -> str:
        """Get current date or search info."""
        pass 

    def get_amazon_product_details_tool(self, asin: str, domain_id: int = 1) -> dict:
        """Fetch Keepa data for ASIN."""
        pass 

    def _execute_tool(self, function_call):
        name = function_call.name
        args = function_call.args
        
        if "google_web_search" in name:
            query = args.get("query", "")
            if "date" in query.lower() or "today" in query.lower():
                return datetime.now().strftime("%Y-%m-%d")
            return f"Current date: {datetime.now().strftime('%Y-%m-%d')}"
            
        elif "get_amazon_product_details" in name:
            return self.keepa_service.get_product_info(
                asins=args.get("asin"),
                domain_id=int(args.get("domain_id", 1)),
                stats_days=None,
                include_rating=True
            )
            
        return f"Error: Unknown tool '{name}'"

    def generate_response(self, user_message, context_data=None):
        """Generate response for a single user message."""
        if not self.api_key:
            return "Gemini API Key is missing."

        prompt_parts = []
        
        # Add context if available
        if context_data:
            context_str = json.dumps(context_data)
            if len(context_str) > 50000:
                context_str = context_str[:50000] + "\n...(truncated)"
            prompt_parts.append(f"CONTEXT:\n{context_str}\n\n")

        # Add user message
        if isinstance(user_message, list):
            prompt_parts.extend(user_message)
        else:
            prompt_parts.append(user_message)

        try:
            response = self.model.generate_content(prompt_parts)
            
            # Handle function calls
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                
                if part.function_call:
                    tool_result = self._execute_tool(part.function_call)
                    
                    # Send result back
                    response = self.model.generate_content(
                        prompt_parts + [
                            genai.protos.Part(function_call=part.function_call),
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=part.function_call.name,
                                    response={"result": tool_result}
                                )
                            )
                        ]
                    )
            
            return response.text

        except Exception as e:
            return f"AI Error: {str(e)}"
