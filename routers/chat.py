from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import os
from datetime import datetime
import uuid
from pydantic import BaseModel

# Import models and question generator
from models import (
    MessageSenders, ResponseType, QuestionTypes, MultipleChoiceQuestion, FillInTheBlankQuestion,
    ProcessMessage
)
from question_generator import QuestionGenerator
from database import MongoDBConversationManager
from dependencies import create_openai_completion, get_current_user, fetch_prompt_from_cms
from routers.prompts import ChatPrompts  # Import the centralized prompts

# Initialize router
router = APIRouter(
    prefix="/api",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)

# Initialize question generator
openai_api_key = os.getenv("OPENAI_API_KEY")
question_generator = QuestionGenerator(openai_api_key)

async def extract_user_settings(user):
    """Get user settings from database"""
    from database import db
    user_id = str(user["_id"])
    user_settings = db.user_settings.find_one({"user_id": user_id})
    preferred_language = user_settings.get("preferred_language", "Portuguese") if user_settings else "Portuguese"
    print(f"User Settings: {user_settings}")
    return preferred_language

async def fetch_topic_prompt(topic_ids):
    """Fetch prompt and topic name from CMS"""
    topic_name = "Portuguese language"  # Default topic name
    
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
            cms_prompt = ChatPrompts.default_system_prompt()
    except Exception as e:
        print(f"Error getting prompt from CMS: {str(e)}")
        # Fallback to default prompt if CMS call fails
        cms_prompt = ChatPrompts.default_system_prompt()
    
    return cms_prompt, topic_name

async def detect_intent(user_message, topic_name):
    """Detect user intent from message content"""
    # Prepare prompt for intent detection
    intent_prompt = [
        {"role": "system", "content": ChatPrompts.intent_classification_prompt(topic_name)}
    ]
    
    # Add intent classification examples
    intent_prompt.extend(ChatPrompts.intent_classification_examples())
    
    # Add current user message
    intent_prompt.append({"role": "user", "content": user_message})
    
    # Get intent classification from OpenAI
    intent_response = await create_openai_completion(messages=intent_prompt)
    intent_text = intent_response.choices[0].message.content.strip().lower()
    print(f"Intent detection: '{intent_text}' for message: '{user_message}'")
    
    return intent_text

async def check_short_response_context(user_message, intent_text, conversation_id):
    """Check if a short response is answering a previous question in the conversation"""
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
    
    return intent_text, in_conversation

async def handle_off_topic(user_message, conversation_id, topic_name):
    """Handle off-topic messages with a redirect to Portuguese learning"""
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
        {"role": "system", "content": ChatPrompts.off_topic_redirect_prompt(topic_name)},
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
    
    # Return the response
    result = {
        "type": "text",
        "intent": "off_topic",
        "message": off_topic_response,
        "topic": "Portuguese learning",
        "topic_name": topic_name
    }
    return result

async def extract_question_type(intent_text):
    """Extract question type from intent text"""
    question_type = None
    if "question_generation" in intent_text:
        if ":multiple_choice" in intent_text:
            question_type = [QuestionTypes.MULTIPLE_CHOICE]
            print(f"Multiple choice question type detected")
        else:  # Default to fill in the blanks if multiple choice not specifically requested
            question_type = [QuestionTypes.FILL_IN_THE_BLANKS]
            print(f"Fill in the blanks question type selected (default or requested)")
    return question_type

async def extract_specific_topic(user_message, topic_name):
    """Extract specific topic from user message"""
    # Try to extract a more specific topic from the user message
    topic_extraction_prompt = [
        {"role": "system", "content": ChatPrompts.topic_extraction_prompt(topic_name)}
    ]
    
    # Add topic extraction examples
    topic_extraction_prompt.extend(ChatPrompts.topic_extraction_examples())
    
    # Add current user message
    topic_extraction_prompt.append({"role": "user", "content": user_message})
    
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
    
    return question_topic

async def generate_and_process_questions(
    user_message, 
    conversation_id, 
    question_topic, 
    num_questions, 
    difficulty, 
    question_type, 
    topic_name,
    cms_prompt
):
    """Generate questions and process them for response"""
    print(f"Generating questions with topic={question_topic}, num_questions={num_questions}, difficulty={difficulty}, question_types={question_type}")
    
    # Make sure we convert difficulty to string for the response
    difficulty_str = difficulty.value if hasattr(difficulty, 'value') else difficulty
    
    # Add cms_prompt to the question generation context if available
    if cms_prompt:
        # Configure the question generator with the custom prompt
        question_generator.configure_custom_prompt(
            ChatPrompts.question_generation_prompt(question_topic, cms_prompt)
        )
        print("Using custom CMS prompt for question generation")
    
    try:
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
    finally:
        # Reset the custom prompt after generating questions
        if cms_prompt:
            question_generator.configure_custom_prompt(None)
            print("Reset custom prompt in question generator")
    
    # Process questions for uniqueness and fallbacks
    processed_questions = await process_generated_questions(questions, num_questions, difficulty, question_type, question_topic)
    
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
                "questions": [q.dict() for q in processed_questions]
            }
        }
    )
    
    # Create lists for the response
    all_questions = []
    for q in processed_questions:
        try:
            all_questions.append(q.dict())
        except Exception as e:
            print(f"Error converting question to dict: {str(e)}")
    
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

