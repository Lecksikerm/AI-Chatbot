import os
from dotenv import load_dotenv
import logging
from typing import List, Dict
import google.generativeai as genai

load_dotenv()
logger = logging.getLogger(__name__)

class Chatbot:
    def __init__(self):
        # 1. Setup API Key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        
        # 2. Define models to try (ordered by reliability)
        # Note: We omit 'models/' prefix as the SDK handles it
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite"
        ]
        
        self.model = None
        
        # 3. Connection Loop
        for model_name in models_to_try:
            try:
                logger.info(f"🔄 Attempting to connect to: {model_name}...")
                temp_model = genai.GenerativeModel(model_name)
                
                temp_model.generate_content("ping", generation_config={"max_output_tokens": 5})
                
                self.model = temp_model
                logger.info(f"✅ Successfully initialized: {model_name}")
                break 
            except Exception as e:
                logger.warning(f"' Model {model_name} failed: {str(e)[:100]}")
                continue
        
        if not self.model:
            raise Exception(" Critical Error: All Gemini models failed to initialize. Check your API key or Google AI Studio quota.")
        
        self.conversations = {}

    def ask_ai(self, message: str, user_id: str = None, conversation_id: str = None, history: List[Dict] = None):
        """
        Generates a response from Gemini while maintaining conversation context.
        """
        try:
            # 4. Construct Context from MongoDB History
            formatted_history = []
            if history:
                for msg in history[-10:]: 
                    formatted_history.append({"role": "user", "parts": [msg.get('user_message', '')]})
                    formatted_history.append({"role": "model", "parts": [msg.get('bot_reply', '')]})

            # 5. Initialize Chat Session
            chat_session = self.model.start_chat(history=formatted_history)
            
            # 6. Send Message
            response = chat_session.send_message(message)
            
            if not response.text:
                return " AI returned an empty response."
            
            return response.text
            
        except Exception as e:
            logger.error(f" AI Error: {e}")
            error_str = str(e)
            
            if "SAFETY" in error_str:
                return " Response blocked by AI safety filters."
            if "RECITATION" in error_str:
                return " Response blocked due to copyright/recitation filters."
            if "429" in error_str or "QUOTA" in error_str:
                return "API Rate limit reached. Please wait a moment."
                
            return f" Error generating response: {error_str[:150]}"

# Create a global chatbot instance
chatbot = Chatbot()

