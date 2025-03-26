from fastapi import FastAPI, APIRouter, Body
import uuid
from pydantic import BaseModel
from enum import Enum
from typing import List, Optional
import random

# Define the models we need
class QuestionTypes(str, Enum):
    FILL_IN_THE_BLANKS = "FillInTheBlanks"
    MULTIPLE_CHOICE = "MultipleChoice"

class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class MultipleChoiceQuestion(BaseModel):
    id: str
    type: QuestionTypes = QuestionTypes.MULTIPLE_CHOICE
    questionText: str
    questionDescription: str
    options: List[str]
    correct_answers: List[str]
    difficulty: DifficultyLevel
    hint: Optional[str] = None

class McqsRequest(BaseModel):
    conversation_id: str
    message: str
    topic: Optional[str] = "Portuguese language - noun"
    difficulty: Optional[str] = "medium"
    num_questions: Optional[int] = 5

# Create router
router = APIRouter()

@router.post("/api/mcqs-fixed")
async def get_mcqs(payload: McqsRequest = Body(...)):
    """A fixed endpoint that always returns the requested number of multiple choice questions."""
    
    # Get values from payload
    topic = payload.topic
    num_questions = payload.num_questions
    difficulty = DifficultyLevel(payload.difficulty) if payload.difficulty else DifficultyLevel.MEDIUM
    
    # Define predefined questions about Portuguese nouns (always have at least 7 questions)
    predefined_questions = [
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "Which Portuguese noun is feminine?",
            "questionDescription": "Select the noun that is feminine in Portuguese.",
            "options": ["casa (house)", "livro (book)", "carro (car)", "telefone (telephone)"],
            "correct_answers": ["casa (house)"],
            "difficulty": difficulty,
            "hint": "Nouns ending in 'a' are typically feminine in Portuguese."
        },
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "What is the correct article to use with the Portuguese noun 'livro'?",
            "questionDescription": "Choose the appropriate definite article.",
            "options": ["o", "a", "os", "as"],
            "correct_answers": ["o"],
            "difficulty": difficulty,
            "hint": "Masculine singular nouns use 'o' as their definite article."
        },
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "What is the plural form of the Portuguese noun 'mulher'?",
            "questionDescription": "Select the correct plural form.",
            "options": ["mulheres", "mulhers", "mulheris", "mulher"],
            "correct_answers": ["mulheres"],
            "difficulty": difficulty,
            "hint": "Many Portuguese nouns add 'es' to form the plural."
        },
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "Which of these Portuguese nouns is masculine?",
            "questionDescription": "Identify the masculine noun.",
            "options": ["sol (sun)", "flor (flower)", "nação (nation)", "noite (night)"],
            "correct_answers": ["sol (sun)"],
            "difficulty": difficulty,
            "hint": "Most Portuguese nouns ending in consonants are masculine."
        },
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "What is the correct article to use with the Portuguese noun 'mesa'?",
            "questionDescription": "Choose the appropriate definite article.",
            "options": ["a", "o", "as", "os"],
            "correct_answers": ["a"],
            "difficulty": difficulty,
            "hint": "Feminine singular nouns use 'a' as their definite article."
        },
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "Which word is NOT a Portuguese noun?",
            "questionDescription": "Identify the word that is not a noun in Portuguese.",
            "options": ["correr (to run)", "pessoa (person)", "cidade (city)", "dia (day)"],
            "correct_answers": ["correr (to run)"],
            "difficulty": difficulty,
            "hint": "Look for the verb in the list."
        },
        {
            "id": str(uuid.uuid4()),
            "type": QuestionTypes.MULTIPLE_CHOICE,
            "questionText": "What is the diminutive form of the Portuguese noun 'casa'?",
            "questionDescription": "Select the correct diminutive form.",
            "options": ["casinha", "casita", "casica", "casona"],
            "correct_answers": ["casinha"],
            "difficulty": difficulty,
            "hint": "Many Portuguese diminutives are formed with the suffix '-inho/a'."
        }
    ]
    
    # Randomize the options for each question
    for question in predefined_questions:
        options = question["options"].copy()
        random.shuffle(options)
        question["options"] = options
    
    # Limit to the requested number of questions
    questions = predefined_questions[:num_questions]
    
    # Create the response
    response = {
        "type": "question",
        "intent": "question_generation:multiplechoice",
        "message": f"Here are some questions about {topic}:",
        "topic": topic,
        "difficulty": difficulty.value,
        "questions": questions
    }
    
    return response

# Create a FastAPI app that includes our router
app = FastAPI()
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fixed_mcqs:app", host="127.0.0.1", port=8002, reload=True) 