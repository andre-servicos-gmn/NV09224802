"""Tenant management endpoints."""

from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import datetime
import calendar
import httpx
import os
import uuid

from app.core.supabase_client import get_supabase
from app.core.database import resolve_tenant_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tenants"])


class UpdateTenantRequest(BaseModel):
    tenant_id: str = "73ee1a5c-1160-4a51-ba34-3fdddcd49f9e"
    brand_voice: Optional[str] = None
    active: Optional[bool] = None
    name: Optional[str] = None


class TenantResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class InviteTeamMemberRequest(BaseModel):
    tenant_id: str
    email: str
    name: Optional[str] = None
    password: Optional[str] = None  # If not provided, a random password will be generated


class DeleteUserRequest(BaseModel):
    user_id: str
    tenant_id: str  # For verification


@router.post("/update-tenant", response_model=TenantResponse)
async def update_tenant(request: UpdateTenantRequest):
    """
    Update tenant settings (brand_voice, active status, name).
    """
    tenant_uuid = resolve_tenant_uuid(request.tenant_id)
    supabase = get_supabase()
    
    # Build update payload with only non-None fields
    update_data = {}
    if request.brand_voice is not None:
        update_data["brand_voice"] = request.brand_voice
    if request.active is not None:
        update_data["active"] = request.active
    if request.name is not None:
        update_data["name"] = request.name
    
    if not update_data:
        return TenantResponse(success=False, message="No fields to update")
    
    try:
        result = supabase.table("tenants").update(update_data).eq("id", tenant_uuid).execute()
        
        if not result.data:
            return TenantResponse(success=False, message="Tenant not found")
        
        return TenantResponse(
            success=True,
            message="Tenant updated successfully",
            data=result.data[0] if result.data else None
        )
    except Exception as e:
        logger.error(f"Failed to update tenant: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update tenant: {str(e)}")


