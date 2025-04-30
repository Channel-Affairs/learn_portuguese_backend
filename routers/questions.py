from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime

# Import models and dependencies
from ..models import (
    MessageSenders, ResponseType, QuestionTypes, 
    QuestionResponse, QuestionRequest, AIChatResponse,
    UserAnswer, AnswerEvaluation, UserAnswerResponse
)
from ..database import MongoDBConversationManager
from ..dependencies import get_current_user, get_next_message_id, create_openai_completion

# Import question generator
from ..question_generator import QuestionGenerator
import os

# Initialize router
router = APIRouter(
    prefix="/api",
    tags=["questions"],
    responses={404: {"description": "Not found"}},
)

# Initialize question generator
openai_api_key = os.getenv("OPENAI_API_KEY")
question_generator = QuestionGenerator(openai_api_key)

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
    from ..main import get_conversation_context
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
        import json
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

# Generate questions endpoint
@router.post("/generate-questions", response_model=AIChatResponse)
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
@router.post("/evaluate-answer", response_model=UserAnswerResponse)
async def evaluate_user_answer(user_answer: UserAnswer):
    """Evaluate user's answer to a question"""
    try:
        return await evaluate_answer(user_answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating answer: {str(e)}") 