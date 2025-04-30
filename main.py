from fastapi import FastAPI, HTTPException, Depends, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import os
from dotenv import load_dotenv
import json
import uuid
from datetime import datetime, timedelta
from passlib.context import CryptContext
from pydantic import BaseModel
from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import models and question generator
from models import (
    MessageSenders, ResponseType, QuestionTypes, DifficultyLevel,
    TextResponse, MultipleChoiceQuestion, FillInTheBlankQuestion,
    QuestionResponse, AIChatResponse, UserChatRequest,
   ProcessMessage
)
from question_generator import QuestionGenerator
# Use MongoDB conversation manager
from database import MongoDBConversationManager, initialize_db

# Import auth router
from routers.auth import router as auth_router
from routers.conversations import router as conversations_router
from routers.user import router as user_router

from dependencies import create_openai_completion
# Load environment variables
load_dotenv()

# Set MongoDB connection string from environment or use default
mongodb_uri = os.getenv("MONGO_URI", "mongodb+srv://zainabkhaliq:2pKL3mJgeMsw0HEE@cluster0.qlzi1.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
print(f"Using MongoDB URI: {mongodb_uri[:30]}...")

# Initialize the database with default data
initialize_db()

# We'll use a proper OpenAI client function with error handling
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    print("WARNING: OpenAI API key not found in environment variables. API calls will fail.")

# Initialize FastAPI app
app = FastAPI(
    title="Portagees Chat API", 
    description="API for the Portagees language learning chat application",
    version="1.0.0"
)

# Include the auth router
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(user_router)

# Configure security scheme for Swagger UI
security_scheme = HTTPBearer(
    description="Enter 'Bearer your-token' to authenticate",
    auto_error=False
)

# Add security scheme to OpenAPI
app.swagger_ui_init_oauth = {
    "usePkceWithAuthorizationCodeGrant": True,
    "useBasicAuthenticationWithAccessCodeGrant": True
}

# Add security definitions to OpenAPI schema
app.openapi_schema = None  # Reset schema so it's regenerated with our modifications

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # Get the original openapi schema
    openapi_schema = FastAPI.openapi(app)
    
    # Add security scheme component
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    
    openapi_schema["components"]["securitySchemes"]["Bearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your JWT token in the format: Bearer your-token"
    }
    
    # Add global security requirement
    openapi_schema["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize question generator
question_generator = QuestionGenerator(openai_api_key)

# Counter for message IDs
message_counter = 0

# Helper function to get next message ID
def get_next_message_id():
    global message_counter
    message_counter += 1
    return message_counter

# Function to check if a query is app-related
def is_app_related_query(query: str) -> bool:
    """
    Check if query is related to Portuguese language learning.
    Short responses like "yes", "no", "maybe" are considered app-related
    as they could be answers to previous questions in conversation.
    """
    # Common short responses should be considered app-related
    # as they're likely responses to previous conversation
    short_responses = [
        "yes", "no", "maybe", "ok", "okay", "sure", 
        "thanks", "thank you", "correct", "incorrect",
        "i do", "i don't", "i can", "i can't", "i cannot",
        "sim", "não", "obrigado", "obrigada", "hello", "hi", "hey"
    ]
    
    query_lower = query.lower().strip()
    
    # If it's a very short answer, consider it app-related
    if query_lower in short_responses or len(query_lower.split()) <= 3:
        return True
    
    # Portuguese language related keywords
    portuguese_keywords = [
        "portuguese", "portugal", "learn", "language", "speak", "words", 
        "grammar", "vocabulary", "phrase", "sentence", "conjugate", "verb",
        "noun", "pronoun", "translation", "meaning", "say", "pronounce"
    ]
    
    # Check if any of the keywords are in the query
    for keyword in portuguese_keywords:
        if keyword in query_lower:
            return True
    
    return False

# Function to get conversation context
async def get_conversation_context(conversation_id: Optional[str]) -> List[Dict[str, Any]]:
    """Get conversation history to provide context for OpenAI"""
    if not conversation_id:
        return []
    
    # Get conversation history from MongoDB
    conversation_history = MongoDBConversationManager.get_conversation_history(conversation_id)
    if not conversation_history:
        return []
    
    # Format conversation history for OpenAI
    context = []
    for message in conversation_history:
        if message.get("sender") == MessageSenders.USER:
            context.append({
                "role": "user",
                "content": message.get("content", "")
            })
        elif message.get("sender") == MessageSenders.AI:
            # For AI messages, we need to extract the full text from payload if available
            content = message.get("content", "")
            if message.get("payload") and message.get("payload").get("text"):
                content = message.get("payload").get("text")
            
            context.append({
                "role": "assistant",
                "content": content
            })
    
    return context
# Updated get_current_user to use the security scheme
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    authorization: Optional[str] = Header(None)
):
    """
    Authenticate and return the current user based on the JWT token.
    Now accepts tokens from both the HTTPBearer security scheme and Header.
    """
    
    # Try to get token from security scheme first (Swagger UI's Authorization)
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    # Otherwise try the Authorization header
    elif authorization:
        print(f"Authorization header found: {authorization}")
        try:
            scheme, token_value = authorization.split()
            if scheme.lower() != "bearer":
                raise HTTPException(status_code=401, detail="Invalid authentication scheme, must be Bearer")
            token = token_value
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid authorization header format")
    else:
        # Check for token in query parameters as fallback
        token_param = request.query_params.get("token")
        if token_param:
            print(f"Token found in query parameter: {token_param[:10]}...")
            token = token_param
    
    # If still no token, check for cookie
    if not token:
        access_token = request.cookies.get("access_token")
        if access_token:
            print(f"Token found in cookie: {access_token[:10]}...")
            token = access_token
    
    if not token:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated. Please provide a valid Bearer token in Authorization header."
        )
    
    try:
        print(f"Token: {token}")
        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        print(f"User ID: {user_id}")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing user_id")
        
        # Get user from database
        from database import db
        # Try to find user by string ID first
        user = db.app_users.find_one({"_id": user_id})
        
        # If not found, try other possible formats
        if user is None:
            # Try to find by string representation of ID
            try:
                from bson import ObjectId
                # Check if the user_id is a valid ObjectId
                if ObjectId.is_valid(user_id):
                    user = db.app_users.find_one({"_id": ObjectId(user_id)})
            except Exception as e:
                print(f"Error converting to ObjectId: {str(e)}")
        
        if user is None:
            raise HTTPException(status_code=404, detail=f"User not found with ID: {user_id}")
            
        return user
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Authentication error: {str(e)}\n{error_details}")
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")


