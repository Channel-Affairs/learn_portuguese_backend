from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from fastapi.security import HTTPBearer

# Use MongoDB conversation manager
from database import  initialize_db

# Import auth router
from routers.auth import router as auth_router
from routers.conversations import router as conversations_router
from routers.user import router as user_router
from routers.chat import router as chat_router
# Load environment variables
load_dotenv()

# Set MongoDB connection string from environment or use default
mongodb_uri = os.getenv("MONGO_URI", "mongodb+srv://zainabkhaliq:2pKL3mJgeMsw0HEE@cluster0.qlzi1.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
print(f"Using MongoDB URI: {mongodb_uri[:30]}...")

# Initialize the database with default data
initialize_db()

# We'll use a proper OpenAI client function with error handling
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    print("WARNING: OpenAI API key not found in environment variables. API calls will fail.")

# Initialize FastAPI app
app = FastAPI(
    title="Portagees Chat API", 
    description="API for the Portagees language learning chat application",
    version="1.0.0"
)

# Include the auth router
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(user_router)
app.include_router(chat_router)

# Configure security scheme for Swagger UI
security_scheme = HTTPBearer(
    description="Enter 'Bearer your-token' to authenticate",
    auto_error=False
)

# Add security scheme to OpenAPI
app.swagger_ui_init_oauth = {
    "usePkceWithAuthorizationCodeGrant": True,
    "useBasicAuthenticationWithAccessCodeGrant": True
}

# Add security definitions to OpenAPI schema
app.openapi_schema = None  # Reset schema so it's regenerated with our modifications

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # Get the original openapi schema
    openapi_schema = FastAPI.openapi(app)
    
    # Add security scheme component
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    
    openapi_schema["components"]["securitySchemes"]["Bearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your JWT token in the format: Bearer your-token"
    }
    
    # Add global security requirement
    openapi_schema["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to the Portagees Chat API. Please use the /api endpoints."}
# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "API is running"}

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True) 