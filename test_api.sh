#!/bin/bash

# Set API base URL
API_URL="http://127.0.0.1:8000"

echo "Testing health endpoint..."
curl -s -X 'GET' "$API_URL/api/health" -H 'accept: application/json'
echo -e "\n"

echo "Testing OpenAI connection..."
curl -s -X 'GET' "$API_URL/api/test-openai" -H 'accept: application/json'
echo -e "\n"

echo "Testing grammar rules endpoint..."
curl -s -X 'GET' "$API_URL/api/grammar-rules" -H 'accept: application/json'
echo -e "\n"

# Get a specific grammar rule
echo "Testing specific grammar rule endpoint..."
curl -s -X 'GET' "$API_URL/api/grammar-rules/pronouns" -H 'accept: application/json'
echo -e "\n"

echo "Creating a new conversation..."
CONVERSATION_RESPONSE=$(curl -s -X 'POST' \
  "$API_URL/api/conversations" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Test Conversation",
    "description": "A test conversation created by the test script",
    "user_id": "default_user"
  }')

echo "$CONVERSATION_RESPONSE"
CONVERSATION_ID=$(echo $CONVERSATION_RESPONSE | grep -o '"conversation_id":"[^"]*"' | cut -d'"' -f4)
echo "Conversation ID: $CONVERSATION_ID"
echo -e "\n"

echo "Testing general chat intent..."
curl -s -X 'POST' \
  "$API_URL/api/chat" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"content\": \"I am planning to visit Portugal next summer. Any tips?\",
    \"conversation_id\": \"$CONVERSATION_ID\"
  }"
echo -e "\n\n"

echo "Testing question request intent..."
curl -s -X 'POST' \
  "$API_URL/api/chat" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"content\": \"Can you give me some Portuguese vocabulary exercises to practice?\",
    \"conversation_id\": \"$CONVERSATION_ID\"
  }"
echo -e "\n\n"

echo "Testing generate questions endpoint..."
curl -s -X 'POST' \
  "$API_URL/api/generate-questions" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"num_questions\": 1,
    \"difficulty\": \"easy\",
    \"topic\": \"Portuguese greetings\",
    \"conversation_id\": \"$CONVERSATION_ID\"
  }"
echo -e "\n\n"

echo "Testing evaluate answer endpoint with question text..."
curl -s -X 'POST' \
  "$API_URL/api/evaluate-answer" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"question_id\": \"q1\",
    \"answer\": \"Olá\",
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"question_text\": \"What is 'hello' in Portuguese?\"
  }"
echo -e "\n\n"

echo "Getting conversation history..."
curl -s -X 'GET' \
  "$API_URL/api/conversations/$CONVERSATION_ID" \
  -H 'accept: application/json'
echo -e "\n\n"

echo "Listing all conversations..."
curl -s -X 'GET' \
  "$API_URL/api/conversations" \
  -H 'accept: application/json'
echo -e "\n\n"

echo "All tests completed!" 