from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import os
from dotenv import load_dotenv
import logging
import urllib.parse

load_dotenv()
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        try:
            mongo_url = os.getenv("MONGO_URL")
            db_name = os.getenv("DATABASE_NAME", "ai_saas")
            
            if not mongo_url:
                raise ValueError("MONGO_URL not found in environment variables")
            
            # Connection settings for Atlas
            self.client = MongoClient(
                mongo_url,
                serverSelectionTimeoutMS=10000,  
                connectTimeoutMS=10000,
                socketTimeoutMS=45000,
            )
            
            # Verify connection
            self.client.admin.command('ping')
            self.db = self.client[db_name]
            
            # Create indexes for performance
            self._create_indexes()
            
            logger.info(f"✅ Connected to MongoDB Atlas: {db_name}")
            
        except ServerSelectionTimeoutError as e:
            logger.error(f"MongoDB Atlas connection timeout: {e}")
            logger.error("Check your IP whitelist in Atlas Network Access")
            raise
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
    
    def _create_indexes(self):
        """Create indexes for better query performance"""
        try:
            # Index for faster message queries
            self.db.messages.create_index([("user_id", 1), ("conversation_id", 1)])
            self.db.messages.create_index([("timestamp", -1)])
            
            # Index for conversations
            self.db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
            self.db.conversations.create_index([("id", 1)], unique=True)
            
            logger.info("✅ Database indexes created")
        except Exception as e:
            logger.warning(f"⚠️ Index creation warning: {e}")
    
    @property
    def users(self):
        return self.db["users"]
    
    @property
    def messages(self):
        return self.db["messages"]
    
    @property
    def conversations(self):
        return self.db["conversations"]

# Global instance
db = Database()