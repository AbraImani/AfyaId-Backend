"""
JWT Bearer dependency for FastAPI route protection.

Extracts the Bearer token from the Authorization header,
validates it against eSignet's JWKS, and returns the user's sub claim.
All protected routes use this dependency.
"""

import logging
from typing import Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from services.auth_service import validate_access_token

logger = logging.getLogger(__name__)

# FastAPI security scheme — extracts Bearer token from Authorization header
security = HTTPBearer(
    scheme_name="eSignet JWT",
    description="JWT access token obtained from eSignet via /auth/callback"
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """FastAPI dependency that validates the JWT and returns user claims.
    
    Usage in routes:
        @router.get("/protected")
        async def protected_route(user=Depends(get_current_user)):
            uid = user["sub"]
    
    Args:
        credentials: Automatically extracted Bearer token.
    
    Returns:
        Dict of validated JWT claims (always includes 'sub').
    
    Raises:
        HTTPException(401): If token is missing, invalid, or expired.
    """
    token = credentials.credentials.strip()

    # Fail fast on malformed Bearer values to give a clear integration hint.
    if token.count(".") != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Malformed bearer token. Send the 'access_token' returned by /auth/callback "
                "as: Authorization: Bearer <access_token>."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Validate the access token using eSignet's JWKS
        claims = await validate_access_token(token)

        if not claims.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing 'sub' claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return claims

    except JWTError as e:
        logger.error(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
