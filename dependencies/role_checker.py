"""
Role-based access control dependency for FastAPI routes.

Provides a dependency factory that checks the authenticated user's role
against a list of allowed roles. Fetches the user from Firestore to get
the current role (not just from the JWT, which may not contain role info).
"""

import logging
from typing import List, Dict, Any, Callable

from fastapi import Depends, HTTPException, status

from dependencies.jwt_bearer import get_current_user
from services import firebase_service

logger = logging.getLogger(__name__)


def require_role(*allowed_roles: str) -> Callable:
    """Factory that creates a FastAPI dependency requiring specific roles.

    Usage:
        @router.get("/admin-only")
        async def admin_route(user=Depends(require_role("ADMIN"))):
            ...

        @router.post("/patients/register")
        async def register(user=Depends(require_role("HEALTH_WORKER", "ADMIN"))):
            ...

    Args:
        *allowed_roles: One or more role strings that are permitted.

    Returns:
        A FastAPI dependency function that validates the user's role.
    """

    async def role_dependency(
        claims: dict = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """Validate that the authenticated user has an allowed role.

        Steps:
        1. Extract 'sub' from the validated JWT claims
        2. Fetch the user document from Firestore
        3. Check that the user's role is in the allowed list
        4. Return the full user data dict (so routes don't re-fetch)

        Raises:
            HTTPException(404): If user not found in Firestore
            HTTPException(403): If user's role is not in allowed_roles
            HTTPException(403): If user has no role assigned yet
        """
        uid = claims["sub"]

        # Fetch user from Firestore to get current role
        user_data = await firebase_service.get_user(uid)

        if not user_data:
            logger.warning(f"Role check failed: user {uid} not found in Firestore")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please complete authentication first.",
            )

        user_role = user_data.get("role")

        if not user_role:
            logger.warning(f"Role check failed: user {uid} has no role assigned")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "No role assigned. Please complete your profile with a valid role "
                    "via POST /auth/complete-profile or PATCH /users/me/profile."
                ),
            )

        if user_role not in allowed_roles:
            logger.warning(
                f"Role check failed: user {uid} has role '{user_role}', "
                f"required one of {list(allowed_roles)}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Your role '{user_role}' is not authorized "
                    f"for this action. Required: {list(allowed_roles)}"
                ),
            )

        logger.info(f"Role check passed: user {uid} has role '{user_role}'")

        # Merge JWT claims with user data so the route has everything
        user_data["_jwt_claims"] = claims
        return user_data

    return role_dependency
