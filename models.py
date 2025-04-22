from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal, Dict, Any
import enum
from datetime import datetime

# Define enums and constants
class MessageSenders(str, enum.Enum):
    USER = "User"
    AI = "AI"

class ResponseType(str, enum.Enum):
    TEXT = "text"
    QUESTION = "question"
    CORRECTION = "correction"
    HINT = "hint"
    EXPLANATION = "explanation"
    FEEDBACK = "feedback"

class QuestionTypes(str, enum.Enum):
    FILL_IN_THE_BLANKS = "FillInTheBlanks"
    MULTIPLE_CHOICE = "MultipleChoice"

class DifficultyLevel(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

# Define data models
class TextResponse(BaseModel):
    text: str

class BaseQuestion(BaseModel):
    id: str
    type: QuestionTypes
    questionText: str
    questionDescription: str
    correct_answers: List[str]
    difficulty: DifficultyLevel
    hint: Optional[str] = None

class MultipleChoiceQuestion(BaseQuestion):
    type: Literal[QuestionTypes.MULTIPLE_CHOICE] = QuestionTypes.MULTIPLE_CHOICE
    options: List[str]

class FillInTheBlankQuestion(BaseQuestion):
    type: Literal[QuestionTypes.FILL_IN_THE_BLANKS] = QuestionTypes.FILL_IN_THE_BLANKS
    questionSentence: str
    blankSeparator: str
    numberOfBlanks: int

class QuestionResponse(BaseModel):
    questions: List[Union[MultipleChoiceQuestion, FillInTheBlankQuestion]]

class AIChatResponse(BaseModel):
    id: int
    sender: Literal[MessageSenders.AI] = MessageSenders.AI
    type: ResponseType
    content: str
    payload: Union[TextResponse, QuestionResponse]

class UserChatRequest(BaseModel):
    content: str
    conversation_id: Optional[str] = None

class QuestionRequest(BaseModel):
    num_questions: int = Field(default=2, ge=1, le=5)
    difficulty: Optional[DifficultyLevel] = None
    topic: Optional[str] = "Portuguese language"
    question_types: Optional[List[QuestionTypes]] = None
    conversation_id: Optional[str] = None

# New models for answer evaluation
class UserAnswer(BaseModel):
    """Model for a user's answer to a question"""
    question_id: str
    answer: Union[str, List[str]]
    conversation_id: Optional[str] = None
    question_text: Optional[str] = None  # Add optional question text field

class AnswerEvaluation(BaseModel):
    is_correct: bool
    correct_answer: Union[str, List[str]]
    explanation: Optional[str] = None
    follow_up_hint: Optional[str] = None

class UserAnswerResponse(BaseModel):
    question_id: str
    evaluation: AnswerEvaluation
    next_question: Optional[Union[MultipleChoiceQuestion, FillInTheBlankQuestion]] = None

# New models for conversations
class ConversationCreate(BaseModel):
    title: Optional[str] = "General Chat"
    description: Optional[str] = "General conversation about Portuguese language"
    user_id: Optional[str] = "default_user"
    conversation_id: Optional[str] = None

class ConversationResponse(BaseModel):
    conversation_id: str
    title: str
    description: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = None

class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]

class Message(BaseModel):
    sender: MessageSenders
    content: str
    timestamp: str
    id: Optional[int] = None
    type: Optional[ResponseType] = None
    payload: Optional[Dict[str, Any]] = None

class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    title: str
    description: str
    messages: List[Message]

# New models for conversation context
class GetOrCreateConversation(BaseModel):
    conversation_id: str
    title: Optional[str] = "New Conversation"
    description: Optional[str] = "Conversation about Portuguese"
    user_id: Optional[str] = "default_user"

class ProcessMessage(BaseModel):
    conversation_id: str
    message: str
    topic: Optional[str] = "Portuguese language"
    difficulty: Optional[DifficultyLevel] = DifficultyLevel.MEDIUM
    num_questions: Optional[int] = Field(default=2, ge=1, le=5)

class ProcessMessageResponse(BaseModel):
    type: Literal["text", "question"]
    intent: str
    message: str
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    questions: Optional[Dict[str, List[Dict[str, Any]]]] = None

# User related models
class UserCreate(BaseModel):
    email: str
    username: str
    first_name: str
    last_name: str
    hashed_password: str
    is_active: bool = True

class AppUser(BaseModel):
    _id: Optional[str] = None
    email: str
    username: str
    first_name: str
    last_name: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())

# User Settings models
class UserSettingsCreate(BaseModel):
    user_id: str
    preferred_language: str = "Portuguese"
    notification_enabled: bool = True

class UserSettingsUpdate(BaseModel):
    preferred_language: Optional[str] = None
    notification_enabled: Optional[bool] = None

class UserSettings(BaseModel):
    _id: Optional[str] = None
    user_id: str  # Foreign key to AppUser
    preferred_language: str = "Portuguese"
    notification_enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow()) 