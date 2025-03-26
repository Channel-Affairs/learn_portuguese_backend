# Simple test script for fill-in-the-blank questions
$API_URL = "http://127.0.0.1:8001"

# Create a conversation
Write-Host "Creating a conversation..."
$conversationBody = @{
    title = "Test Conversation"
    description = "Fill in the blank test"
} | ConvertTo-Json

$conversationResponse = Invoke-RestMethod -Uri "$API_URL/api/conversations" -Method Post -ContentType "application/json" -Body $conversationBody
$CONVERSATION_ID = $conversationResponse.conversation_id
Write-Host "Conversation ID: $CONVERSATION_ID"

# Test fill-in-the-blank question generation
Write-Host "Testing fill-in-the-blank question generation..."
$testBody = @{
    conversation_id = $CONVERSATION_ID
    message = "Give me a fill in the blank question about Portuguese verbs"
    topic = "Portuguese verbs"
    num_questions = 1
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody -ErrorAction Stop
    Write-Host "Request successful!"
    Write-Host "Question type: $($response.questions[0].type)"
    Write-Host "Question text: $($response.questions[0].questionText)"
    Write-Host "Question sentence: $($response.questions[0].questionSentence)"
    Write-Host "Number of questions: $($response.questions.Count)"
} catch {
    Write-Host "Error: $_"
    Write-Host "Status code: $($_.Exception.Response.StatusCode.value__)"
    $errorDetails = $_.ErrorDetails.Message
    if ($errorDetails) {
        Write-Host "Error details: $errorDetails"
    }
} 