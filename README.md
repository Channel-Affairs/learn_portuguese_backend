# Portagees Chat API

A FastAPI application that provides a conversational chat API for a Portuguese language learning application. The API integrates with OpenAI to provide informative responses, generate Portuguese language questions, and help users learn Portuguese.

## Key Features

- **MongoDB Integration**: Persistent storage for conversations, messages, grammar rules, and user data
- **Contextual Conversation Management**: Tracks conversation state and history for personalized interactions
- **Grammar Rules API**: Provides hierarchical grammar rules for structured learning
- **Question Generation**: AI-powered generation of Portuguese language exercises
- **Answer Evaluation**: Intelligent assessment of user responses with feedback
- **Adaptive Difficulty**: Adjusts question difficulty based on user performance

## Features

- Conversational chat interface with memory and context tracking
- AI-generated Portuguese language questions (multiple choice and fill in the blanks)
- Answer evaluation and feedback
- Adaptive difficulty based on user performance
- Conversation history tracking
- Different response types (text, questions, hints, explanations, corrections, feedback)
- Only responds to Portuguese language-related queries

## Setup

### Prerequisites

- Python 3.9+ installed on your system
- pip (Python package manager)
- Git (optional, for cloning the repository)

### Step 1: Clone the Repository (Optional)

```bash
git clone https://github.com/yourusername/portagees-app-flask-api.git
cd portagees-app-flask-api
```

### Step 2: Create a Virtual Environment

A virtual environment isolates your project dependencies from other Python projects.

**On macOS/Linux:**
```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

**On Windows:**
```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
venv\Scripts\activate
```

### Step 3: Install Dependencies

With your virtual environment activated, install the required packages:
```bash
pip install -r requirements.txt
```

### Step 4: Set Up Environment Variables

1. Create a `.env` file in the project root directory:
```bash
touch .env
```

2. Add your OpenAI API key and MongoDB URI to the `.env` file:
```
# OpenAI API Key (required)
OPENAI_API_KEY=your_openai_api_key_here

# MongoDB Connection URI (required)
MONGO_URI=mongodb+srv://your_username:your_password@your_cluster.mongodb.net/?retryWrites=true&w=majority

# Server settings
PORT=8000
```

### Step 5: Set Up MongoDB

This application uses MongoDB for persistent storage of conversations and grammar rules.

1. You can use MongoDB Atlas (cloud) or a local MongoDB instance. 

2. For MongoDB Atlas:
   - Create a free account at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
   - Create a new cluster
   - Create a database user with read/write permissions
   - Get your connection string and add it to the `.env` file

3. For local MongoDB:
   - Install MongoDB on your system
   - Start the MongoDB service
   - Use the connection string: `mongodb://localhost:27017` in the `.env` file

The application will automatically:
- Create the necessary collections if they don't exist
- Initialize basic grammar rules if not present
- Create a default user
- Handle connection failures gracefully (falls back to in-memory storage)

### Step 6: Run the API

Start the API server with uvicorn:
```bash
python3 -m uvicorn main:app --reload
```

The API will be available at http://127.0.0.1:8000

You can also run it using the Python script:
```bash
python main.py
```

## Testing the API

You can test the API using the provided test script or with individual curl commands.

### Automated Testing

To run all API tests with a single command, use the test_api.sh script:

```bash
# Make the script executable (only needed once)
chmod +x test_api.sh

# Run the test script
./test_api.sh
```

The script will test all endpoints sequentially and display the results of each request.

### Manual Testing

You can also test individual endpoints using curl commands. Here are some examples:

### 1. Create a new conversation
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/conversations' \
  -H 'accept: application/json'
```

### 2. Send a chat message
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/chat' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "How do I say hello in Portuguese?",
    "conversation_id": "conversation_id_from_step_1"
  }'
```

### 3. Generate questions
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/generate-questions' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "num_questions": 2,
    "difficulty": "easy",
    "topic": "Portuguese vocabulary",
    "conversation_id": "conversation_id_from_step_1"
  }'
```

### 4. Submit an answer for evaluation
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/evaluate-answer' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "question_id": "question_id_from_question_response",
    "answer": "your_answer",
    "conversation_id": "conversation_id_from_step_1"
  }'
```

### 4b. Submit an answer with question text (more reliable)
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/evaluate-answer' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "question_id": "q1",
    "answer": "cachorro",
    "conversation_id": "conversation_id_from_step_1",
    "question_text": "What is the Portuguese word for dog?"
  }'
