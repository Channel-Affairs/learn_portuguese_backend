from fastapi import FastAPI, HTTPException, Depends, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import os
from dotenv import load_dotenv
import openai
import json
import uuid
from datetime import datetime, timedelta
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer

# Import models and question generator
from models import (
    MessageSenders, ResponseType, QuestionTypes, DifficultyLevel,
    TextResponse, BaseQuestion, MultipleChoiceQuestion, FillInTheBlankQuestion,
    QuestionResponse, AIChatResponse, UserChatRequest, QuestionRequest,
    UserAnswer, AnswerEvaluation, UserAnswerResponse, 
    ConversationCreate, ConversationResponse,
    ConversationListResponse, Message, ConversationHistoryResponse,
    GetOrCreateConversation, ProcessMessage, ProcessMessageResponse,
    UserCreate, AppUser, UserSettings, UserSettingsCreate, UserSettingsUpdate
)
from question_generator import QuestionGenerator
# Use MongoDB conversation manager
from database import MongoDBConversationManager, MongoJSONEncoder, initialize_db

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

# Create a safe OpenAI client function with proper error handling
async def create_openai_completion(messages, model="gpt-3.5-turbo"):
    """Helper function to create OpenAI chat completions without proxy issues"""
    try:
        # Use direct HTTP requests instead of the OpenAI client
        import aiohttp
        import json
        
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": messages
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                result = await response.json()
                
                # Create response object that mimics the OpenAI client response
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    
                    # Create a dummy message object
                    class Message:
                        def __init__(self, content):
                            self.content = content
                    
                    # Create a dummy choice object
                    class Choice:
                        def __init__(self, message):
                            self.message = message
                    
                    # Create a dummy response object
                    class Response:
                        def __init__(self, choices):
                            self.choices = choices
                    
                    # Create and return the response
                    message = Message(content)
                    choice = Choice(message)
                    return Response([choice])
                else:
                    raise Exception(f"Unexpected response format: {result}")
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        # Return a dummy response object for graceful fallback
        class DummyChoice:
            def __init__(self):
                self.message = type('obj', (object,), {
                    'content': f"I couldn't process your request due to a technical issue: {str(e)[:100]}..."
                })
        
        class DummyResponse:
            def __init__(self):
                self.choices = [DummyChoice()]
        
        return DummyResponse()

# Initialize FastAPI app
app = FastAPI(
    title="Portagees Chat API", 
    description="API for the Portagees language learning chat application",
    version="1.0.0"
)

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
    # Check if query is related to Portuguese language learning
    portuguese_keywords = [
        "portuguese", "portugal", "learn", "language", "speak", "words", 
        "grammar", "vocabulary", "phrase", "sentence", "conjugate", "verb",
        "noun", "pronoun", "translation", "meaning", "say", "pronounce"
    ]
    
    query_lower = query.lower()
    
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

# Function to detect user intent
async def detect_user_intent(user_message: str) -> Dict[str, Any]:
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
    
    # Determine if this is a question generation request
    is_question_intent = "question_generation" in intent_text
    
    # Extract question type if it's a question generation intent
    question_type = None
    if is_question_intent:
        if ":multiple_choice" in intent_text:
            question_type = [QuestionTypes.MULTIPLE_CHOICE]
        else:  # Default to fill in the blanks if multiple choice not specifically requested
            question_type = [QuestionTypes.FILL_IN_THE_BLANKS]
    
    # Default intent is general chat
    intent = {
        "intent": "general_chat"
    }
    
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
    intent = await detect_user_intent(user_message)
    
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
    
    # Based on intent, generate appropriate response
    if intent.get("is_question_request", False):
        # Handle question generation
        difficulty = conversation_state.get("difficulty_level", "medium") if conversation_state else "medium"
        
        # Generate questions
        questions = question_generator.generate_questions(
            topic=intent.get("topic", "Portuguese language"),
            num_questions=intent.get("num_questions", 2),
            difficulty=difficulty,
            question_types=intent.get("question_type", [QuestionTypes.MULTIPLE_CHOICE, QuestionTypes.FILL_IN_THE_BLANKS])
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
            # Create more friendly, conversational responses for off-topic questions
            off_topic_responses = [
                "Oh, while I'd love to chat about that, I'm actually your Portuguese language buddy! 😊 I'm here to help you learn Portuguese - would you like to know some fun Portuguese phrases instead?",
                
                "That's an interesting topic! Though I'm actually specialized in Portuguese language learning. 🇵🇹 I'd be thrilled to help you discover something fascinating about Portuguese culture or language instead!",
                
                "I wish I could help with that, but Portuguese is my specialty! 🌟 How about we explore some beautiful Portuguese expressions or maybe learn about Portugal's amazing culture instead?",
                
                "While that's outside my Portuguese expertise, I'm super eager to help you learn something new about the Portuguese language! 🤩 Would you like to try a quick vocabulary exercise instead?",
                
                "I'm your friendly Portuguese language assistant, so that's not really my area. But hey, did you know that Portuguese has some really cool words that don't exist in English? Would you like to learn some?"
            ]
            
            # Select a random friendly response
            import random
            ai_response = random.choice(off_topic_responses)
        
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

# Function to evaluate user answers
async def evaluate_answer(user_answer: UserAnswer) -> UserAnswerResponse:
    """Evaluate a user's answer to a question"""
    conversation_id = user_answer.conversation_id
    question_id = user_answer.question_id
    answer = user_answer.answer
    question_text = user_answer.question_text
    
    # If we don't have the question_text, we need to find it in the conversation history
    if not question_text:
        # Get conversation history
        messages = MongoDBConversationManager.get_conversation_history(conversation_id)
        
        # Find the question with the matching ID
        for msg in messages:
            if msg.get("sender") == MessageSenders.AI and msg.get("type") == ResponseType.QUESTION:
                payload = msg.get("payload", {})
                if isinstance(payload, dict) and "questions" in payload:
                    for question in payload["questions"]:
                        if question.get("id") == question_id:
                            question_text = question.get("questionText", "")
                            break
    
    # If we still don't have the question_text, return an error
    if not question_text:
        raise HTTPException(status_code=400, detail="Question not found in conversation history")
    
    # Get conversation context for OpenAI
    context = await get_conversation_context(conversation_id)
    
    # Format the answer for evaluation
    user_answer_str = answer if isinstance(answer, str) else ", ".join(answer)
    
    # Create evaluation message
    eval_message = [
        {"role": "system", "content": "You are a Portuguese language teacher evaluating a student's answer to a question."},
        {"role": "user", "content": f"Question: {question_text}\nStudent's answer: {user_answer_str}\nEvaluate if this answer is correct. Provide explanation and any corrections needed. Return your response as a JSON object with the following structure: {{\"is_correct\": boolean, \"correct_answer\": \"string or array of strings with correct answer\", \"explanation\": \"detailed explanation string\", \"follow_up_hint\": \"optional hint for next steps\" }}"}
    ]
    
    # Generate evaluation from OpenAI
    response = await create_openai_completion(eval_message)
    
    # Parse the JSON response
    try:
        evaluation_text = response.choices[0].message.content
        
        # Extract JSON object from the response
        # Sometimes the model returns markdown with json inside
        if "```json" in evaluation_text:
            json_part = evaluation_text.split("```json")[1].split("```")[0].strip()
            evaluation_data = json.loads(json_part)
        elif "```" in evaluation_text:
            json_part = evaluation_text.split("```")[1].strip()
            evaluation_data = json.loads(json_part)
        else:
            evaluation_data = json.loads(evaluation_text)
        
        # Create evaluation object
        evaluation = AnswerEvaluation(
            is_correct=evaluation_data.get("is_correct", False),
            correct_answer=evaluation_data.get("correct_answer", ""),
            explanation=evaluation_data.get("explanation", ""),
            follow_up_hint=evaluation_data.get("follow_up_hint", None)
        )
        
        # Record answer result
        difficulty = "medium"  # Default difficulty
        MongoDBConversationManager.record_answer_result(
            conversation_id=conversation_id,
            question_id=question_id,
            was_correct=evaluation.is_correct,
            user_answer=user_answer_str,
            difficulty=difficulty
        )
        
        # Get conversation state to check current difficulty
        state = MongoDBConversationManager.get_state(conversation_id)
        current_difficulty = state.get("difficulty_level", "medium") if state else "medium"
        
        # Prepare response
        response = UserAnswerResponse(
            question_id=question_id,
            evaluation=evaluation,
            next_question=None  # We don't automatically generate next question
        )
        
        # Add evaluation to conversation history
        ai_msg = {
            "sender": MessageSenders.AI,
            "content": "Here's my evaluation of your answer:",
            "payload": {"text": evaluation.explanation},
            "type": ResponseType.FEEDBACK,
            "id": get_next_message_id(),
            "timestamp": datetime.now().isoformat()
        }
        MongoDBConversationManager.add_message(conversation_id, ai_msg)
        
        return response
        
    except Exception as e:
        print(f"Error evaluating answer: {str(e)}")
        
        # Fallback evaluation
        evaluation = AnswerEvaluation(
            is_correct=False,
            correct_answer="Could not determine",
            explanation=f"Sorry, I couldn't properly evaluate your answer due to a technical issue. Please try again."
        )
        
        return UserAnswerResponse(
            question_id=question_id,
            evaluation=evaluation,
            next_question=None
        )

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

# Generate questions endpoint
@app.post("/api/generate-questions", response_model=AIChatResponse)
async def generate_questions(request: QuestionRequest):
    """Generate Portuguese language questions"""
    try:
        # Get conversation state if conversation_id is provided
        difficulty = request.difficulty
        if not difficulty and request.conversation_id:
            conversation_state = MongoDBConversationManager.get_state(request.conversation_id)
            if conversation_state:
                difficulty = conversation_state.get("difficulty_level", "medium")
        
        # Default to medium if not specified
        if not difficulty:
            difficulty = "medium"
        
        # Generate questions
        questions = question_generator.generate_questions(
            topic=request.topic,
            num_questions=request.num_questions,
            difficulty=difficulty,
            question_types=request.question_types
        )
        
        # Create response
        content = f"Here are {request.num_questions} Portuguese language questions on {request.topic}:"
        response = AIChatResponse(
            id=get_next_message_id(),
            type=ResponseType.QUESTION,
            content=content,
            payload=QuestionResponse(questions=questions)
        )
        
        # If conversation_id is provided, save response to conversation history
        if request.conversation_id:
            MongoDBConversationManager.add_message(
                conversation_id=request.conversation_id,
                message={
                    "sender": MessageSenders.AI,
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                    "id": response.id,
                    "type": ResponseType.QUESTION,
                    "payload": {
                        "questions": [q.dict() for q in questions]
                    }
                }
            )
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating questions: {str(e)}")

# Evaluate answer endpoint
@app.post("/api/evaluate-answer", response_model=UserAnswerResponse)
async def evaluate_user_answer(user_answer: UserAnswer):
    """Evaluate user's answer to a question"""
    try:
        return await evaluate_answer(user_answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating answer: {str(e)}")

# Create conversation endpoint
@app.post("/api/conversations", response_model=ConversationResponse)
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
@app.get("/api/conversations/{conversation_id}", response_model=ConversationHistoryResponse)
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

# List user's conversations
@app.get("/api/conversations", response_model=ConversationListResponse)
async def list_conversations(user_id: str = "default_user"):
    """List all conversations for a user"""
    try:
        # Get all conversations for the user from MongoDB
        from database import conversations_collection
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
@app.post("/api/conversations/get-or-create", 
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

# Process user message with context
@app.post("/api/process-message", 
          summary="Process user message with topic context", 
          description="Process user message maintaining topic context and detecting intent for questions or general chat")
async def process_message(message_data: ProcessMessage):
    try:
        # Extract data from request
        conversation_id = message_data.conversation_id
        user_message = message_data.message
        topic = message_data.topic
        
        print(f"Process message request: conversation_id={conversation_id}, message='{user_message}', topic='{topic}'")
        try:
            cms_data = await fetch_prompt_from_cms(topic)
            print(f"Received CMS data: {cms_data}")
            
            # Extract prompt from CMS response
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
        # Use OpenAI to detect intent rather than keywords
        intent_prompt = [
            {"role": "system", "content": "You are an AI assistant that can detect user intent. Your task is to classify if the user is asking for practice exercises/quiz/questions to test their knowledge, or if they're having a general conversation seeking information. When the user wants a quiz or exercises to practice Portuguese, classify as 'question_generation' AND specify the question type as either 'multiple_choice' or 'fill_in_the_blanks' based on what the user is asking for. Pay careful attention to any specific topic the user mentions they want questions about. For general information or conversation, including questions about vocabulary, grammar rules, common phrases, or language information, classify as 'general_chat'. If the user's request is unrelated to Portuguese language learning, classify as 'off_topic'. Respond with ONLY 'question_generation:multiple_choice', 'question_generation:fill_in_the_blanks', 'general_chat', or 'off_topic'."},
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
            {"role": "user", "content": user_message}
        ]
        
        # Get intent classification from OpenAI
        intent_response = await create_openai_completion(messages=intent_prompt)
        intent_text = intent_response.choices[0].message.content.strip().lower()
        print(f"Intent detection: '{intent_text}' for message: '{user_message}'")
        
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
            
            # Generate a polite response redirecting to Portuguese learning
            off_topic_response = "Insufficient information to respond"
            
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
                "topic": "Portuguese learning"
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
                question_topic = topic  # Default to the current topic
                
                # Try to extract a more specific topic from the user message
                topic_extraction_prompt = [
                    {"role": "system", "content": "Extract the specific topic the user wants questions about from their message. Pay special attention to any Portuguese grammar concepts, vocabulary categories, or language features mentioned. Return ONLY the topic, no extra text or explanation."},
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
                    # If we couldn't extract a specific topic, but one was provided in the API call, use that
                    if topic and topic.lower() != "portuguese language":
                        question_topic = topic
                        print(f"Using topic from API call: '{question_topic}'")
                    else:
                        # Default to a generic topic
                        question_topic = "Portuguese language basics"
                        print(f"Using default topic: '{question_topic}'")
                
                # Debug prints
                print(f"Generating questions with topic={question_topic}, num_questions={num_questions}, difficulty={difficulty}, question_types={question_type}")
                
                # Make sure we convert difficulty to string for the response
                difficulty_str = difficulty.value if hasattr(difficulty, 'value') else difficulty
                
                # Generate questions with appropriate type
                print(f"About to call question_generator.generate_questions with: topic={question_topic}, num_questions={num_questions}, difficulty={difficulty}, question_types={question_type}")
                
                # For multiple choice questions, let's generate more to ensure we get enough unique ones
                adjusted_num_questions = num_questions
                if question_type[0] == QuestionTypes.MULTIPLE_CHOICE:
                    adjusted_num_questions = num_questions * 3  # Generate 3x as many to ensure uniqueness
                    print(f"Adjusted number of questions for multiple choice to {adjusted_num_questions} to ensure {num_questions} unique questions")
                
                questions = question_generator.generate_questions(
                    topic=question_topic,
                    num_questions=adjusted_num_questions,
                    difficulty=difficulty,
                    question_types=question_type
                )
                
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
                    "questions": all_questions
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
            print(f"Processing general chat for topic: {topic}")
            
            # Create context with topic to maintain the conversation focus
            # context_messages = [
            #     {"role": "system", "content": f"You are a Portuguese language assistant. The user is studying about '{topic}'. Keep your responses focused on this topic when relevant."}
            # ]
            system_prompt = f"""
            You are a Portuguese language assistant. The user is studying about '{topic}'. 
            Keep your responses focused on this '{topic}' when relevant. 
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
            
            for msg in history[-5:]:  # Use last 5 messages for context
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
                "topic": topic
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

# User signup schema
class UserSignup(BaseModel):
    email: EmailStr
    username: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

# User signup response
class UserSignupResponse(BaseModel):
    message: str
    user_id: str

# Login schema
class UserLogin(BaseModel):
    email: EmailStr
    password: str

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

# User signup endpoint
@app.post("/api/signup", response_model=UserSignupResponse)
async def signup(user_data: UserSignup):
    """Register a new user"""
    # Get database connection
    from database import db
    
    # Check if email already exists
    existing_user = db.app_users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if username already exists
    existing_username = db.app_users.find_one({"username": user_data.username})
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")

    try:
        # Hash the password
        hashed_password = pwd_context.hash(user_data.password)
        
        # Generate a user ID
        user_id = str(uuid.uuid4())
        
        # Create user object
        new_user = AppUser(
            _id=user_id,
            email=user_data.email,
            username=user_data.username,
            first_name=user_data.first_name or "",
            last_name=user_data.last_name or "",
            hashed_password=hashed_password,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Save user to database using the AppUser model
        user_dict = new_user.dict()
        result = db.app_users.insert_one(user_dict)
        
        # Return success response with the user ID
        return UserSignupResponse(
            message="User successfully created",
            user_id=user_id
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating user: {str(e)}"
        )

# Login endpoint
@app.post("/api/login", response_model=Token)
async def login(user_data: UserLogin):
    """Authenticate a user and return a JWT token"""
    try:
        # Get database connection
        from database import db
        
        # Find user by email in app_users collection
        user = db.app_users.find_one({"email": user_data.email})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Verify password
        if not pwd_context.verify(user_data.password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Create access token - ensure all data is JSON serializable
        user_id = str(user["_id"])  # Convert ObjectId to string if needed
        
        token_data = {
            "sub": user["email"],
            "user_id": user_id
        }
        token = create_access_token(token_data)
        
        # Return token with user profile data
        return Token(
            access_token=token,
            token_type="bearer",
            user_id=user_id,
            email=user["email"],
            username=user["username"],
            first_name=user["first_name"],
            last_name=user["last_name"]
        )
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Login error: {str(e)}"
        )

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
    # Debug all request headers
    print("All headers:")
    for key, value in request.headers.items():
        print(f"  {key}: {value}")
    
    # Try to get token from security scheme first (Swagger UI's Authorization)
    token = None
    if credentials and credentials.credentials:
        print(f"Token found in security scheme: {credentials.credentials[:10]}...")
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

# User settings endpoints
@app.get("/api/user/settings", summary="Get user settings")
async def get_user_settings(user=Depends(get_current_user)):
    """Get settings for the current user"""
    try:
        from database import db
        user_id = str(user["_id"])
        print(f"Getting settings for user ID: {user_id}")
        
        # Find user settings
        settings = db.user_settings.find_one({"user_id": user_id})
        
        if not settings:
            print(f"No settings found for user ID: {user_id}, returning defaults")
            # Return default settings if none exist
            return UserSettings(
                user_id=user_id,
                preferred_language="Portuguese",
                notification_enabled=True
            )
        
        # Convert MongoDB ObjectId to string
        if "_id" in settings:
            settings["_id"] = str(settings["_id"])
            
        return settings
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error retrieving user settings: {str(e)}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error retrieving user settings: {str(e)}")

@app.post("/api/user/settings", summary="Create user settings")
async def create_user_settings(settings_data: UserSettingsCreate, user=Depends(get_current_user)):
    """Create settings for the current user"""
    try:
        from database import db
        user_id = str(user["_id"])
        print(f"Creating settings for user ID: {user_id}")
        
        # Check if settings already exist
        existing_settings = db.user_settings.find_one({"user_id": user_id})
        if existing_settings:
            raise HTTPException(status_code=400, detail="Settings already exist for this user. Use PUT to update.")
        
        # Create new settings
        new_settings = UserSettings(
            _id=str(uuid.uuid4()),
            user_id=user_id,
            preferred_language=settings_data.preferred_language,
            notification_enabled=settings_data.notification_enabled,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Insert into database
        settings_dict = new_settings.dict()
        print(f"Inserting new settings: {settings_dict}")
        result = db.user_settings.insert_one(settings_dict)
        print(f"Insert result: {result.inserted_id}")
        
        return new_settings
        
    except HTTPException as e:
        # Re-raise HTTP exceptions as-is
        raise e
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error creating user settings: {str(e)}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error creating user settings: {str(e)}")

@app.put("/api/user/settings", summary="Update user settings")
async def update_user_settings(settings_data: UserSettingsUpdate, user=Depends(get_current_user)):
    """Update settings for the current user"""
    try:
        from database import db
        user_id = str(user["_id"])
        print(f"Updating settings for user ID: {user_id}")
        
        # Find existing settings
        existing_settings = db.user_settings.find_one({"user_id": user_id})
        print(f"Existing settings found: {existing_settings is not None}")
        
        if not existing_settings:
            # Create new settings if none exist
            settings_id = str(uuid.uuid4())
            new_settings = UserSettings(
                _id=settings_id,
                user_id=user_id,
                preferred_language=settings_data.preferred_language or "Portuguese",
                notification_enabled=settings_data.notification_enabled if settings_data.notification_enabled is not None else True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            settings_dict = new_settings.dict()
            print(f"Creating new settings during update: {settings_dict}")
            result = db.user_settings.insert_one(settings_dict)
            print(f"Insert result: {result.inserted_id}")
            
            # Get the newly created settings
            updated_settings = db.user_settings.find_one({"_id": settings_id})
            if updated_settings is None:
                print(f"Warning: Could not find newly created settings with ID {settings_id}")
                # Return the model we just created as fallback
                return new_settings
                
            if "_id" in updated_settings:
                updated_settings["_id"] = str(updated_settings["_id"])
                
            return updated_settings
        
        # Prepare update data
        update_data = {}
        if settings_data.preferred_language is not None:
            update_data["preferred_language"] = settings_data.preferred_language
        if settings_data.notification_enabled is not None:
            update_data["notification_enabled"] = settings_data.notification_enabled
        
        # Add updated timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        print(f"Updating settings with data: {update_data}")
        
        # Update settings
        update_result = db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        print(f"Update result: matched={update_result.matched_count}, modified={update_result.modified_count}")
        
        # Get updated settings
        updated_settings = db.user_settings.find_one({"user_id": user_id})
        if updated_settings is None:
            raise HTTPException(status_code=404, detail="Settings not found after update")
            
        if "_id" in updated_settings:
            updated_settings["_id"] = str(updated_settings["_id"])
            
        return updated_settings
        
    except HTTPException as e:
        # Re-raise HTTP exceptions as-is
        raise e
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error updating user settings: {str(e)}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error updating user settings: {str(e)}")

async def fetch_prompt_from_cms(topic_ids: str):
    """Fetch prompt from CMS based on topic IDs"""
    try:
        import aiohttp
        import json

        cms_base_url = os.getenv("CMS_BASE_URL", "http://localhost:3000")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{cms_base_url}/get-prompt", params={"topicIds": topic_ids}) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"CMS Response: {data}")
                    return data
                else:
                    error_text = await response.text()
                    print(f"CMS API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Error from CMS API: {error_text}"
                    )
    except Exception as e:
        print(f"Error fetching prompt from CMS: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching prompt from CMS: {str(e)}")

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True) 