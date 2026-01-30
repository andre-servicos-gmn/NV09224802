from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from app.core.database import get_client
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])

class CheckEmailRequest(BaseModel):
    email: EmailStr

class CheckEmailResponse(BaseModel):
    exists: bool
    message: Optional[str] = None

@router.post("/check-email", response_model=CheckEmailResponse)
async def check_email(payload: CheckEmailRequest):
    """
    Check if an email exists in the public.users table.
    Used by frontend to validate email before asking for password.
    Note: This endpoint is public.
    """
    try:
        # Query public.users table (using Service Role Key implicitly via supabase client if configured, 
        # or checking if we need to elevate privileges. 
        # app.core.database.supabase usually uses SERVICE_KEY for backend ops)
        
        # We need to ensure we can read users. 
        # If supabase client uses SERVICE_KEY, RLS is bypassed.
        # We need to ensure we can read users. 
        # If supabase client uses SERVICE_KEY, RLS is bypassed.
        result = get_client().table("users").select("id").eq("email", payload.email).execute()
        
        # result.data will be a list of dicts or empty list
        
        exists = len(result.data) > 0
        
        if exists:
            return {"exists": True, "message": "Email found."}
        else:
            return {"exists": False, "message": "Email not found."}
            
    except Exception as e:
        # Log error?
        print(f"Error checking email: {e}")
        # Return false to be safe/fail-closed, or error?
        # User wants error message "Email not found".
        return {"exists": False, "message": "Error checking email."}