```

### 5. View conversation history
```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/api/conversations/conversation_id_from_step_1' \
  -H 'accept: application/json'
```

## API Endpoints

### Chat API

- `POST /api/chat`
  - Accepts a user message and returns an AI response
  - Request body: `{"content": "your message here", "conversation_id": "conversation_id"}`
  - Response: AI chat response in JSON format

### Question Generation API

- `POST /api/generate-questions`
  - Generates Portuguese language learning questions
  - Request body:
    ```json
    {
      "num_questions": 2,
      "difficulty": "medium",
      "topic": "Portuguese verbs",
      "question_types": ["MultipleChoice", "FillInTheBlanks"],
      "conversation_id": "conversation_id"
    }
    ```

### Answer Evaluation API

- `POST /api/evaluate-answer`
  - Evaluates a user's answer to a question
  - Request body:
    ```json
    {
      "question_id": "id_of_the_question",
      "answer": "user_answer",
      "conversation_id": "conversation_id",
      "question_text": "What is the Portuguese word for dog?" // Optional but recommended
    }
    ```

### Grammar Rules API

- `GET /api/grammar-rules`
  - Retrieves all grammar rules for displaying in a tree structure
  - Response: List of grammar rules with subtopics
  
- `GET /api/grammar-rules/{rule_id}`
  - Retrieves a specific grammar rule by ID
  - Path parameter: `rule_id`
  - Response: A grammar rule with its subtopics

### Conversation Management API

- `POST /api/conversations`
  - Creates a new conversation
  - Request body:
    ```json
    {
      "title": "Conversation Title",
      "description": "Conversation Description",
      "user_id": "default_user" // Optional, defaults to "default_user"
    }
    ```
  - Response: `{"conversation_id": "new_uuid"}`

- `GET /api/conversations/{conversation_id}`
  - Retrieves conversation history
  - Path parameter: `conversation_id`
  - Query parameter: `limit` (optional, default 50, max 100)
  - Response: Conversation with its messages

- `GET /api/conversations`
  - Lists all conversations for a user
  - Query parameter: `user_id` (optional, default "default_user")
  - Response: List of conversations

### Utility Endpoints

- `GET /` - Welcome message
- `GET /api/health` - Health check endpoint
- `GET /api/test-openai` - Test OpenAI connection
- `GET /docs` - Interactive API documentation (Swagger UI)

## Response Format

The API returns responses in this format:

```json
{
  "id": 1,
  "sender": "AI",
  "type": "text",
  "content": "Summary of response",
  "payload": {
    "text": "Full response text"
  }
}
```

For questions, the format is:

```json
{
  "id": 2,
  "sender": "AI",
  "type": "question",
  "content": "Here are some questions:",
  "payload": {
    "questions": [
      {
        "id": "q1",
        "type": "MultipleChoice",
        "questionText": "What is the capital of Portugal?",
        "questionDescription": "Choose the correct capital city.",
        "options": ["Madrid", "Lisbon", "Porto", "Barcelona"],
        "correct_answers": ["Lisbon"],
        "difficulty": "easy",
        "hint": "It starts with L"
      }
    ]
  }
}
```

## Development

### Project Structure

```
.
├── main.py                 # Main FastAPI application
├── models.py               # Pydantic models for request/response
├── conversation.py         # Conversation context management
├── question_generator.py   # Question generation module
├── database.py             # MongoDB database integration
├── test_api.sh             # API testing script
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this)
└── README.md               # This file
```

### Database Structure

The application uses MongoDB for persistent storage with the following collections:

- **conversations**: Stores conversation metadata (title, description, created_at, updated_at)
- **messages**: Stores all messages within conversations, including user queries and AI responses
- **grammar_rules**: Stores grammar rules with subtopics for the learning tree
- **users**: Stores user information (currently only a default user)

### Managing Dependencies

If you add new dependencies to the project, remember to update requirements.txt:
```bash
pip freeze > requirements.txt
```

### Running Tests

To run tests (once implemented):
```bash
pytest
```

## Troubleshooting

### Common Issues

1. **OpenAI API Key Issues**
   - Ensure your API key is correctly set in the `.env` file
   - Check if your API key has the necessary permissions

2. **Virtual Environment Problems**
   - If you see "command not found" errors, make sure your virtual environment is activated
   - On macOS, you may need to use `python3` instead of `python`

3. **Port Already in Use**
   - If port 8000 is already in use, change the port in `.env` or use the command:
     ```bash
     python3 -m uvicorn main:app --port 8001 --reload
     ```

### Getting Help

If you encounter any issues not covered here, please create an issue on the GitHub repository.

## License

MIT 

## Frontend Integration

This API is designed to work with a frontend application:

1. **Grammar Rules**: When a user arrives on the chat page, the frontend can fetch all grammar rules using `/api/grammar-rules`
   
2. **Conversation Creation**:
   - When a topic or subtopic is clicked in the frontend
   - Generate a unique ID on the frontend based on nesting levels
   - Call `/api/conversations` with the ID, title, and description
   - The API will create the conversation and return the conversation ID
   
3. **Chat Interface**:
   - Use the conversation ID from step 2 for all subsequent requests
   - Send user messages to `/api/chat` with the conversation ID
   - Display AI responses in the appropriate format
   - All messages between user and AI are saved in the conversation history

4. **Access History**:
   - Retrieve conversation history using `/api/conversations/{conversation_id}`
   - List all conversations for a user with `/api/conversations`

## Updated API Endpoints

New endpoints have been added to support the frontend requirements:

### Grammar Rules API

- `GET /api/grammar-rules`
  - Returns all grammar rules for the learning tree
  - Response format: 
    ```json
    {
      "rules": [
        {
          "id": "pronouns",
          "title": "Portuguese Pronouns",
          "description": "Personal pronouns in Portuguese",
          "subtopics": [...]
        }
      ]
    }
    ```

- `GET /api/grammar-rules/{rule_id}`
  - Returns details about a specific grammar rule
  - Path parameter: `rule_id`

### Conversation Management API (Updated)

- `POST /api/conversations`
  - Creates a new conversation with title and description
  - Request body:
    ```json
    {
      "title": "Learning Pronouns",
      "description": "Conversation about Portuguese pronouns",
      "user_id": "default_user" 
    }
    ```
  - Response includes the conversation details with ID

- `GET /api/conversations`
  - Returns all conversations for a user
  - Query parameter: `user_id` (optional, defaults to "default_user")

### Utility Endpoints

- `GET /` - Welcome message
- `GET /api/health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)

