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

# Test 1: General chat message
echo "TEST 1: General chat message about Portuguese for tourists"
echo "--------------------------------------------------------"
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

# Test 2: Default fill-in-the-blank questions
echo "TEST 2: Default fill-in-the-blank questions (not specifying question type)"
echo "-----------------------------------------------------------------------"
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"Give me some questions to practice Portuguese greetings\",
    \"topic\": \"Portuguese greetings\",
    \"num_questions\": 3
  }" | jq '.questions | length' | xargs echo "Number of questions received:"
echo

# Test 3: Explicitly requesting multiple choice questions with specific topic
echo "TEST 3: Explicitly requesting multiple choice questions about days of the week"
echo "----------------------------------------------------------------------------"
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"I need multiple choice questions about days of the week in Portuguese\",
    \"topic\": \"Portuguese calendar terms\",
    \"num_questions\": 2
  }" | jq '.questions | map(.type) | unique' | xargs echo "Question types received:"
echo

# Test 4: Explicitly requesting fill-in-the-blank with specific number
echo "TEST 4: Explicitly requesting 4 fill-in-the-blank questions about verbs"
echo "----------------------------------------------------------------------"
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"Give me 4 fill in the blank questions about Portuguese verb conjugation\",
    \"topic\": \"Portuguese verbs\",
    \"num_questions\": 4
  }" | jq '.questions | length' | xargs echo "Number of questions received:"
echo

# Test 5: Test if generated questions are unique
echo "TEST 5: Testing if generated questions are unique"
echo "------------------------------------------------"
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"Test me with fill in the blank questions about Portuguese prepositions\",
    \"topic\": \"Portuguese prepositions\",
    \"num_questions\": 3
  }" | jq '.questions | map(.questionSentence) | unique | length' | xargs echo "Number of unique question sentences:"
echo

echo "All tests completed!" 