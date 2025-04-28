import os
from pymongo import MongoClient
from pymongo.collection import Collection
from datetime import datetime
from typing import Dict, Any, List, Optional
import json
from bson import ObjectId
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection string
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://zainabkhaliq:2pKL3mJgeMsw0HEE@cluster0.qlzi1.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
print(f"Connecting to MongoDB with URI: {MONGO_URI[:60]}...")

# JSON encoder for MongoDB ObjectId
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

# Database client
try:
    print("Attempting to connect to MongoDB...")
    client = MongoClient(MONGO_URI)
    # Test the connection by accessing server info
    server_info = client.server_info()
    print(f"Successfully connected to MongoDB. Server version: {server_info.get('version', 'unknown')}")
    db = client["test"]
    print(f"Using database: test")
except Exception as e:
    print(f"Error connecting to MongoDB: {str(e)}")
    # Provide a fallback in-memory implementation for testing
    print("Using fallback in-memory data store")
    from conversation import conversation_manager
    
    # Mock implementation for testing without MongoDB
    class MockDB:
        def __init__(self):
            self.collections = {}
        
        def __getitem__(self, key):
            if key not in self.collections:
                self.collections[key] = MockCollection(key)
            return self.collections[key]
    
    class MockCollection:
        def __init__(self, name):
            self.name = name
            self.data = []
        
        def insert_one(self, doc):
            self.data.append(doc)
            return type('obj', (object,), {'inserted_id': len(self.data)})
        
        def insert_many(self, docs):
            for doc in docs:
                self.insert_one(doc)
        
        def find_one(self, query, projection=None):
            for doc in self.data:
                match = True
                for k, v in query.items():
                    if k not in doc or doc[k] != v:
                        match = False
                        break
                if match:
                    return doc
            return None
        
        def find(self, query=None, projection=None):
            if query is None:
                return self.data
            
            results = []
            for doc in self.data:
                match = True
                for k, v in query.items():
                    if k not in doc or doc[k] != v:
                        match = False
                        break
                if match:
                    results.append(doc)
            
            return MockCursor(results)
        
        def update_one(self, query, update, upsert=False):
            for i, doc in enumerate(self.data):
                match = True
                for k, v in query.items():
                    if k not in doc or doc[k] != v:
                        match = False
                        break
                if match:
                    # Process the update operation
                    if "$set" in update:
                        for k, v in update["$set"].items():
                            doc[k] = v
                    if "$push" in update:
                        for k, v in update["$push"].items():
                            if k not in doc:
                                doc[k] = []
                            doc[k].append(v)
                    self.data[i] = doc
                    return type('obj', (object,), {'modified_count': 1})
            
            # If we get here, no document was updated
            return type('obj', (object,), {'modified_count': 0})
        
        def count_documents(self, query):
            count = 0
            for doc in self.data:
                match = True
                for k, v in query.items():
                    if k not in doc or doc[k] != v:
                        match = False
                        break
                if match:
                    count += 1
            return count
        
        def create_index(self, field, unique=False):
            # Mock implementation, doesn't actually create an index
            pass
    
    class MockCursor:
        def __init__(self, data):
            self.data = data
        
        def sort(self, field, direction):
            # Mock implementation, doesn't actually sort
            return self
        
        def __iter__(self):
            return iter(self.data)
        
        def __list__(self):
            return list(self.data)
    
    # Create mock DB
    db = MockDB()
    client = None

# Collections
conversations_collection = db["conversations"]
messages_collection = db["messages"]
users_collection = db["users"]

# Ensure indexes for performance
conversations_collection.create_index("conversation_id", unique=True)
messages_collection.create_index("conversation_id")

# Hardcoded user for now
def ensure_hardcoded_user_exists():
    """Ensure the hardcoded user exists in the database"""
    if users_collection.count_documents({"username": "default_user"}) == 0:
        users_collection.insert_one({
            "username": "default_user",
            "display_name": "Default User",
            "created_at": datetime.now()
        })

# Initialize database with basic data
def initialize_db():
    """Initialize the database with required data"""
    ensure_hardcoded_user_exists()