@router.get("/tenant/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str):
    """
    Get tenant details.
    """
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    supabase = get_supabase()
    
    try:
        result = supabase.table("tenants").select("id, name, brand_voice, active, settings").eq("id", tenant_uuid).execute()
        
        if not result.data:
            return TenantResponse(success=False, message="Tenant not found")
        
        return TenantResponse(
            success=True,
            message="Tenant found",
            data=result.data[0]
        )
    except Exception as e:
        logger.error(f"Failed to get tenant: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get tenant: {str(e)}")


@router.post("/upload-logo", response_model=TenantResponse)
async def upload_logo(
    file: UploadFile = File(...),
    tenant_id: str = Form(default="73ee1a5c-1160-4a51-ba34-3fdddcd49f9e")
):
    """
    Upload organization logo to 'avatars' bucket and update tenant settings.
    """
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    supabase = get_supabase()
    
    # 1. Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    ext = file.filename.split(".")[-1].lower()
    if ext not in ["jpg", "jpeg", "png", "webp"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use JPG, PNG or WEBP.")
    
    # 2. Upload to Storage
    try:
        content = await file.read()
        filename = f"{tenant_uuid}/logo.{ext}"
        
        # Using the new storage interface
        bucket = supabase.storage.from_("avatars")
        bucket.upload(filename, content, content_type=file.content_type, upsert="true")
        
        public_url = bucket.get_public_url(filename)
        
    except Exception as e:
        logger.error(f"Failed to upload to storage: {e}")
        # Try to create bucket if it fails? (Hard to do via REST without admin rights usually)
        # Assuming bucket exists.
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    # 3. Update Tenant Settings
    try:
        # First get existing settings
        current = supabase.table("tenants").select("settings").eq("id", tenant_uuid).execute()
        settings = current.data[0].get("settings", {}) if current.data else {}
        
        # Update logo_url
        settings["logo_url"] = public_url
        
        # Save back
        result = supabase.table("tenants").update({"settings": settings}).eq("id", tenant_uuid).execute()
        
        return TenantResponse(
            success=True,
            message="Logo updated successfully",
            data={"logo_url": public_url}
        )
        
    except Exception as e:
        logger.error(f"Failed to update tenant settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save logo URL: {str(e)}")


class RemoveLogoRequest(BaseModel):
    tenant_id: str = "73ee1a5c-1160-4a51-ba34-3fdddcd49f9e"


@router.post("/remove-logo", response_model=TenantResponse)
async def remove_logo(request: RemoveLogoRequest):
    """
    Remove organization logo from tenant settings.
    """
    tenant_uuid = resolve_tenant_uuid(request.tenant_id)
    supabase = get_supabase()
    
    try:
        # Get existing settings
        current = supabase.table("tenants").select("settings").eq("id", tenant_uuid).execute()
        settings = current.data[0].get("settings", {}) if current.data else {}
        
        # Remove logo_url
        if "logo_url" in settings:
            del settings["logo_url"]
        
        # Save back
        supabase.table("tenants").update({"settings": settings}).eq("id", tenant_uuid).execute()
        
        return TenantResponse(
            success=True,
            message="Logo removed successfully",
            data={"logo_url": None}
        )
        
    except Exception as e:
        logger.error(f"Failed to remove logo: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove logo: {str(e)}")


@router.get("/tenant/{tenant_id}/team", response_model=TenantResponse)
async def get_team_members(tenant_id: str):
    """
    Get all team members (users) that share the same tenant_id.
    """
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    supabase = get_supabase()
    
    try:
        result = supabase.table("users").select("id, email, name, created_at").eq("tenant_id", tenant_uuid).execute()
        
        team_members = []
        for user in result.data or []:
            team_members.append({
                "id": user.get("id"),
                "email": user.get("email"),
                "name": user.get("name") or user.get("email", "").split("@")[0],
                "role": "Admin",  # Default role for now
                "status": "Ativo",
                "created_at": user.get("created_at")
            })
        
        return TenantResponse(
            success=True,
            message=f"Found {len(team_members)} team members",
            data={"members": team_members}
        )
    except Exception as e:
        logger.error(f"Failed to get team members: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get team members: {str(e)}")


class UpdateUserRequest(BaseModel):
    user_id: str
    name: Optional[str] = None


@router.post("/update-user", response_model=TenantResponse)
async def update_user(request: UpdateUserRequest):
    """
    Update user profile (name) in the users table.
    """
    supabase = get_supabase()
    
    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    
    if not update_data:
        return TenantResponse(success=False, message="No fields to update")
    
    try:
        result = supabase.table("users").update(update_data).eq("id", request.user_id).execute()
        
        if not result.data:
            return TenantResponse(success=False, message="User not found")
        
        return TenantResponse(
            success=True,
            message="User updated successfully",
            data=result.data[0] if result.data else None
        )
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


@router.post("/invite-team-member", response_model=TenantResponse)
async def invite_team_member(request: InviteTeamMemberRequest):
    """
    Invite a new team member using Supabase Auth inviteUserByEmail API.
    Uses the service role key to access Supabase Auth Admin API.
    """
    tenant_uuid = resolve_tenant_uuid(request.tenant_id)
    supabase = get_supabase()
    
    # Get environment variables for Auth Admin API
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not service_key:
        raise HTTPException(status_code=500, detail="Supabase credentials not configured")
    
    try:
        # Use Supabase Auth Admin API to invite user by email
        # POST /auth/v1/invite
        invite_url = f"{supabase_url}/auth/v1/invite"
        
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json"
        }
        
        invite_data = {
            "email": request.email,
            "data": {
                "tenant_id": str(tenant_uuid)
            },
            # Redirect to auth callback page which will handle the invite
            "redirect_to": "http://localhost:3000/auth/callback"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(invite_url, json=invite_data, headers=headers, timeout=30)
            
            if response.status_code not in (200, 201):
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                error_msg = error_data.get("msg") or error_data.get("message") or error_data.get("error_description") or str(error_data)
                
                # Check if user already exists
                if "already been registered" in str(error_msg).lower() or "already exists" in str(error_msg).lower():
                    return TenantResponse(success=False, message="Este email já está registrado no sistema.")
                
                logger.error(f"Invite API error: {response.status_code} - {error_data}")
                raise HTTPException(status_code=400, detail=f"Erro ao enviar convite: {error_msg}")
            
            invite_response = response.json()
            new_user_id = invite_response.get("id")
            
            logger.info(f"User invited successfully: {request.email}, id: {new_user_id}")
        
        # Insert into public.users table if we got a user ID
        if new_user_id:
            user_name = request.email.split("@")[0]
            
            try:
                result = supabase.table("users").insert({
                    "id": new_user_id,
                    "tenant_id": str(tenant_uuid),
                    "email": request.email,
                    "name": user_name
                }).execute()
                
                if not result.data:
                    logger.warning(f"User invited but failed to insert into public.users")
            except Exception as insert_error:
                logger.warning(f"Failed to insert user into public.users: {insert_error}")
        
        return TenantResponse(
            success=True,
            message=f"Convite enviado com sucesso para {request.email}!",
            data={
                "user_id": new_user_id,
                "email": request.email
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invite team member: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao convidar membro: {str(e)}")


@router.post("/delete-user", response_model=TenantResponse)
async def delete_user(request: DeleteUserRequest):
    """
    Delete a user from both public.users and auth.users.
    Uses the service role key to access Supabase Auth Admin API.
    """
    tenant_uuid = resolve_tenant_uuid(request.tenant_id)
    supabase = get_supabase()
    
    # Get environment variables for Auth Admin API
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not service_key:
        raise HTTPException(status_code=500, detail="Supabase credentials not configured")
    
    try:
        # 1. Verify user belongs to this tenant
        user_result = supabase.table("users").select("id, email, tenant_id").eq("id", request.user_id).execute()
        
        if not user_result.data:
            return TenantResponse(success=False, message="Usuário não encontrado.")
        
        user_data = user_result.data[0]
        if user_data.get("tenant_id") != str(tenant_uuid):
            return TenantResponse(success=False, message="Usuário não pertence a esta organização.")
        
        user_email = user_data.get("email", "")
        
        # 2. Delete from public.users table first
        delete_result = supabase.table("users").delete().eq("id", request.user_id).execute()
        
        if not delete_result.data:
            logger.warning(f"Failed to delete user from public.users: {request.user_id}")
        
        # 3. Delete from auth.users using Admin API
        # DELETE /auth/v1/admin/users/{user_id}
        auth_url = f"{supabase_url}/auth/v1/admin/users/{request.user_id}"
        
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(auth_url, headers=headers, timeout=30)
            
            if response.status_code not in (200, 204):
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                error_msg = error_data.get("msg") or error_data.get("message") or str(error_data)
                
                logger.error(f"Auth API delete error: {response.status_code} - {error_data}")
                # User was already deleted from public.users, so warn but don't fail
                return TenantResponse(
                    success=True,
                    message=f"Usuário removido parcialmente. Erro ao remover da autenticação: {error_msg}"
                )
        
        logger.info(f"User deleted successfully: {user_email} ({request.user_id})")
        
        return TenantResponse(
            success=True,
            message=f"Usuário {user_email} removido com sucesso!",
            data={"user_id": request.user_id, "email": user_email}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete user: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao remover usuário: {str(e)}")


def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.1f} {power_labels[n]}B"


@router.get("/tenant/{tenant_id}/usage", response_model=dict)
async def get_usage_stats(tenant_id: str):
    """
    Get usage statistics for the dashboard (messages, storage, team).
    """
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    supabase = get_supabase()
    
    # 1. Date Range (Current Month)
    now = datetime.utcnow()
    last_day = calendar.monthrange(now.year, now.month)[1]
    start_date = datetime(now.year, now.month, 1).isoformat() + "Z"
    end_date = datetime(now.year, now.month, last_day, 23, 59, 59).isoformat() + "Z"
    
    stats = {
        "conversations": 0,
        "max_conversations": 1500, 
        "storage": "0 B",
        "max_storage": "500 MB", 
        "team": 0,
        "max_team": "Illimitado"
    }
    
    try:
        # 1. Conversations Count (Active/Updated in current month)
        # Filter by updated_at in range to show active conversations
        convs = supabase.table("conversations") \
            .select("id", count="exact") \
            .eq("tenant_id", tenant_uuid) \
            .gte("updated_at", start_date) \
            .lte("updated_at", end_date) \
            .execute()
            
        stats["conversations"] = convs.count if convs.count is not None else 0
        
        # 2. Storage Usage (Exact File Size Sum)
        # Fetch metadata to sum distinct file sizes
        # Logic update: Use max(file_size) per source to handle re-uploads where old chunks have 0 size
        kb = supabase.table("knowledge_base").select("metadata").eq("tenant_id", tenant_uuid).execute()
        
        total_bytes = 0
        if kb.data:
            sources_size = {} # source -> max_size
            for row in kb.data:
                meta = row.get("metadata", {})
                if not meta:
                    continue
                
                source = meta.get("source")
                if source:
                    fsize = meta.get("file_size", 0)
                    # Keep the maximum size found for this source (handles mixed valid/invalid chunks)
                    if fsize > sources_size.get(source, -1):
                        sources_size[source] = fsize
            
            total_bytes = sum(sources_size.values())
        
        stats["storage"] = f"{format_bytes(total_bytes)}"
        
        # 3. Team Members
        
        # 3. Team Members
        # Count actual users in this tenant
        members = supabase.table("users").select("id", count="exact").eq("tenant_id", tenant_uuid).execute()
        stats["team"] = members.count if members.count is not None else 1
        
        return {
            "success": True,
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage stats: {e}")
        # Return fallback/empty stats rather than 500
        return {"success": False, "message": str(e), "data": stats}
