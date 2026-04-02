"""
User profile routes.

Endpoints:
- PATCH /users/me/profile → Update own staff profile
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.jwt_bearer import get_current_user
from services import firebase_service
from services.auth_service import is_profile_complete
from models.user import ProfileUpdateRequest, UserModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


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
