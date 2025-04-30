from fastapi import HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional
import os

# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"

# Configure security scheme for Swagger UI
security_scheme = HTTPBearer(
    description="Enter 'Bearer your-token' to authenticate",
    auto_error=False
)

# Counter for message IDs
message_counter = 0

# Helper function to get next message ID
def get_next_message_id():
    global message_counter
    message_counter += 1
    return message_counter

# Create a safe OpenAI client function with proper error handling
async def create_openai_completion(messages, model="gpt-3.5-turbo"):
    """Helper function to create OpenAI chat completions without proxy issues"""
    try:
        # Use direct HTTP requests instead of the OpenAI client
        import aiohttp
        import json
        
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": messages
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                result = await response.json()
                
                # Create response object that mimics the OpenAI client response
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    
                    # Create a dummy message object
                    class Message:
                        def __init__(self, content):
                            self.content = content
                    
                    # Create a dummy choice object
                    class Choice:
                        def __init__(self, message):
                            self.message = message
                    
                    # Create a dummy response object
                    class Response:
                        def __init__(self, choices):
                            self.choices = choices
                    
                    # Create and return the response
                    message = Message(content)
                    choice = Choice(message)
                    return Response([choice])
                else:
                    raise Exception(f"Unexpected response format: {result}")
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        # Return a dummy response object for graceful fallback
        class DummyChoice:
            def __init__(self):
                self.message = type('obj', (object,), {
                    'content': f"I couldn't process your request due to a technical issue: {str(e)[:100]}..."
                })
        
        class DummyResponse:
            def __init__(self):
                self.choices = [DummyChoice()]
        
        return DummyResponse()

# Updated get_current_user to use the security scheme
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    authorization: Optional[str] = Header(None)
):
    """
    Authenticate and return the current user based on the JWT token.
    Now accepts tokens from both the HTTPBearer security scheme and Header.
    """
    
    # Try to get token from security scheme first (Swagger UI's Authorization)
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    # Otherwise try the Authorization header
    elif authorization:
        print(f"Authorization header found: {authorization}")
        try:
            scheme, token_value = authorization.split()
            if scheme.lower() != "bearer":
                raise HTTPException(status_code=401, detail="Invalid authentication scheme, must be Bearer")
            token = token_value
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid authorization header format")
    else:
        # Check for token in query parameters as fallback
        token_param = request.query_params.get("token")
        if token_param:
            print(f"Token found in query parameter: {token_param[:10]}...")
            token = token_param
    
    # If still no token, check for cookie
    if not token:
        access_token = request.cookies.get("access_token")
        if access_token:
            print(f"Token found in cookie: {access_token[:10]}...")
            token = access_token
    
    if not token:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated. Please provide a valid Bearer token in Authorization header."
        )
    
    try:
        print(f"Token: {token}")
        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        print(f"User ID: {user_id}")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing user_id")
        
        # Get user from database
        from database import db
        # Try to find user by string ID first
        user = db.app_users.find_one({"_id": user_id})
        
        # If not found, try other possible formats
        if user is None:
            # Try to find by string representation of ID
            try:
                from bson import ObjectId
                # Check if the user_id is a valid ObjectId
                if ObjectId.is_valid(user_id):
                    user = db.app_users.find_one({"_id": ObjectId(user_id)})
            except Exception as e:
                print(f"Error converting to ObjectId: {str(e)}")
        
        if user is None:
            raise HTTPException(status_code=404, detail=f"User not found with ID: {user_id}")
            
        return user
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Authentication error: {str(e)}\n{error_details}")
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")


# Function to check if a query is app-related
def is_app_related_query(query: str) -> bool:
    """
    Check if query is related to Portuguese language learning.
    Short responses like "yes", "no", "maybe" are considered app-related
    as they could be answers to previous questions in conversation.
    """
    # Common short responses should be considered app-related
    # as they're likely responses to previous conversation
    short_responses = [
        "yes", "no", "maybe", "ok", "okay", "sure", 
        "thanks", "thank you", "correct", "incorrect",
        "i do", "i don't", "i can", "i can't", "i cannot",
        "sim", "não", "obrigado", "obrigada", "hello", "hi", "hey"
    ]
    
    query_lower = query.lower().strip()
    
    # If it's a very short answer, consider it app-related
    if query_lower in short_responses or len(query_lower.split()) <= 3:
        return True
    
    # Portuguese language related keywords
    portuguese_keywords = [
        "portuguese", "portugal", "learn", "language", "speak", "words", 
        "grammar", "vocabulary", "phrase", "sentence", "conjugate", "verb",
        "noun", "pronoun", "translation", "meaning", "say", "pronounce"
    ]
    
    # Check if any of the keywords are in the query
    for keyword in portuguese_keywords:
        if keyword in query_lower:
            return True
    
    return False

async def fetch_prompt_from_cms(topic_ids: str):
    """Fetch prompt from CMS based on topic IDs"""
    try:
        import aiohttp
        import json

        cms_base_url = os.getenv("CMS_BASE_URL", "http://localhost:3000/api")
        print(f"Fetching prompt from CMS for topic_ids: {topic_ids}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{cms_base_url}/get-prompt", params={"topicIds": topic_ids}) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"CMS Response: {data}")
                    
                    # Make sure we properly extract the data from the CMS response structure
                    if data.get('success') and data.get('data'):
                        return {
                            'success': True,
                            'data': {
                                'id': data['data'].get('id', ''),
                                'name': data['data'].get('name', 'Portuguese language'),
                                'description': data['data'].get('description', ''),
                                'prompt': data['data'].get('prompt', ''),
                                'examples': data['data'].get('examples', [])
                            }
                        }
                    else:
                        print(f"Warning: CMS response missing expected structure: {data}")
                        return {
                            'success': False,
                            'data': {
                                'name': 'Portuguese language',
                                'prompt': ''
                            }
                        }
                else:
                    error_text = await response.text()
                    print(f"CMS API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Error from CMS API: {error_text}"
                    )
    except Exception as e:
        print(f"Error fetching prompt from CMS: {str(e)}")
        return {
            'success': False,
            'data': {
                'name': 'Portuguese language',
                'prompt': ''
            }
        } 