## Response Format

The API returns responses in this format:

```json
{
  "id": 1,
  "sender": "AI",
  "type": "text",
  "content": "Summary of response",
  "payload": {
    "text": "Full response text"
  }
}
```

For questions, the format is:

```json
{
  "id": 2,
  "sender": "AI",
  "type": "question",
  "content": "Here are some questions:",
  "payload": {
    "questions": [
      {
        "id": "q1",
        "type": "MultipleChoice",
        "questionText": "What is the capital of Portugal?",
        "questionDescription": "Choose the correct capital city.",
        "options": ["Madrid", "Lisbon", "Porto", "Barcelona"],
        "correct_answers": ["Lisbon"],
        "difficulty": "easy",
        "hint": "It starts with L"
      }
    ]
  }
}
```

## Development

### Project Structure

```
.
├── main.py                 # Main FastAPI application
├── models.py               # Pydantic models for request/response
├── conversation.py         # Conversation context management
├── question_generator.py   # Question generation module
├── database.py             # MongoDB database integration
├── test_api.sh             # API testing script
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this)
└── README.md               # This file
```

### Database Structure

The application uses MongoDB for persistent storage with the following collections:

- **conversations**: Stores conversation metadata (title, description, created_at, updated_at)
- **messages**: Stores all messages within conversations, including user queries and AI responses
- **grammar_rules**: Stores grammar rules with subtopics for the learning tree
- **users**: Stores user information (currently only a default user)

### Managing Dependencies

If you add new dependencies to the project, remember to update requirements.txt:
```bash
pip freeze > requirements.txt
```

### Running Tests

To run tests (once implemented):
```bash
pytest
```

## Troubleshooting

### Common Issues

1. **OpenAI API Key Issues**
   - Ensure your API key is correctly set in the `.env` file
   - Check if your API key has the necessary permissions

2. **Virtual Environment Problems**
   - If you see "command not found" errors, make sure your virtual environment is activated
   - On macOS, you may need to use `python3` instead of `python`

3. **Port Already in Use**
   - If port 8000 is already in use, change the port in `.env` or use the command:
     ```bash
     python3 -m uvicorn main:app --port 8001 --reload
     ```

### Getting Help

If you encounter any issues not covered here, please create an issue on the GitHub repository.

## License

MIT 