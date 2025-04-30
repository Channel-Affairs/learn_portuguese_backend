from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import os
import uuid
from datetime import datetime, timedelta
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import necessary models
from models import AppUser

# Initialize router
router = APIRouter(
    prefix="/api",
    tags=["authentication"],
    responses={404: {"description": "Not found"}},
)

# Initialize password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# User signup schema
class UserSignup(BaseModel):
    email: EmailStr
    username: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

# User signup response
class UserSignupResponse(BaseModel):
    message: str
    user_id: str

# Login schema
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Token schema
class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str
    username: str
    first_name: str
    last_name: str

# Function to create access token
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# User signup endpoint
@router.post("/signup", response_model=UserSignupResponse)
async def signup(user_data: UserSignup):
    """Register a new user"""
    # Get database connection
    from database import db
    
    # Check if email already exists
    existing_user = db.app_users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if username already exists
    existing_username = db.app_users.find_one({"username": user_data.username})
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")

    try:
        # Hash the password
        hashed_password = pwd_context.hash(user_data.password)
        
        # Generate a user ID
        user_id = str(uuid.uuid4())
        
        # Create user object
        new_user = AppUser(
            _id=user_id,
            email=user_data.email,
            username=user_data.username,
            first_name=user_data.first_name or "",
            last_name=user_data.last_name or "",
            hashed_password=hashed_password,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Save user to database using the AppUser model
        user_dict = new_user.dict()
        result = db.app_users.insert_one(user_dict)
        
        # Return success response with the user ID
        return UserSignupResponse(
            message="User successfully created",
            user_id=user_id
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating user: {str(e)}"
        )

# Login endpoint
@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """Authenticate a user and return a JWT token"""
    try:
        # Get database connection
        from database import db
        
        # Find user by email in app_users collection
        user = db.app_users.find_one({"email": user_data.email})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Verify password
        if not pwd_context.verify(user_data.password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Create access token - ensure all data is JSON serializable
        user_id = str(user["_id"])  # Convert ObjectId to string if needed
        
        token_data = {
            "sub": user["email"],
            "user_id": user_id
        }
        token = create_access_token(token_data)
        
        # Return token with user profile data
        return Token(
            access_token=token,
            token_type="bearer",
            user_id=user_id,
            email=user["email"],
            username=user["username"],
            first_name=user["first_name"],
            last_name=user["last_name"]
        )
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Login error: {str(e)}"
        )
