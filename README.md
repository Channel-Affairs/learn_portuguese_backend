# Portuguese Learning Platform - Backend

## Introduction

The backend service for the Portuguese Learning Platform provides AI-powered conversation capabilities, question generation, and learning session management. Built with FastAPI, it offers a robust and scalable API for the frontend application.

## Project Description

This backend service implements several key features:

- AI-powered conversation processing using OpenAI's GPT models
- Dynamic question generation for different difficulty levels
- Multiple choice and fill-in-the-blank question types
- Conversation history management with MongoDB
- User progress tracking and answer evaluation
- Intent detection for user queries
- Health monitoring and API testing endpoints

## Installation Instructions

1. Clone the repository:

```bash
git clone git@github.com:zainabkhaliq/portuguese_backend.git
cd portuguese_backend
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Unix or MacOS:
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration:

```
OPENAI_API_KEY=your_openai_api_key
MONGO_URI=your_mongodb_connection_string
```

## Running the Project

### Development Mode

```bash
uvicorn main:app --reload --port 8000
```

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Chat and Conversation

- `POST /api/process-message` - Process messages with topic context
- `POST /api/conversations` - Create new conversations
- `GET /api/conversations/{conversation_id}` - Get conversation history
- `GET /api/conversations` - List all conversations


### System

- `GET /api/health` - Health check endpoint

## Dependencies

- FastAPI 0.104.1
- Uvicorn 0.23.2
- Pydantic 2.4.2
- OpenAI 1.3.0
- Python-dotenv 1.0.0
- MongoDB (via pymongo 4.6.2)
- Additional dependencies listed in requirements.txt

## Special Instructions

### Development Setup

1. Ensure MongoDB is running and accessible
2. Set up your OpenAI API key

### API Documentation

Once the server is running, access the interactive API documentation at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Error Handling

The API implements comprehensive error handling for:

- Invalid API keys
- Database connection issues
- OpenAI API errors
- Invalid user inputs

### Testing

Use the provided test scripts to verify functionality:

```bash
# Test multiple choice questions
./test_mcq.ps1

# Test basic API functionality
./test_simple.ps1

# Test message processing
./test_process_message.ps1
```

## Project Structure

```
portuguese_backend/
├── main.py              # Main FastAPI application
├── models.py            # Pydantic models
├── database.py          # MongoDB connection and operations
├── question_generator.py # Question generation logic
├── fixed_mcqs.py        # Pre-defined multiple choice questions
├── services/            # Business logic services
├── routes/             # API route handlers
├── models/             # Data models
└── requirements.txt    # Project dependencies
```
