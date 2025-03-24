#!/bin/bash

# Set API base URL
API_URL="http://127.0.0.1:8001"

# Create a test conversation first
echo "Creating a test conversation..."
CONVERSATION_RESPONSE=$(curl -s -X 'POST' \
  "$API_URL/api/conversations" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Test Conversation",
    "description": "Test for process-message endpoint"
  }')

CONVERSATION_ID=$(echo $CONVERSATION_RESPONSE | grep -o '"conversation_id":"[^"]*"' | cut -d'"' -f4)
echo "Conversation ID: $CONVERSATION_ID"
echo

# Test the process-message endpoint with a general chat message
echo "Testing process-message with a general chat message..."
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"I'm planning to visit Portugal next month. Could you tell me some useful Portuguese phrases for tourists?\",
    \"topic\": \"Portuguese for tourists\"
  }" | jq
echo

# Test the process-message endpoint with a question generation message
echo "Testing process-message with a question generation message..."
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"Give me some questions to practice Portuguese greetings\",
    \"topic\": \"Portuguese greetings\",
    \"num_questions\": 2
  }" | jq
echo

echo "Tests completed!" 