from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import uuid
from datetime import datetime

# Import models and dependencies
from ..models import (
    UserSettings, UserSettingsCreate, UserSettingsUpdate
)
from ..dependencies import get_current_user

# Initialize router
router = APIRouter(
    prefix="/api/user",
    tags=["user"],
    responses={404: {"description": "Not found"}},
)

# User settings endpoints
@router.get("/settings", summary="Get user settings")
async def get_user_settings(user=Depends(get_current_user)):
    """Get settings for the current user"""
    try:
        from ..database import db
        user_id = str(user["_id"])
        print(f"Getting settings for user ID: {user_id}")
        
        # Find user settings
        settings = db.user_settings.find_one({"user_id": user_id})
        
        if not settings:
            print(f"No settings found for user ID: {user_id}, returning defaults")
            # Return default settings if none exist
            return UserSettings(
                user_id=user_id,
                preferred_language="Portuguese",
                notification_enabled=True
            )
        
        # Convert MongoDB ObjectId to string
        if "_id" in settings:
            settings["_id"] = str(settings["_id"])
            
        return settings
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error retrieving user settings: {str(e)}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error retrieving user settings: {str(e)}")

@router.post("/settings", summary="Create user settings")
async def create_user_settings(settings_data: UserSettingsCreate, user=Depends(get_current_user)):
    """Create settings for the current user"""
    try:
        from ..database import db
        user_id = str(user["_id"])
        print(f"Creating settings for user ID: {user_id}")
        
        # Check if settings already exist
        existing_settings = db.user_settings.find_one({"user_id": user_id})
        if existing_settings:
            raise HTTPException(status_code=400, detail="Settings already exist for this user. Use PUT to update.")
        
        # Create new settings
        new_settings = UserSettings(
            _id=str(uuid.uuid4()),
            user_id=user_id,
            preferred_language=settings_data.preferred_language,
            notification_enabled=settings_data.notification_enabled,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Insert into database
        settings_dict = new_settings.dict()
        print(f"Inserting new settings: {settings_dict}")
        result = db.user_settings.insert_one(settings_dict)
        print(f"Insert result: {result.inserted_id}")
        
        return new_settings
        
    except HTTPException as e:
        # Re-raise HTTP exceptions as-is
        raise e
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error creating user settings: {str(e)}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error creating user settings: {str(e)}")

@router.put("/settings", summary="Update user settings")
async def update_user_settings(settings_data: UserSettingsUpdate, user=Depends(get_current_user)):
    """Update settings for the current user"""
    try:
        from ..database import db
        user_id = str(user["_id"])
        print(f"Updating settings for user ID: {user_id}")
        
        # Find existing settings
        existing_settings = db.user_settings.find_one({"user_id": user_id})
        print(f"Existing settings found: {existing_settings is not None}")
        
        if not existing_settings:
            # Create new settings if none exist
            settings_id = str(uuid.uuid4())
            new_settings = UserSettings(
                _id=settings_id,
                user_id=user_id,
                preferred_language=settings_data.preferred_language or "Portuguese",
                notification_enabled=settings_data.notification_enabled if settings_data.notification_enabled is not None else True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            settings_dict = new_settings.dict()
            print(f"Creating new settings during update: {settings_dict}")
            result = db.user_settings.insert_one(settings_dict)
            print(f"Insert result: {result.inserted_id}")
            
            # Get the newly created settings
            updated_settings = db.user_settings.find_one({"_id": settings_id})
            if updated_settings is None:
                print(f"Warning: Could not find newly created settings with ID {settings_id}")
                # Return the model we just created as fallback
                return new_settings
                
            if "_id" in updated_settings:
                updated_settings["_id"] = str(updated_settings["_id"])
                
            return updated_settings
        
        # Prepare update data
        update_data = {}
        if settings_data.preferred_language is not None:
            update_data["preferred_language"] = settings_data.preferred_language
        if settings_data.notification_enabled is not None:
            update_data["notification_enabled"] = settings_data.notification_enabled
        
        # Add updated timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        print(f"Updating settings with data: {update_data}")
        
        # Update settings
        update_result = db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        print(f"Update result: matched={update_result.matched_count}, modified={update_result.modified_count}")
        
        # Get updated settings
        updated_settings = db.user_settings.find_one({"user_id": user_id})
        if updated_settings is None:
            raise HTTPException(status_code=404, detail="Settings not found after update")
            
        if "_id" in updated_settings:
            updated_settings["_id"] = str(updated_settings["_id"])
            
        return updated_settings
        
    except HTTPException as e:
        # Re-raise HTTP exceptions as-is
        raise e
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error updating user settings: {str(e)}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error updating user settings: {str(e)}") 