from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime

# Import models and dependencies
from ..models import (
    ConversationCreate, ConversationResponse, ConversationListResponse,
    ConversationHistoryResponse, Message, GetOrCreateConversation,
)
from ..database import MongoDBConversationManager
from ..dependencies import get_current_user

# Initialize router
router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    responses={404: {"description": "Not found"}},
)

# Create conversation endpoint
@router.post("", response_model=ConversationResponse)
async def create_conversation(conversation: ConversationCreate):
    try:
        # Get conversation_id from request if provided
        provided_id = conversation.conversation_id
        
        # Check if this ID exists in our database
        if provided_id and MongoDBConversationManager.get_conversation(provided_id):
            # Conversation exists, return it
            return ConversationResponse(
                conversation_id=provided_id,
                title=MongoDBConversationManager.get_conversation(provided_id).get("title", "Untitled"),
                description=MongoDBConversationManager.get_conversation(provided_id).get("description", ""),
                status="success",
                message="Existing conversation retrieved"
            )
        
        # Either ID wasn't provided or conversation doesn't exist
        # If ID was provided, use it, otherwise generate a new one
        conversation_id = provided_id if provided_id else str(uuid.uuid4())
        
        # Create the conversation
        title = conversation.title if conversation.title else "General Chat"
        description = conversation.description if conversation.description else "General conversation about Portuguese language"
        user_id = conversation.user_id if conversation.user_id else "default_user"
        
        MongoDBConversationManager.create_conversation(
            conversation_id=conversation_id,
            title=title,
            description=description,
            user_id=user_id
        )
        
        return ConversationResponse(
            conversation_id=conversation_id,
            title=title,
            description=description,
            status="success",
            message="Conversation created successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error creating conversation: {str(e)}"
        )

# Get conversation history endpoint
@router.get("/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(conversation_id: str, limit: int = Query(50, ge=1, le=100)):
    """Get conversation history with the specified ID"""
    try:
        # Get conversation data
        conversation = MongoDBConversationManager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail=f"Conversation with ID {conversation_id} not found")
        
        # Get conversation history
        messages = MongoDBConversationManager.get_conversation_history(conversation_id, limit)
        
        # Format messages for response
        formatted_messages = []
        for msg in messages:
            formatted_msg = Message(
                sender=msg.get("sender"),
                content=msg.get("content", ""),
                timestamp=msg.get("timestamp")
            )
            
            # Add optional fields if present
            if "id" in msg:
                formatted_msg.id = msg["id"]
            if "type" in msg:
                formatted_msg.type = msg["type"]
            if "payload" in msg:
                formatted_msg.payload = msg["payload"]
            
            formatted_messages.append(formatted_msg)
        
        # Create and return response
        return ConversationHistoryResponse(
            conversation_id=conversation_id,
            title=conversation.get("title", "Untitled"),
            description=conversation.get("description", ""),
            messages=formatted_messages
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation history: {str(e)}")

# List user's conversations
@router.get("", response_model=ConversationListResponse)
async def list_conversations(user_id: str = "default_user"):
    """List all conversations for a user"""
    try:
        # Get all conversations for the user from MongoDB
        from ..database import conversations_collection
        conversations = list(conversations_collection.find({"user_id": user_id}))
        
        # Format conversations for response
        formatted_conversations = []
        for conv in conversations:
            formatted_conversations.append(
                ConversationResponse(
                    conversation_id=conv.get("conversation_id"),
                    title=conv.get("title", "Untitled"),
                    description=conv.get("description", ""),
                    created_at=conv.get("created_at").isoformat() if "created_at" in conv else datetime.now().isoformat(),
                    updated_at=conv.get("updated_at").isoformat() if "updated_at" in conv else datetime.now().isoformat()
                )
            )
        
        return ConversationListResponse(conversations=formatted_conversations)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing conversations: {str(e)}")

# Get or create conversation endpoint
@router.post("/get-or-create", 
          response_model=ConversationHistoryResponse, 
          summary="Get or create conversation by ID",
          description="Get conversation if exists or create a new one with the provided ID")
async def get_or_create_conversation(conversation_data: GetOrCreateConversation):
    try:
        # Get the conversation ID from the request
        conversation_id = conversation_data.conversation_id
        
        # Check if this ID exists in MongoDB
        conversation = MongoDBConversationManager.get_conversation(conversation_id)
        
        if conversation:
            # Conversation exists, return its history
            messages = MongoDBConversationManager.get_conversation_history(conversation_id)
            return ConversationHistoryResponse(
                conversation_id=conversation_id,
                title=conversation.get("title", "Untitled"),
                description=conversation.get("description", ""),
                messages=messages
            )
        else:
            # Create a new conversation with the provided ID
            title = conversation_data.title
            description = conversation_data.description
            user_id = conversation_data.user_id
            
            MongoDBConversationManager.create_conversation(
                conversation_id=conversation_id,
                title=title,
                description=description,
                user_id=user_id
            )
            
            return ConversationHistoryResponse(
                conversation_id=conversation_id,
                title=title,
                description=description,
                messages=[]
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing conversation: {str(e)}"
        ) 