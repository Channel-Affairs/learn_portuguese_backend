#!/bin/bash

# Set API base URL
API_URL="http://127.0.0.1:8000"

# Test get or create conversation endpoint
echo "Testing get-or-create conversation endpoint..."
CONVERSATION_ID="test-$(date +%s)"
echo "Using test conversation ID: $CONVERSATION_ID"

curl -s -X 'POST' \
  "$API_URL/api/conversations/get-or-create" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"title\": \"Test Topic Conversation\",
    \"description\": \"A conversation about Portuguese verbs\"
  }" | jq
echo -e "\n"

# Test processing a general message with topic
echo "Testing process-message endpoint with general chat..."
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"Can you explain Portuguese verb conjugation?\",
    \"topic\": \"Portuguese verb tenses\"
  }" | jq
echo -e "\n"

# Test processing a message with question intent
echo "Testing process-message endpoint with question intent..."
curl -s -X 'POST' \
  "$API_URL/api/process-message" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"message\": \"Can you give me some questions to practice Portuguese verb conjugation?\",
    \"topic\": \"Portuguese verb tenses\",
    \"difficulty\": \"medium\",
    \"num_questions\": 2
  }" | jq
echo -e "\n"

# Test fetching an existing conversation
echo "Testing get-or-create with existing conversation ID..."
curl -s -X 'POST' \
  "$API_URL/api/conversations/get-or-create" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"conversation_id\": \"$CONVERSATION_ID\"
  }" | jq
echo -e "\n"

echo "All tests completed!" 