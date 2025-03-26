# Simple test script for multiple choice questions
$API_URL = "http://127.0.0.1:8001"

# Create a conversation
Write-Host "Creating a conversation..."
$conversationBody = @{
    title = "Test MCQ Conversation"
    description = "Multiple choice test"
} | ConvertTo-Json

$conversationResponse = Invoke-RestMethod -Uri "$API_URL/api/conversations" -Method Post -ContentType "application/json" -Body $conversationBody
$CONVERSATION_ID = $conversationResponse.conversation_id
Write-Host "Conversation ID: $CONVERSATION_ID"

# Test multiple choice question generation
Write-Host "Testing multiple choice question generation..."
$testBody = @{
    conversation_id = $CONVERSATION_ID
    message = "I need multiple choice questions about Portuguese numbers"
    topic = "Portuguese numbers"
    num_questions = 2
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$API_URL/api/process-message" -Method Post -ContentType "application/json" -Body $testBody -ErrorAction Stop
    Write-Host "Request successful!"
    Write-Host "Number of questions: $($response.questions.Count)"
    
    foreach ($question in $response.questions) {
        Write-Host "-------------------------------"
        Write-Host "Question type: $($question.type)"
        Write-Host "Question text: $($question.questionText)"
        Write-Host "Options: $($question.options -join ', ')"
        Write-Host "Correct answers: $($question.correct_answers -join ', ')"
    }
} catch {
    Write-Host "Error: $_"
    Write-Host "Status code: $($_.Exception.Response.StatusCode.value__)"
    $errorDetails = $_.ErrorDetails.Message
    if ($errorDetails) {
        Write-Host "Error details: $errorDetails"
    }
} 