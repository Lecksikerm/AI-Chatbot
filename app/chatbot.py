import os
from dotenv import load_dotenv
import logging
from typing import List, Dict, Optional
import google.generativeai as genai
import PIL.Image as Image
import io

load_dotenv()
logger = logging.getLogger(__name__)

class Chatbot:
    def __init__(self):
        self.model = None
        self.is_available = False
        
        # Setup API Key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found - chatbot will be unavailable")
            return
        
        genai.configure(api_key=api_key)
        
        # Define models to try
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite"
        ]
        
        # Connection Loop
        for model_name in models_to_try:
            try:
                logger.info(f"🔄 Attempting to connect to: {model_name}...")
                temp_model = genai.GenerativeModel(model_name)
                
                # Test with minimal request
                temp_model.generate_content("ping", generation_config={"max_output_tokens": 5})
                
                self.model = temp_model
                self.is_available = True
                logger.info(f"✅ Successfully initialized: {model_name}")
                break 
            except Exception as e:
                logger.warning(f"Model {model_name} failed: {str(e)[:100]}")
                continue
        
        if not self.model:
            logger.error("⚠️ All Gemini models failed - chatbot unavailable")
            # Don't raise exception - allow app to start

    def ask_ai(self, message: str, user_id: str = None, conversation_id: str = None, 
               history: List[Dict] = None, files: Optional[List[Dict]] = None):
        """Generates a response from Gemini with optional file support."""
        
        if not self.is_available or not self.model:
            return "⚠️ AI service is temporarily unavailable. Please try again later or contact support."
        
        try:
            # Build content parts
            content_parts = [message]
            
            # Process files if provided
            if files:
                for file_info in files:
                    if file_info["type"] == "image":
                        image = Image.open(io.BytesIO(file_info["content"]))
                        content_parts.append(image)
                    elif file_info["type"] == "document":
                        content_parts.append(f"\n[Document attached: {file_info['filename']}]")
            
            # Construct Context from History
            formatted_history = []
            if history:
                for msg in history[-10:]: 
                    formatted_history.append({"role": "user", "parts": [msg.get('user_message', '')]})
                    formatted_history.append({"role": "model", "parts": [msg.get('bot_reply', '')]})

            # Initialize Chat Session
            chat_session = self.model.start_chat(history=formatted_history)
            
            # Send Message
            response = chat_session.send_message(content_parts)
            
            if not response.text:
                return "AI returned an empty response."
            
            return response.text
            
        except Exception as e:
            logger.error(f"AI Error: {e}")
            error_str = str(e)
            
            if "SAFETY" in error_str:
                return "Response blocked by AI safety filters."
            if "RECITATION" in error_str:
                return "Response blocked due to copyright/recitation filters."
            if "429" in error_str or "QUOTA" in error_str or "exceeded" in error_str:
                return "⚠️ AI service quota exceeded. Please check billing or try again later."
                
            return f"Error generating response: {error_str[:150]}"

chatbot = Chatbot()