# Function to detect user intent
async def detect_user_intent(user_message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Detect the user's intent from their message"""
    # Use OpenAI to detect intent rather than keywords
    intent_prompt = [
        {"role": "system", "content": "You are an AI assistant that can detect user intent. Your task is to classify if the user is asking for practice exercises/quiz/questions to test their knowledge, or if they're having a general conversation seeking information. When the user wants a quiz or exercises to practice Portuguese, classify as 'question_generation' AND specify the question type as either 'multiple_choice' or 'fill_in_the_blanks' based on what the user is asking for. Pay careful attention to any specific topic the user mentions they want questions about. For general information or conversation, including questions about vocabulary, grammar rules, common phrases, or language information, classify as 'general_chat'. Respond with ONLY 'question_generation:multiple_choice', 'question_generation:fill_in_the_blanks', or 'general_chat'."},
        {"role": "user", "content": "Give me a quiz about Portuguese verbs"},
        {"role": "assistant", "content": "question_generation:multiple_choice"},
        {"role": "user", "content": "How do you say 'hello' in Portuguese?"},
        {"role": "assistant", "content": "general_chat"},
        {"role": "user", "content": "Can you explain the most common Portuguese verbs?"},
        {"role": "assistant", "content": "general_chat"},
        {"role": "user", "content": "I need multiple choice questions for Portuguese vocabulary"},
        {"role": "assistant", "content": "question_generation:multiple_choice"},
        {"role": "user", "content": "What are the most used nouns in Portuguese?"},
        {"role": "assistant", "content": "general_chat"},
        {"role": "user", "content": "Test my knowledge of Portuguese grammar with fill in the blank questions"},
        {"role": "assistant", "content": "question_generation:fill_in_the_blanks"},
        {"role": "user", "content": "I want to practice Portuguese through a quiz"},
        {"role": "assistant", "content": "question_generation:fill_in_the_blanks"},
        {"role": "user", "content": user_message}
    ]
    
    # Get intent classification from OpenAI
    intent_response = await create_openai_completion(messages=intent_prompt)
    intent_text = intent_response.choices[0].message.content.strip().lower()
    print(f"Intent detection: '{intent_text}' for message: '{user_message}'")
    
    # Check for simple/short responses that might be answering a previous question
    is_simple_response = len(user_message.strip().split()) <= 3 and intent_text == "off_topic"
    in_conversation = False
    
    if is_simple_response and conversation_id:
        # Get conversation history to check context
        history = MongoDBConversationManager.get_conversation_history(conversation_id)
        
        # Check if there's previous context where the AI asked a question
        if history and len(history) > 0:
            # Get the most recent AI message
            ai_messages = [msg for msg in history if msg.get("sender") == MessageSenders.AI]
            if ai_messages:
                last_ai_message = ai_messages[-1]
                last_ai_content = last_ai_message.get("content", "")
                
                # Check if the last AI message ended with a question mark or contains common question phrases
                question_indicators = ["?", "can you", "do you", "could you", "would you", "how about", "have you"]
                for indicator in question_indicators:
                    if indicator in last_ai_content.lower():
                        print(f"Short response '{user_message}' appears to be answering AI's previous question")
                        # Override the off-topic classification
                        intent_text = "general_chat"
                        in_conversation = True
                        break
    
    # Default intent is general chat
    intent = {
        "intent": "general_chat"
    }
    
    # Determine if this is a question generation intent
    is_question_intent = "question_generation" in intent_text
    
    if is_question_intent:
        # Extract topic if mentioned
        topic = "Portuguese language"  # Default
        topic_indicators = ["about ", "on ", "related to ", "regarding ", "for "]
        
        for indicator in topic_indicators:
            if indicator in user_message:
                # Extract the part after the indicator
                parts = user_message.split(indicator, 1)
                if len(parts) > 1:
                    # Extract up to the next punctuation or end of string
                    topic_part = parts[1].split('.')[0].split('?')[0].split('!')[0]
                    if topic_part:
                        topic = topic_part
        
        # Detect difficulty if mentioned
        difficulty = None
        if "easy" in user_message:
            difficulty = DifficultyLevel.EASY
        elif "hard" in user_message or "difficult" in user_message:
            difficulty = DifficultyLevel.HARD
        elif "medium" in user_message or "intermediate" in user_message:
            difficulty = DifficultyLevel.MEDIUM
        
        # Extract question type from intent_text
        question_type = None
        if ":multiple_choice" in intent_text:
            question_type = QuestionTypes.MULTIPLE_CHOICE
        else:
            question_type = QuestionTypes.FILL_IN_THE_BLANKS
        
        intent = {
            "intent": "question_request",
            "topic": topic,
            "difficulty": difficulty,
            "question_type": question_type
        }
    
    return intent

# Function to generate AI response
async def generate_ai_response(user_message: str, conversation_id: Optional[str] = None) -> AIChatResponse:
    # Create conversation if needed
    if conversation_id is None:
        # Generate a unique ID for the conversation if not provided
        conversation_id = str(uuid.uuid4())
        MongoDBConversationManager.create_conversation(
            conversation_id=conversation_id,
            title="Chat about Portuguese",
            description="General conversation about Portuguese language"
        )
    
    # Get the conversation state
    conversation_state = MongoDBConversationManager.get_state(conversation_id)
    
    # Detect user intent
    intent = await detect_user_intent(user_message, conversation_id)
    
    # Add user message to conversation history
    MongoDBConversationManager.add_message(
        conversation_id=conversation_id,
        message={
            "sender": MessageSenders.USER,
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        }
    )
    
    # Get conversation context for OpenAI
    context = await get_conversation_context(conversation_id)
    
    # Check for simple/short responses that might be answering a previous question
    is_simple_response = len(user_message.strip().split()) <= 3 and not is_app_related_query(user_message)
    
    if is_simple_response and context:
        # Check if there's previous context where the AI asked a question
        if len(context) > 0:
            # Get the most recent AI message
            for i in range(len(context) - 1, -1, -1):
                if context[i]["role"] == "assistant":
                    last_ai_content = context[i]["content"]
                    
                    # Check if the last AI message ended with a question mark or contains common question phrases
                    question_indicators = ["?", "can you", "do you", "could you", "would you", "how about", "have you"]
                    for indicator in question_indicators:
                        if indicator in last_ai_content.lower():
                            print(f"Short response '{user_message}' appears to be answering AI's previous question")
                            # Don't treat as off-topic
                            break
                    break
    
    # Based on intent, generate appropriate response
    if intent.get("intent") == "question_request":
        # Handle question generation
        difficulty = conversation_state.get("difficulty_level", "medium") if conversation_state else "medium"
        
        # Generate questions
        questions = question_generator.generate_questions(
            topic=intent.get("topic", "Portuguese language"),
            num_questions=intent.get("num_questions", 2),
            difficulty=difficulty,
            question_types=[intent.get("question_type", QuestionTypes.MULTIPLE_CHOICE)]
        )
        
        # Create response
        question_content = f"Here are some Portuguese language questions ({difficulty} difficulty):"
        response = AIChatResponse(
            id=get_next_message_id(),
            type=ResponseType.QUESTION,
            content=question_content,
            payload=QuestionResponse(questions=questions)
        )
        
        # Add AI response to conversation history
        MongoDBConversationManager.add_message(
            conversation_id=conversation_id,
            message={
                "sender": MessageSenders.AI,
                "content": question_content,
                "timestamp": datetime.now().isoformat(),
                "id": response.id,
                "type": ResponseType.QUESTION,
                "payload": {
                    "questions": [q.dict() for q in questions]
                }
            }
        )
        
        return response
    else:
        # Handle general conversation
        system_prompt = """You are an AI assistant for Portuguese language learning. 
        Only respond to queries related to the Portuguese language, Portugal, or Portuguese culture. 
        If the query is not related to these topics, respond in a friendly, cheerful, and conversational way, 
        gently steering the conversation back to Portuguese topics.
        Be enthusiastic and warmly invite users to ask about Portuguese instead.
        Provide helpful, educational responses that aid in learning Portuguese."""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation context
        messages.extend(context)
        
        # Add the current user message
        messages.append({"role": "user", "content": user_message})
        
        # Get response from OpenAI
        response_obj = await create_openai_completion(messages)
        ai_response = response_obj.choices[0].message.content
        
        # Check if the response is app-related
        if not is_app_related_query(user_message):
            # Define topic name for off-topic redirection
            topic_name = "Portuguese language" # Default topic name
            
            # Try to extract topic from intent or context
            if intent.get("topic"):
                topic_name = intent.get("topic")
            
            # Generate a contextual response redirecting to Portuguese learning
            redirect_prompt = [
                {"role": "system", "content": f"""
                You are a Portuguese language learning assistant. The user has asked something off-topic.
                
                Generate a friendly, conversational response that:
                1. Briefly acknowledges their off-topic question in a warm, friendly way
                2. Gently redirects them back to learning Portuguese
                3. Specifically mentions their current topic: '{topic_name}'
                4. Offers a specific suggestion, example, or question about '{topic_name}' to re-engage them
                5. Format your response in HTML for readability using simple <p>, <strong> tags
                
                Keep your response friendly, helpful and concise (max 3 sentences).
                """},
                {"role": "user", "content": user_message}
            ]
            
            # Get response from OpenAI
            redirect_response = await create_openai_completion(messages=redirect_prompt)
            ai_response = redirect_response.choices[0].message.content
        
        # Create response object
        text_content = ai_response.strip()
        response = AIChatResponse(
            id=get_next_message_id(),
            type=ResponseType.TEXT,
            content=text_content[:100] + "..." if len(text_content) > 100 else text_content,
            payload=TextResponse(text=text_content)
        )
        
        # Add AI response to conversation history
        MongoDBConversationManager.add_message(
            conversation_id=conversation_id,
            message={
                "sender": MessageSenders.AI,
                "content": response.content,
                "timestamp": datetime.now().isoformat(),
                "id": response.id,
                "type": ResponseType.TEXT,
                "payload": {
                    "text": text_content
                }
            }
        )
        
        return response
# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to the Portagees Chat API. Please use the /api endpoints."}

# Chat endpoint
@app.post("/api/chat", response_model=AIChatResponse)
async def chat(user_request: UserChatRequest):
    """Chat endpoint that handles user messages and returns AI responses"""
    try:
        return await generate_ai_response(user_request.content, user_request.conversation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "API is running"}

# Test OpenAI connection
@app.get("/api/test-openai")
async def test_openai_connection():
    """Test OpenAI API connection"""
    try:
        # Get OpenAI module version
        import openai
        openai_version = openai.__version__
        
        # Test a simple completion
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'OpenAI connection successful!' if you can read this."}
        ]
        
        response = await create_openai_completion(messages)
        response_text = response.choices[0].message.content
        
        # Check if we got an error response
        if "technical issue" in response_text or "couldn't process" in response_text.lower():
            return {
                "status": "error",
                "message": response_text,
                "api_key_configured": bool(openai_api_key),
                "openai_module_version": openai_version
            }
        
        return {
            "status": "success",
            "message": "OpenAI connection successful!",
            "api_key_configured": bool(openai_api_key),
            "openai_module_version": openai_version
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error connecting to OpenAI API: {str(e)}",
            "api_key_configured": bool(openai_api_key),
            "openai_module_version": openai.__version__ if 'openai' in globals() else "unknown"
        }

