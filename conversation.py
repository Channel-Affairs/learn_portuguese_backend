from typing import List, Dict, Any, Optional
import json
import time
from datetime import datetime
import uuid
from database import MongoDBConversationManager

class ConversationManager:
    """
    Legacy conversation manager - now delegates to MongoDB implementation.
    Kept for backward compatibility.
    """
    
    def create_conversation(self, user_id: str = "default_user", title: str = "General Chat", description: str = "General conversation about Portuguese language") -> str:
        """Create a new conversation and return the ID"""
        conversation_id = str(uuid.uuid4())
        return MongoDBConversationManager.create_conversation(
            conversation_id=conversation_id,
            title=title,
            description=description,
            user_id=user_id
        )
    
    def add_message(self, conversation_id: str, message: Dict[str, Any]) -> bool:
        """Add a message to the conversation"""
        return MongoDBConversationManager.add_message(conversation_id, message)
    
    def get_conversation_history(self, conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the conversation history"""
        return MongoDBConversationManager.get_conversation_history(conversation_id, limit)
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get a conversation by ID"""
        return MongoDBConversationManager.get_conversation(conversation_id)
    
    def update_state(self, conversation_id: str, update_data: Dict[str, Any]) -> bool:
        """Update the conversation state"""
        return MongoDBConversationManager.update_state(conversation_id, update_data)
    
    def get_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get the conversation state"""
        return MongoDBConversationManager.get_state(conversation_id)
    
    def record_answer_result(self, conversation_id: str, question_id: str, 
                           was_correct: bool, user_answer: Any, difficulty: str) -> bool:
        """Record a question answer result"""
        return MongoDBConversationManager.record_answer_result(
            conversation_id=conversation_id,
            question_id=question_id,
            was_correct=was_correct,
            user_answer=user_answer,
            difficulty=difficulty
        )

# Create singleton instance
conversation_manager = ConversationManager() 