# PowerShell script to test the process-message endpoint

# Set API base URL
$API_URL = "http://127.0.0.1:8001"

# Create a test conversation first
Write-Host "Creating a test conversation..."
$conversationBody = @{
    title = "Test Conversation"
    description = "Test for process-message endpoint"
} | ConvertTo-Json

$conversationResponse = Invoke-RestMethod -Uri "$API_URL/api/conversations" -Method Post -ContentType "application/json" -Body $conversationBody
$CONVERSATION_ID = $conversationResponse.conversation_id
Write-Host "Conversation ID: $CONVERSATION_ID"
Write-Host ""

# Test 1: General chat message
Write-Host "TEST 1: General chat message about Portuguese for tourists"
Write-Host "--------------------------------------------------------"
$testBody1 = @{
    conversation_id = $CONVERSATION_ID
    message = "I'm planning to visit Portugal next month. Could you tell me some useful Portuguese phrases for tourists?"
    topic = "Portuguese for tourists"
} | ConvertTo-Json

$response1 = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody1
Write-Host "Response type: $($response1.type)"
Write-Host "Topic: $($response1.topic)"
Write-Host ""

# Test 2: Default fill-in-the-blank questions
Write-Host "TEST 2: Default fill-in-the-blank questions (not specifying question type)"
Write-Host "-----------------------------------------------------------------------"
$testBody2 = @{
    conversation_id = $CONVERSATION_ID
    message = "Give me some questions to practice Portuguese greetings"
    topic = "Portuguese greetings"
    num_questions = 3
} | ConvertTo-Json

$response2 = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody2
Write-Host "Number of questions received: $($response2.questions.Count)"
Write-Host "Question type: $($response2.questions[0].type)"
Write-Host ""

# Test 3: Explicitly requesting multiple choice questions with specific topic
Write-Host "TEST 3: Explicitly requesting multiple choice questions about days of the week"
Write-Host "----------------------------------------------------------------------------"
$testBody3 = @{
    conversation_id = $CONVERSATION_ID
    message = "I need multiple choice questions about days of the week in Portuguese"
    topic = "Portuguese calendar terms"
    num_questions = 2
} | ConvertTo-Json

$response3 = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody3
Write-Host "Number of questions received: $($response3.questions.Count)"
Write-Host "Question type: $($response3.questions[0].type)"
Write-Host ""

# Test 4: Explicitly requesting fill-in-the-blank with specific number
Write-Host "TEST 4: Explicitly requesting 4 fill-in-the-blank questions about verbs"
Write-Host "----------------------------------------------------------------------"
$testBody4 = @{
    conversation_id = $CONVERSATION_ID
    message = "Give me 4 fill in the blank questions about Portuguese verb conjugation"
    topic = "Portuguese verbs"
    num_questions = 4
} | ConvertTo-Json

$response4 = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody4
Write-Host "Number of questions received: $($response4.questions.Count)"
Write-Host "Question type: $($response4.questions[0].type)"
Write-Host ""

# Test 5: Test if generated questions are unique
Write-Host "TEST 5: Testing if generated questions are unique"
Write-Host "------------------------------------------------"
$testBody5 = @{
    conversation_id = $CONVERSATION_ID
    message = "Test me with fill in the blank questions about Portuguese prepositions"
    topic = "Portuguese prepositions"
    num_questions = 3
} | ConvertTo-Json

$response5 = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody5
$uniqueQuestions = $response5.questions | Select-Object -Property questionSentence -Unique
Write-Host "Total questions: $($response5.questions.Count)"
Write-Host "Unique questions: $($uniqueQuestions.Count)"
Write-Host ""

Write-Host "All tests completed!" 