# Process user message with context
@app.post("/api/process-message", 
          summary="Process user message with topic context", 
          description="Process user message maintaining topic context and detecting intent for questions or general chat")
async def process_message(message_data: ProcessMessage, user=Depends(get_current_user)):
    try:
        # Extract data from request
        conversation_id = message_data.conversation_id
        user_message = message_data.message
        topic_ids = message_data.topic
        difficulty = message_data.difficulty
        num_questions = message_data.num_questions
        # Default topic name if CMS fetch fails
        topic_name = "Portuguese language"
        
        # Get user's preferred language from settings
        from database import db
        user_id = str(user["_id"])
        user_settings = db.user_settings.find_one({"user_id": user_id})
        preferred_language = user_settings.get("preferred_language", "Portuguese") if user_settings else "Portuguese"
        print(f"User Settings: {user_settings}")
        print(f"Process message request: conversation_id={conversation_id}, message='{user_message}', topic_ids='{topic_ids}', preferred_language='{preferred_language}'")
        
        
        try:
            cms_data = await fetch_prompt_from_cms(topic_ids)
            print(f"Received CMS data: {cms_data}")
            
            # Extract prompt and topic name from CMS response
            if cms_data.get('data'):
                cms_prompt = cms_data.get('data', {}).get('prompt', '')
                topic_name = cms_data.get('data', {}).get('name', 'Portuguese language')
                print(f"Extracted topic name from CMS: '{topic_name}'")
            else:
                cms_prompt = cms_data.get('prompt', '')
                
            if not cms_prompt:
                print("Warning: No prompt received from CMS, using default system prompt")
                cms_prompt = """You are an AI assistant for Portuguese language learning. 
                Only respond to queries related to the Portuguese language, Portugal, or Portuguese culture."""
        except Exception as e:
            print(f"Error getting prompt from CMS: {str(e)}")
            # Fallback to default prompt if CMS call fails
            cms_prompt = """You are an AI assistant for Portuguese language learning. 
            Only respond to queries related to the Portuguese language, Portugal, or Portuguese culture."""

        # Use topic_name for intent detection
        intent_prompt = [
            {"role": "system", "content": f"""
                You are a classifier for a Portuguese language learning app.
                Classify if the user message is asking for:
                - question_generation:multiple_choice - they want multiple choice questions about Portuguese
                - question_generation:fill_in_the_blanks - they want fill-in-the-blank exercises for Portuguese
                - general_chat - they want to generally talk about Portuguese language or related topics
                - off_topic - they're asking about something not related to Portuguese
                
                They are currently learning about: {topic_name}
                
                IMPORTANT: Short responses like "yes", "no", "maybe", "I can't", etc. should be classified as 
                "general_chat" as they are likely responses to previous questions in the conversation.
                
                Return ONLY one of these classifications without any explanation.
                """},
            {"role": "user", "content": "Give me a quiz about Portuguese verbs"},
            {"role": "assistant", "content": "question_generation:multiple_choice"},
            {"role": "user", "content": "How do you say 'hello' in Portuguese?"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": "Can you explain the most common Portuguese verbs?"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": "I need multiple choice questions for Portuguese vocabulary"},
            {"role": "assistant", "content": "question_generation:multiple_choice"},
            {"role": "user", "content": "What are the most used nouns in Portuguese?"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": "Test my knowledge of Portuguese grammar with fill in the blank questions"},
            {"role": "assistant", "content": "question_generation:fill_in_the_blanks"},
            {"role": "user", "content": "I want to practice Portuguese through a quiz"},
            {"role": "assistant", "content": "question_generation:fill_in_the_blanks"},
            {"role": "user", "content": "What's the weather like today?"},
            {"role": "assistant", "content": "off_topic"},
            {"role": "user", "content": "Yes"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": "No, I can't"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": "Maybe later"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": user_message}
        ]
        
        # Get intent classification from OpenAI
        intent_response = await create_openai_completion(messages=intent_prompt)
        intent_text = intent_response.choices[0].message.content.strip().lower()
        print(f"Intent detection: '{intent_text}' for message: '{user_message}'")
        
        # Check for simple/short responses that might be answering a previous question
        is_simple_response = len(user_message.strip().split()) <= 3 and intent_text == "off_topic"
        in_conversation = False
        
        if is_simple_response and conversation_id:
            # Get conversation history to check context
            history = MongoDBConversationManager.get_conversation_history(conversation_id)
            
            # Check if there's previous context where the AI asked a question
            if history and len(history) > 0:
                # Get the most recent AI message
                ai_messages = [msg for msg in history if msg.get("sender") == MessageSenders.AI]
                if ai_messages:
                    last_ai_message = ai_messages[-1]
                    last_ai_content = last_ai_message.get("content", "")
                    
                    # Check if the last AI message ended with a question mark or contains common question phrases
                    question_indicators = ["?", "can you", "do you", "could you", "would you", "how about", "have you"]
                    for indicator in question_indicators:
                        if indicator in last_ai_content.lower():
                            print(f"Short response '{user_message}' appears to be answering AI's previous question")
                            # Override the off-topic classification
                            intent_text = "general_chat"
                            in_conversation = True
                            break
        
        # Check if the request is off-topic (not related to Portuguese learning)
        if intent_text == "off_topic":
            print("Detected off-topic request")
            # Store the message in conversation history
            MongoDBConversationManager.add_message(
                conversation_id=conversation_id,
                message={
                    "sender": MessageSenders.USER,
                    "content": user_message,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Generate a contextual response redirecting to Portuguese learning
            # using OpenAI instead of hardcoded response
            redirect_prompt = [
                {"role": "system", "content": f"""
                You are a Portuguese language learning assistant. The user has asked something off-topic.
                
                Generate a friendly, conversational response that:
                1. Briefly acknowledges their off-topic question in a warm, friendly way
                2. Gently redirects them back to learning Portuguese
                3. Specifically mentions their current topic: '{topic_name}'
                4. Offers a specific suggestion, example, or question about '{topic_name}' to re-engage them
                5. Format your response in HTML for readability using simple <p>, <strong> tags
                
                Keep your response friendly, helpful and concise (max 3 sentences).
                """},
                {"role": "user", "content": user_message}
            ]
            
            # Get response from OpenAI
            redirect_response = await create_openai_completion(messages=redirect_prompt)
            off_topic_response = redirect_response.choices[0].message.content
            
            MongoDBConversationManager.add_message(
                conversation_id=conversation_id,
                message={
                    "sender": MessageSenders.AI,
                    "content": off_topic_response,
                    "timestamp": datetime.now().isoformat(),
                    "type": ResponseType.TEXT,
                    "payload": {"text": off_topic_response}
                }
            )
            
            # Return the response with debugging info
            result = {
                "type": "text",
                "intent": "off_topic",
                "message": off_topic_response,
                "topic": "Portuguese learning",
                "topic_name": topic_name
            }
            return result
        
        # Determine if this is a question generation request
        is_question_intent = "question_generation" in intent_text
        print(f"Question intent detected: {is_question_intent}, full intent: {intent_text}")
        
        # Extract question type if it's a question generation intent
        question_type = None
        if is_question_intent:
            if ":multiple_choice" in intent_text:
                question_type = [QuestionTypes.MULTIPLE_CHOICE]
                print(f"Multiple choice question type detected")
            else:  # Default to fill in the blanks if multiple choice not specifically requested
                question_type = [QuestionTypes.FILL_IN_THE_BLANKS]
                print(f"Fill in the blanks question type selected (default or requested)")
        
        if is_question_intent:
            # Generate questions
            difficulty = message_data.difficulty
            num_questions = message_data.num_questions
            
            try:
                # Extract topic from user message if they're asking for specific questions
                question_topic = topic_name  # Default to the current topic
                
                # Try to extract a more specific topic from the user message
                topic_extraction_prompt = [
                    {"role": "system", "content": f"""
                    Extract the specific topic the user wants questions about from their message. 
                    Pay special attention to any Portuguese grammar concepts, vocabulary categories, or language features mentioned.
                    The user is currently studying: {topic_name}
                    Return ONLY the topic, no extra text or explanation.
                    """},
                    {"role": "user", "content": "Give me questions about Portuguese verb conjugation"},
                    {"role": "assistant", "content": "Portuguese verb conjugation"},
                    {"role": "user", "content": "I want to practice Portuguese greetings"},
                    {"role": "assistant", "content": "Portuguese greetings"},
                    {"role": "user", "content": "Test me on days of the week in Portuguese"},
                    {"role": "assistant", "content": "Days of the week in Portuguese"},
                    {"role": "user", "content": "Can I have 5 fill in the blank questions about Portuguese prepositions?"},
                    {"role": "assistant", "content": "Portuguese prepositions"},
                    {"role": "user", "content": user_message}
                ]
                
                # Get the specific topic from the user message
                topic_response = await create_openai_completion(messages=topic_extraction_prompt)
                extracted_topic = topic_response.choices[0].message.content.strip()
                
                # Use the extracted topic if it seems valid
                if extracted_topic and len(extracted_topic) > 3 and extracted_topic.lower() != "portuguese":
                    question_topic = extracted_topic
                    print(f"Extracted specific topic: '{question_topic}' from user message")
                else:
                    # If we couldn't extract a specific topic, use the topic name from CMS
                    question_topic = topic_name
                    print(f"Using topic name from CMS: '{question_topic}'")
                
                # Debug prints
                print(f"Generating questions with topic={question_topic}, num_questions={num_questions}, difficulty={difficulty}, question_types={question_type}")
                
                # Make sure we convert difficulty to string for the response
                difficulty_str = difficulty.value if hasattr(difficulty, 'value') else difficulty
                
                # Add cms_prompt to the question generation context if available
                if cms_prompt:
                    # Configure the question generator with the custom prompt and preferred language
                    question_generator.configure_custom_prompt(
                        f"You are generating questions about {question_topic}. {cms_prompt}"
                    )
                    print("Using custom CMS prompt for question generation")
                
                # Generate questions with appropriate type
                print(f"About to call question_generator.generate_questions with: topic={question_topic}, num_questions={num_questions}, difficulty={difficulty}, question_types={question_type}")
                
                # For multiple choice questions, let's generate more to ensure we get enough unique ones
                adjusted_num_questions = num_questions
                if question_type[0] == QuestionTypes.MULTIPLE_CHOICE:
                    adjusted_num_questions = num_questions * 3  # Generate 3x as many to ensure uniqueness
                    print(f"Adjusted number of questions for multiple choice to {adjusted_num_questions} to ensure {num_questions} unique questions")
                
                try:
                    questions = question_generator.generate_questions(
                        topic=question_topic,
                        num_questions=adjusted_num_questions,
                        difficulty=difficulty,
                        question_types=question_type
                    )
                finally:
                    # Reset the custom prompt after generating questions
                    if cms_prompt:
                        question_generator.configure_custom_prompt(None)
                        print("Reset custom prompt in question generator")
                
                if not questions:
                    print("Warning: No questions were generated. Using fallback questions.")
                    # Create a fallback question if none were generated
                    if question_type[0] == QuestionTypes.MULTIPLE_CHOICE:
                        questions = []
                        # Generate multiple different fallback questions
                        for i in range(num_questions):
                            fallback = MultipleChoiceQuestion(
                                id=str(uuid.uuid4()),
                                type=QuestionTypes.MULTIPLE_CHOICE,
                                questionText=f"What is the Portuguese word for '{['hello', 'goodbye', 'please', 'thank you', 'yes'][i % 5]}'?",
                                questionDescription="Choose the correct translation.",
                                options=[
                                    ["Olá", "Adeus", "Bom dia", "Obrigado"],
                                    ["Adeus", "Olá", "Até logo", "Bom dia"],
                                    ["Por favor", "Obrigado", "De nada", "Sim"],
                                    ["Obrigado/Obrigada", "Por favor", "De nada", "Sim"],
                                    ["Sim", "Não", "Talvez", "Por favor"]
                                ][i % 5],
                                correct_answers=[["Olá", "Adeus", "Por favor", "Obrigado/Obrigada", "Sim"][i % 5]],
                                difficulty=difficulty,
                                hint=f"This is a common greeting or polite expression."
                            )
                            questions.append(fallback)
                    else:
                        questions = []
                        # Generate multiple different fallback questions for fill in the blanks
                        templates = [
                            {"sentence": "Eu ____ português todos os dias.", "answer": "falo"},
                            {"sentence": "Nós ____ para a escola de manhã.", "answer": "vamos"},
                            {"sentence": "O gato ____ no sofá.", "answer": "está"},
                            {"sentence": "A casa é ____.", "answer": "grande"},
                            {"sentence": "Eles ____ muito felizes.", "answer": "são"}
                        ]
                        
                        for i in range(num_questions):
                            template = templates[i % len(templates)]
                            fallback = FillInTheBlankQuestion(
                                id=str(uuid.uuid4()),
                                type=QuestionTypes.FILL_IN_THE_BLANKS,
                                questionText="Complete the sentence with the correct word:",
                                questionDescription="Fill in the blank with the appropriate Portuguese word.",
                                questionSentence=template["sentence"],
                                correct_answers=[template["answer"]],
                                difficulty=difficulty,
                                hint=f"Think about the context of the sentence.",
                                blankSeparator="____",
                                numberOfBlanks=1
                            )
                            questions.append(fallback)
                
                print(f"Generated {len(questions)} questions of types: {[q.type for q in questions if q is not None]}")
                
                # Ensure we have unique questions
                unique_questions = []
                question_texts = set()
                
                for q in questions:
                    if q is None:
                        print("Warning: Found None question, skipping")
                        continue
                        
                    try:
                        # For multiple choice, check questionText
                        if q.type == QuestionTypes.MULTIPLE_CHOICE and q.questionText not in question_texts:
                            unique_questions.append(q)
                            question_texts.add(q.questionText)
                        # For fill in the blanks, check questionSentence
                        elif q.type == QuestionTypes.FILL_IN_THE_BLANKS and q.questionSentence not in question_texts:
                            unique_questions.append(q)
                            question_texts.add(q.questionSentence)
                    except Exception as e:
                        print(f"Error processing question: {str(e)}")
                        continue
                
                # If we still don't have enough unique questions after initial generation,
                # generate more using direct method calls instead of through question_generator
                # Try this approach a couple of times but not too many to avoid wasting time
                attempts = 0
                max_direct_attempts = 3
                
                while len(unique_questions) < num_questions and attempts < max_direct_attempts:
                    attempts += 1
                    print(f"Direct generation attempt {attempts}/{max_direct_attempts} to reach {num_questions} questions")
                    
                    try:
                        if question_type[0] == QuestionTypes.MULTIPLE_CHOICE:
                            # Generate one more directly using the generator method
                            new_question = question_generator.generate_multiple_choice_question(
                                difficulty=difficulty,
                                topic=f"{question_topic} {len(unique_questions)}"  # Add a number to make it more unique
                            )
                            
                            if new_question and new_question.questionText not in question_texts:
                                unique_questions.append(new_question)
                                question_texts.add(new_question.questionText)
                                print(f"Added unique multiple choice question. Now have {len(unique_questions)}/{num_questions}")
                        else:
                            # Generate one more fill in the blank question directly
                            new_question = question_generator.generate_fill_in_blank_question(
                                difficulty=difficulty,
                                topic=f"{question_topic} {len(unique_questions)}"  # Add a number to make it more unique
                            )
                            
                            if new_question and new_question.questionSentence not in question_texts:
                                unique_questions.append(new_question)
                                question_texts.add(new_question.questionSentence)
                                print(f"Added unique fill-in-the-blank question. Now have {len(unique_questions)}/{num_questions}")
                    except Exception as e:
                        print(f"Error generating additional question directly: {str(e)}")
                
                # After all the attempts to generate questions, ensure we have the requested number
                if question_type[0] == QuestionTypes.MULTIPLE_CHOICE and len(unique_questions) < num_questions:
                    # Force adding hardcoded questions to meet the requirement
                    remaining_count = num_questions - len(unique_questions)
                    print(f"FORCE ADDING {remaining_count} hardcoded multiple choice questions to meet the requirement")
                    
                    # Import random for shuffling options
                    import random
                    
                    # These are our guaranteed questions that will always be available
                    mcq_questions = [
                        {
                            "questionText": "Which Portuguese noun is feminine?",
                            "questionDescription": "Select the noun that is feminine in Portuguese.",
                            "options": ["casa (house)", "livro (book)", "carro (car)", "telefone (telephone)"],
                            "correct_answers": ["casa (house)"],
                            "hint": "Nouns ending in 'a' are typically feminine in Portuguese."
                        },
                        {
                            "questionText": "What is the correct article to use with the Portuguese noun 'livro'?",
                            "questionDescription": "Choose the appropriate definite article.",
                            "options": ["o", "a", "os", "as"],
                            "correct_answers": ["o"],
                            "hint": "Masculine singular nouns use 'o' as their definite article."
                        },
                        {
                            "questionText": "What is the plural form of the Portuguese noun 'mulher'?",
                            "questionDescription": "Select the correct plural form.",
                            "options": ["mulheres", "mulhers", "mulheris", "mulher"],
                            "correct_answers": ["mulheres"],
                            "hint": "Many Portuguese nouns add 'es' to form the plural."
                        },
                        {
                            "questionText": "Which of these Portuguese nouns is masculine?",
                            "questionDescription": "Identify the masculine noun.",
                            "options": ["sol (sun)", "flor (flower)", "nação (nation)", "noite (night)"],
                            "correct_answers": ["sol (sun)"],
                            "hint": "Most Portuguese nouns ending in consonants are masculine."
                        },
                        {
                            "questionText": "What is the correct article to use with the Portuguese noun 'mesa'?",
                            "questionDescription": "Choose the appropriate definite article.",
                            "options": ["a", "o", "as", "os"],
                            "correct_answers": ["a"],
                            "hint": "Feminine singular nouns use 'a' as their definite article."
                        },
                        {
                            "questionText": "Which word is NOT a Portuguese noun?",
                            "questionDescription": "Identify the word that is not a noun in Portuguese.",
                            "options": ["correr (to run)", "pessoa (person)", "cidade (city)", "dia (day)"],
                            "correct_answers": ["correr (to run)"],
                            "hint": "Look for the verb in the list."
                        },
                        {
                            "questionText": "What is the diminutive form of the Portuguese noun 'casa'?",
                            "questionDescription": "Select the correct diminutive form.",
                            "options": ["casinha", "casita", "casica", "casona"],
                            "correct_answers": ["casinha"],
                            "hint": "Many Portuguese diminutives are formed with the suffix '-inho/a'."
                        }
                    ]
                    
                    # Add the required number of fallback questions
                    for i in range(remaining_count):
                        question_data = mcq_questions[i % len(mcq_questions)]
                        
                        # Make a copy of the options and shuffle them
                        options = question_data["options"].copy()
                        random.shuffle(options)
                        
                        hardcoded_question = MultipleChoiceQuestion(
                            id=str(uuid.uuid4()),
                            type=QuestionTypes.MULTIPLE_CHOICE,
                            questionText=question_data["questionText"],
                            questionDescription=question_data["questionDescription"],
                            options=options,
                            correct_answers=question_data["correct_answers"],
                            difficulty=difficulty,
                            hint=question_data["hint"]
                        )
                        unique_questions.append(hardcoded_question)
                        print(f"Added hardcoded MCQ #{i+1} with randomized options")
                
                print(f"Final count: {len(unique_questions)} unique questions on topic '{question_topic}'")
                
                # Ensure we have exactly the right number
                if len(unique_questions) > num_questions:
                    unique_questions = unique_questions[:num_questions]
                    print(f"Trimmed to exactly {num_questions} questions as requested")
                
                # Store the message and response in the conversation history
                MongoDBConversationManager.add_message(
                    conversation_id=conversation_id,
                    message={
                        "sender": MessageSenders.USER,
                        "content": user_message,
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                # Add AI message with questions to conversation history
                response_content = f"Here are some questions about {question_topic}:"
                MongoDBConversationManager.add_message(
                    conversation_id=conversation_id,
                    message={
                        "sender": MessageSenders.AI,
                        "content": response_content,
                        "timestamp": datetime.now().isoformat(),
                        "type": ResponseType.QUESTION,
                        "payload": {
                            "questions": [q.dict() for q in unique_questions]
                        }
                    }
                )
                
                # Create lists for the response
                all_questions = []
                for q in unique_questions:
                    try:
                        all_questions.append(q.dict())
                    except Exception as e:
                        print(f"Error converting question to dict: {str(e)}")
                
                # Ensure we have exactly the right number of questions in the final response
                print(f"Final response includes {len(all_questions)} questions")
                assert len(all_questions) == num_questions, f"Error: Final response has {len(all_questions)} questions instead of {num_questions}"
                
                # Return the questions in a format based on the question type
                result = {
                    "type": "question",
                    "intent": f"question_generation:{question_type[0].value.lower()}",
                    "message": response_content,
                    "topic": question_topic,
                    "difficulty": difficulty_str,
                    "questions": all_questions,
                    "topic_name": topic_name
                }
                
                print(f"Returning result with {len(all_questions)} questions")
                return result
                
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"Error in question generation: {str(e)}\n{error_details}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error generating questions: {str(e)}"
                )
        else:
            # General conversation logic - print more debug information
            print(f"Processing general chat for topic: {topic_name}")
            
            # Create context with topic to maintain the conversation focus and incorporate CMS prompt
            system_prompt = f"""
            You are a Portuguese language assistant. The user is studying about '{topic_name}'. 
            {cms_prompt}
            
            Keep your responses focused on this '{topic_name}' when relevant. 
            Format your response in HTML for readability, using:
            - <p> tags for paragraphs
            - <ul> and <li> for bullet points when listing items or examples
            - <strong> for emphasis on key terms
            - Avoid using scripts or potentially unsafe HTML
            Ensure the response is clear, concise, and broken into logical sections.
            Return the response wrapped in a single <div> tag.
            """

            # Create context with topic and history
            context_messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # Get conversation history to maintain context
            history = MongoDBConversationManager.get_conversation_history(conversation_id)
            print(f"Got history with {len(history)} messages")
            
            # Use all messages for context instead of limiting to last 5
            for msg in history:
                if msg.get("sender") == MessageSenders.USER:
                    context_messages.append({"role": "user", "content": msg.get("content", "")})
                else:
                    context_messages.append({"role": "assistant", "content": msg.get("content", "")})
            
            # Add current message
            context_messages.append({"role": "user", "content": user_message})
            print(f"Created context with {len(context_messages)} messages")
            
            # Generate AI response
            print("Calling OpenAI API...")
            response = await create_openai_completion(messages=context_messages)
            ai_message = response.choices[0].message.content
            print(f"Got response: {ai_message[:50]}...")
            
            # Store the user message in conversation history
            MongoDBConversationManager.add_message(
                conversation_id=conversation_id,
                message={
                    "sender": MessageSenders.USER,
                    "content": user_message,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Store the AI response in conversation history
            print("Adding AI message to conversation history")
            MongoDBConversationManager.add_message(
                conversation_id=conversation_id,
                message={
                    "sender": MessageSenders.AI,
                    "content": ai_message,
                    "timestamp": datetime.now().isoformat(),
                    "type": ResponseType.TEXT,
                    "payload": {"text": ai_message}
                }
            )
            
            # Return the response with debugging info
            print("Returning response to client")
            result = {
                "type": "text",
                "intent": "general_chat",
                "message": ai_message,
                "topic": topic_ids,
                "topic_name": topic_name
            }
            print(f"Result: {result}")
            return result
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error processing message: {str(e)}\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )

# Initialize password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Token schema
class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str
    username: str
    first_name: str
    last_name: str

# Function to create access token
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def fetch_prompt_from_cms(topic_ids: str):
    """Fetch prompt from CMS based on topic IDs"""
    try:
        import aiohttp
        import json

        cms_base_url = os.getenv("CMS_BASE_URL", "http://localhost:3000/api")
        print(f"Fetching prompt from CMS for topic_ids: {topic_ids}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{cms_base_url}/get-prompt", params={"topicIds": topic_ids}) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"CMS Response: {data}")
                    
                    # Make sure we properly extract the data from the CMS response structure
                    if data.get('success') and data.get('data'):
                        return {
                            'success': True,
                            'data': {
                                'id': data['data'].get('id', ''),
                                'name': data['data'].get('name', 'Portuguese language'),
                                'description': data['data'].get('description', ''),
                                'prompt': data['data'].get('prompt', ''),
                                'examples': data['data'].get('examples', [])
                            }
                        }
                    else:
                        print(f"Warning: CMS response missing expected structure: {data}")
                        return {
                            'success': False,
                            'data': {
                                'name': 'Portuguese language',
                                'prompt': ''
                            }
                        }
                else:
                    error_text = await response.text()
                    print(f"CMS API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Error from CMS API: {error_text}"
                    )
    except Exception as e:
        print(f"Error fetching prompt from CMS: {str(e)}")
        return {
            'success': False,
            'data': {
                'name': 'Portuguese language',
                'prompt': ''
            }
        }

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True) 