# Conversation operations
class MongoDBConversationManager:
    @staticmethod
    def create_conversation(conversation_id: str, title: str, description: str, user_id: str = "default_user") -> str:
        """Create a new conversation in MongoDB"""
        conversation = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "title": title,
            "description": description,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "state": {
                "current_topic": None,
                "difficulty_level": "medium",
                "correct_answers": 0,
                "incorrect_answers": 0,
                "question_history": []
            }
        }
        
        # Insert the conversation document
        conversations_collection.insert_one(conversation)
        
        return conversation_id
    
    @staticmethod
    def add_message(conversation_id: str, message: Dict[str, Any]) -> bool:
        """Add a message to the conversation"""
        # Update conversation updated_at time
        conversations_collection.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"updated_at": datetime.now()}}
        )
        
        # Add the message
        message_doc = {
            "conversation_id": conversation_id,
            "timestamp": datetime.now(),
            **message
        }
        
        messages_collection.insert_one(message_doc)
        return True
    
    @staticmethod
    def get_conversation_history(conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the conversation history for a specific conversation"""
        # Find messages for the conversation, sorted by timestamp
        messages = list(messages_collection.find(
            {"conversation_id": conversation_id},
            {"_id": 0}  # Exclude MongoDB _id
        ).sort("timestamp", 1))  # Sort by timestamp ascending
        
        # Return the most recent messages up to the limit
        return messages[-limit:] if len(messages) > limit else messages
    
    @staticmethod
    def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get a conversation by ID"""
        conversation = conversations_collection.find_one(
            {"conversation_id": conversation_id},
            {"_id": 0}  # Exclude MongoDB _id
        )
        
        return conversation
    
    @staticmethod
    def update_state(conversation_id: str, update_data: Dict[str, Any]) -> bool:
        """Update the conversation state"""
        result = conversations_collection.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "updated_at": datetime.now(),
                    **{f"state.{key}": value for key, value in update_data.items()}
                }
            }
        )
        
        return result.modified_count > 0
    
    @staticmethod
    def get_state(conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get the current state of a conversation"""
        conversation = conversations_collection.find_one(
            {"conversation_id": conversation_id},
            {"state": 1, "_id": 0}
        )
        
        return conversation.get("state") if conversation else None
    
    @staticmethod
    def record_answer_result(conversation_id: str, question_id: str, 
                           was_correct: bool, user_answer: Any, difficulty: str) -> bool:
        """Record the result of a user answering a question"""
        # Create question result document
        question_result = {
            "question_id": question_id,
            "timestamp": datetime.now(),
            "was_correct": was_correct,
            "user_answer": user_answer,
            "difficulty": difficulty
        }
        
        # Get current state
        state = MongoDBConversationManager.get_state(conversation_id)
        if not state:
            return False
        
        # Update counts
        correct_answers = state.get("correct_answers", 0)
        incorrect_answers = state.get("incorrect_answers", 0)
        
        if was_correct:
            correct_answers += 1
        else:
            incorrect_answers += 1
        
        # Add question to history and update counts
        result = conversations_collection.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "updated_at": datetime.now(),
                    "state.correct_answers": correct_answers,
                    "state.incorrect_answers": incorrect_answers
                },
                "$push": {"state.question_history": question_result}
            }
        )
        
        # Adapt difficulty based on performance
        MongoDBConversationManager._adapt_difficulty(conversation_id)
        
        return result.modified_count > 0
    
    @staticmethod
    def _adapt_difficulty(conversation_id: str) -> None:
        """Adapt the difficulty level based on user performance"""
        state = MongoDBConversationManager.get_state(conversation_id)
        if not state:
            return
        
        # Analyze recent performance (last 5 questions)
        question_history = state.get("question_history", [])
        recent_results = question_history[-5:] if len(question_history) >= 5 else question_history
        
        if len(recent_results) < 3:
            return  # Need more data to adjust
        
        correct_count = sum(1 for result in recent_results if result.get('was_correct', False))
        accuracy_rate = correct_count / len(recent_results)
        
        # Adjust difficulty based on accuracy
        current_difficulty = state.get('difficulty_level', 'medium')
        new_difficulty = current_difficulty
        
        if accuracy_rate > 0.8 and current_difficulty == 'easy':
            new_difficulty = 'medium'
        elif accuracy_rate > 0.8 and current_difficulty == 'medium':
            new_difficulty = 'hard'
        elif accuracy_rate < 0.4 and current_difficulty == 'hard':
            new_difficulty = 'medium'
        elif accuracy_rate < 0.4 and current_difficulty == 'medium':
            new_difficulty = 'easy'
        
        # Update difficulty if changed
        if new_difficulty != current_difficulty:
            conversations_collection.update_one(
                {"conversation_id": conversation_id},
                {"$set": {"state.difficulty_level": new_difficulty}}
            )

# Initialize the database on module import
initialize_db()

# MongoDB conversation manager instance to replace the in-memory one
mongodb_conversation_manager = MongoDBConversationManager() 