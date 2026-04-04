"""
User profile routes.

Endpoints:
- PATCH /users/me/profile : Update own staff profile
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field

from dependencies.jwt_bearer import get_current_user
from services import firebase_service
from services.auth_service import is_profile_complete
from config.settings import settings
from models.user import ProfileUpdateRequest, UserModel, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


class UserBootstrapRequest(BaseModel):
    """Dev-only request model for manually creating a staff user."""

    uid: str = Field(..., description="User UID (normally OIDC sub)")
    email: Optional[str] = Field(None, description="User email")
    fullName: Optional[str] = Field(None, description="Full name")
    role: Optional[UserRole] = Field(None, description="Staff role")
    hospital: Optional[str] = Field(None, description="Hospital")
    title: Optional[str] = Field(None, description="Professional title")
    matriculeNumber: Optional[str] = Field(None, description="Professional matricule")
    nationalId: Optional[str] = Field(None, description="National ID")
    specialty: Optional[str] = Field(None, description="Medical specialty")
    unitName: Optional[str] = Field(None, description="Hospital unit")
    contactPhone: Optional[str] = Field(None, description="Phone number")
    photoURL: Optional[str] = Field(None, description="Photo URL")
    kycStatus: str = Field("VERIFIED_BY_PROVIDER", description="KYC status")
    provider: str = Field("mock-oidc", description="Identity provider label")
    isActive: bool = Field(True, description="Whether account is active")


@router.post(
    "/bootstrap",
    summary="Bootstrap Staff User (Dev/Mock Only)",
    description=(
        "Creates a staff user directly in Firestore for mock/dev testing. "
        "Disabled in production. Requires X-Bootstrap-Key header equal to APP_SECRET_KEY."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_user(
    request: UserBootstrapRequest,
    x_bootstrap_key: Optional[str] = Header(None, alias="X-Bootstrap-Key"),
):
    """Create a user without OIDC callback for local/mock bootstrapping."""
    try:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User bootstrap is disabled in production.",
            )

        if not x_bootstrap_key or x_bootstrap_key != settings.app_secret_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-Bootstrap-Key.",
            )

        existing = await firebase_service.get_user(request.uid)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User already exists: {request.uid}",
            )

        if request.nationalId:
            is_unique = await firebase_service.check_national_id_unique(request.nationalId)
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This National ID is already registered.",
                )

        payload = request.model_dump()
        if payload.get("role") is not None:
            payload["role"] = payload["role"].value

        created = await firebase_service.create_user(payload)
        return {
            "message": "User bootstrapped successfully.",
            "user": created,
            "profile_complete": is_profile_complete(created),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bootstrap user failed for {request.uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bootstrap user.",
        )


@router.patch(
    "/me/profile",
    summary="Update My Profile",
    description=(
        "Update the currently authenticated user's profile fields. "
        "All fields are optional — only provided fields will be updated. "
        "If 'role' is provided, it must be one of: "
        "ADMIN, DOCTOR, HEALTH_WORKER, FIRST_RESPONDER."
    ),
)
async def update_my_profile(
    request: ProfileUpdateRequest,
    claims: dict = Depends(get_current_user),
):
    """
    Any authenticated staff user can update their own profile.

    Validates:
    - nationalId uniqueness if changed
    - role cannot be changed from this endpoint (admin-only operation)

    Request body (all optional):
        fullName, hospital, role, title, matriculeNumber,
        nationalId, specialty, unitName, contactPhone, photoURL

    Response:
        - 200: Updated user profile
        - 404: User not found
        - 409: Duplicate nationalId
    """
    uid = claims["sub"]

    try:
        user_data = await firebase_service.get_user(uid)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update.",
            )

        if "role" in update_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role changes are restricted to admin endpoints.",
            )

        # Validate nationalId uniqueness if changing
        if "nationalId" in update_data:
            is_unique = await firebase_service.check_national_id_unique(
                update_data["nationalId"], exclude_uid=uid
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This National ID is already registered.",
                )

        updated_user = await firebase_service.update_user(uid, update_data)

        return {
            "message": "Profile updated successfully.",
            "user": updated_user,
            "profile_complete": is_profile_complete(updated_user),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update failed for {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile.",
        )