async def process_generated_questions(questions, num_questions, difficulty, question_type, question_topic):
    """Process generated questions for uniqueness and add fallbacks if needed"""
    if not questions:
        print("Warning: No questions were generated. Using fallback questions.")
        return await generate_fallback_questions(num_questions, difficulty, question_type)
    
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
    # generate more using direct method calls
    unique_questions = await ensure_enough_questions(
        unique_questions, question_texts, num_questions, difficulty, question_type, question_topic
    )
    
    # Ensure we have exactly the right number of questions
    if len(unique_questions) > num_questions:
        unique_questions = unique_questions[:num_questions]
        print(f"Trimmed to exactly {num_questions} questions as requested")
    
    return unique_questions

async def ensure_enough_questions(unique_questions, question_texts, num_questions, difficulty, question_type, question_topic):
    """Ensure we have enough unique questions by generating more if needed"""
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
    
    # If still not enough, add hardcoded questions
    if len(unique_questions) < num_questions:
        if question_type[0] == QuestionTypes.MULTIPLE_CHOICE:
            unique_questions = await add_hardcoded_multiple_choice(unique_questions, num_questions, difficulty)
    
    return unique_questions

async def generate_fallback_questions(num_questions, difficulty, question_type):
    """Generate fallback questions if no questions were generated"""
    fallback_questions = []
    
    if question_type[0] == QuestionTypes.MULTIPLE_CHOICE:
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
            fallback_questions.append(fallback)
    else:
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
            fallback_questions.append(fallback)
    
    return fallback_questions

async def add_hardcoded_multiple_choice(unique_questions, num_questions, difficulty):
    """Add hardcoded multiple choice questions to reach the required number"""
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
    
    return unique_questions

async def handle_general_chat(user_message, conversation_id, topic_name, cms_prompt):
    """Handle general chat interactions"""
    print(f"Processing general chat for topic: {topic_name}")
    
    # Create context with topic to maintain the conversation focus and incorporate CMS prompt
    system_prompt = ChatPrompts.general_chat_prompt(topic_name, cms_prompt)

    # Create context with topic and history
    context_messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Get conversation history to maintain context
    history = MongoDBConversationManager.get_conversation_history(conversation_id)
    print(f"Got history with {len(history)} messages")
    
    # Use all messages for context
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
    
    # Return the response
    result = {
        "type": "text",
        "intent": "general_chat",
        "message": ai_message,
        "topic": topic_name,
        "topic_name": topic_name
    }
    return result

# Process user message with context
@router.post("/process-message", 
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
        
        # Get user settings
        preferred_language = await extract_user_settings(user)
        
        # Get topic prompt from CMS
        cms_prompt, topic_name = await fetch_topic_prompt(topic_ids)
        
        print(f"Process message request: conversation_id={conversation_id}, message='{user_message}', topic_ids='{topic_ids}', preferred_language='{preferred_language}'")
        
        # Detect intent
        intent_text = await detect_intent(user_message, topic_name)
        
        # Check context for short responses
        intent_text, in_conversation = await check_short_response_context(user_message, intent_text, conversation_id)
        
        # Handle off-topic messages
        if intent_text == "off_topic":
            print("Detected off-topic request")
            return await handle_off_topic(user_message, conversation_id, topic_name)
        
        # Determine if this is a question generation request
        is_question_intent = "question_generation" in intent_text
        print(f"Question intent detected: {is_question_intent}, full intent: {intent_text}")
        
        # Extract question type if needed
        question_type = await extract_question_type(intent_text)
        
        if is_question_intent:
            # Extract specific topic from user message
            question_topic = await extract_specific_topic(user_message, topic_name)
            
            # Generate and process questions
            return await generate_and_process_questions(
                user_message, 
                conversation_id, 
                question_topic, 
                num_questions, 
                difficulty, 
                question_type, 
                topic_name,
                cms_prompt
            )
        else:
            # Handle general chat
            return await handle_general_chat(user_message, conversation_id, topic_name, cms_prompt)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error processing message: {str(e)}\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )
