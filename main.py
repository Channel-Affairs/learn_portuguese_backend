from fastapi import FastAPI, HTTPException, Depends, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import os
from dotenv import load_dotenv
import openai
import json
import uuid
from datetime import datetime

# Import models and question generator
from models import (
    MessageSenders, ResponseType, QuestionTypes, DifficultyLevel,
    TextResponse, BaseQuestion, MultipleChoiceQuestion, FillInTheBlankQuestion,
    QuestionResponse, AIChatResponse, UserChatRequest, QuestionRequest,
    UserAnswer, AnswerEvaluation, UserAnswerResponse, GrammarRule, 
    GrammarRuleResponse, ConversationCreate, ConversationResponse,
    ConversationListResponse, Message, ConversationHistoryResponse,
    GetOrCreateConversation, ProcessMessage, ProcessMessageResponse
)
from question_generator import QuestionGenerator
# Use MongoDB conversation manager
from database import MongoDBConversationManager, GrammarRulesManager, MongoJSONEncoder, initialize_db

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
app = FastAPI(title="Portagees Chat API", description="API for the Portagees language learning chat application")

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
        {"role": "system", "content": "You are an AI assistant that can detect user intent. Your task is to classify if the user is asking for practice exercises/quiz/questions to test their knowledge, or if they're having a general conversation seeking information. When the user wants a quiz or exercises to practice Portuguese, classify as 'question_generation'. For general information or conversation, classify as 'general_chat'. Respond with ONLY 'question_generation' or 'general_chat'."},
        {"role": "user", "content": "Give me a quiz about Portuguese verbs"},
        {"role": "assistant", "content": "question_generation"},
        {"role": "user", "content": "How do you say 'hello' in Portuguese?"},
        {"role": "assistant", "content": "general_chat"},
        {"role": "user", "content": "I need practice questions for Portuguese vocabulary"},
        {"role": "assistant", "content": "question_generation"},
        {"role": "user", "content": "Can you tell me about Portugal's history?"},
        {"role": "assistant", "content": "general_chat"},
        {"role": "user", "content": user_message}
    ]
    
    # Get intent classification from OpenAI
    intent_response = await create_openai_completion(messages=intent_prompt)
    intent_text = intent_response.choices[0].message.content.strip().lower()
    print(f"Intent detection: '{intent_text}' for message: '{user_message}'")
    
    # Determine if this is a question generation request
    is_question_intent = intent_text == "question_generation"
    
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
            "difficulty": difficulty
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
            question_types=intent.get("question_types", ["MultipleChoice", "FillInTheBlanks"])
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

# Get grammar rules endpoint
@app.get("/api/grammar-rules", response_model=GrammarRuleResponse)
async def get_grammar_rules():
    """Get all grammar rules"""
    try:
        grammar_rules = GrammarRulesManager.get_all_grammar_rules()
        return GrammarRuleResponse(rules=grammar_rules)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving grammar rules: {str(e)}")

# Get specific grammar rule
@app.get("/api/grammar-rules/{rule_id}")
async def get_grammar_rule(rule_id: str):
    """Get a specific grammar rule by ID"""
    try:
        rule = GrammarRulesManager.get_grammar_rule(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Grammar rule with ID {rule_id} not found")
        return rule
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving grammar rule: {str(e)}")

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
        
        # Use OpenAI to detect intent rather than keywords
        intent_prompt = [
            {"role": "system", "content": "You are an AI assistant that can detect user intent. Your task is to classify if the user is asking for practice exercises/quiz/questions to test their knowledge, or if they're having a general conversation seeking information. When the user wants a quiz or exercises to practice Portuguese, classify as 'question_generation'. For general information or conversation, classify as 'general_chat'. Respond with ONLY 'question_generation' or 'general_chat'."},
            {"role": "user", "content": "Give me a quiz about Portuguese verbs"},
            {"role": "assistant", "content": "question_generation"},
            {"role": "user", "content": "How do you say 'hello' in Portuguese?"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": "I need practice questions for Portuguese vocabulary"},
            {"role": "assistant", "content": "question_generation"},
            {"role": "user", "content": "Can you tell me about Portugal's history?"},
            {"role": "assistant", "content": "general_chat"},
            {"role": "user", "content": user_message}
        ]
        
        # Get intent classification from OpenAI
        intent_response = await create_openai_completion(messages=intent_prompt)
        intent_text = intent_response.choices[0].message.content.strip().lower()
        print(f"Intent detection: '{intent_text}' for message: '{user_message}'")
        
        # Determine if this is a question generation request
        is_question_intent = intent_text == "question_generation"
        
        if is_question_intent:
            # Generate questions
            difficulty = message_data.difficulty
            num_questions = message_data.num_questions
            
            try:
                # Debug prints
                print(f"Generating questions with topic={topic}, num_questions={num_questions}, difficulty={difficulty}")
                
                # Make sure we convert difficulty to string for the response
                difficulty_str = difficulty.value if hasattr(difficulty, 'value') else difficulty
                
                # Generate only fill in the blank questions for simplicity
                print("Generating Fill In The Blanks questions only")
                questions = question_generator.generate_questions(
                    topic=topic,
                    num_questions=num_questions,
                    difficulty=difficulty,
                    question_types=[QuestionTypes.FILL_IN_THE_BLANKS]
                )
                
                print(f"Generated {len(questions)} questions")
                
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
                response_content = f"Here are some questions about {topic}:"
                MongoDBConversationManager.add_message(
                    conversation_id=conversation_id,
                    message={
                        "sender": MessageSenders.AI,
                        "content": response_content,
                        "timestamp": datetime.now().isoformat(),
                        "type": ResponseType.QUESTION,
                        "payload": {
                            "questions": [q.dict() for q in questions]
                        }
                    }
                )
                
                # Create lists for the response
                all_questions = []
                for q in questions:
                    try:
                        all_questions.append(q.dict())
                    except Exception as e:
                        print(f"Error converting question to dict: {str(e)}")
                
                # Return the questions in a simplified JSON format
                result = {
                    "type": "question",
                    "intent": "question_generation",
                    "message": response_content,
                    "topic": topic,
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
            context_messages = [
                {"role": "system", "content": f"You are a Portuguese language assistant. The user is studying about '{topic}'. Keep your responses focused on this topic when relevant."}
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

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True) 