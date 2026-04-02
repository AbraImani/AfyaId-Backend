"""
Authentication routes for eSignet OIDC flow.

Endpoints:
- GET  /auth/login    → Redirect user to eSignet for authentication
- GET  /auth/callback → Handle the callback with authorization code
- GET  /auth/me       → Get current authenticated user profile
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, JSONResponse

from services import auth_service
from services import firebase_service
from services import patient_service
from dependencies.jwt_bearer import get_current_user
from models.user import (
    AuthLoginResponse,
    AuthCallbackResponse,
    UserProfileResponse,
    UserModel,
    ProfileCompletion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /auth/login
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/login",
    response_model=AuthLoginResponse,
    summary="Initiate eSignet Login",
    description=(
        "Builds the eSignet authorization URL and returns it. "
        "The Flutter app should open this URL in a browser/webview. "
        "Pass ?redirect=true to get a 302 redirect instead of JSON."
    ),
)
async def login(redirect: bool = Query(False, description="If true, redirect to eSignet")):
    """
    Step 1 of the OIDC flow.
    
    Builds the authorization URL with:
    - response_type=code
    - scope=openid profile email phone
    - Fresh state and nonce (CSRF + replay protection)
    - claims requesting user attributes
    
    Returns the URL for the Flutter app to redirect the user to eSignet.
    """
    try:
        authorization_url, state, nonce = await auth_service.build_authorization_url()

        await firebase_service.save_auth_state(
            state=state,
            nonce=nonce,
            flow="staff_login",
            metadata={},
        )

        logger.info(f"Login initiated. State: {state}")

        if redirect:
            # Browser redirect mode (for web testing)
            return RedirectResponse(url=authorization_url)

        # JSON mode (for Flutter app)
        return AuthLoginResponse(
            authorization_url=authorization_url,
            state=state
        )

    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build authorization URL: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /auth/callback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/callback",
    summary="eSignet Callback",
    description=(
        "Handles the OIDC callback from eSignet. "
        "Receives the authorization code, exchanges it for tokens, "
        "validates the JWT, fetches userinfo, and creates/updates the user."
    ),
)
async def callback(
    code: str = Query(..., description="Authorization code from eSignet"),
    state: str = Query(..., description="State parameter for CSRF validation"),
    error: str = Query(None, description="Error code from eSignet"),
    error_description: str = Query(None, description="Error description"),
):
    """
    Step 2-3 of the OIDC flow.
    
    1. Validate state parameter (CSRF protection)
    2. Exchange authorization code for tokens (access_token + id_token)
    3. Validate id_token JWT (signature, iss, aud, exp)
    4. Fetch userinfo (name, email, phone, verified status)
    5. Create or update user in Firestore
    6. Determine KYC status
    7. Return tokens + user profile to Flutter
    """
    # ── Handle eSignet errors ─────────────────────────────────
    if error:
        logger.error(f"eSignet returned error: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {error} - {error_description}"
        )

    # ── Validate and consume state parameter (strict CSRF protection) ─────
    state_data = await firebase_service.consume_auth_state(state)
    if not state_data:
        logger.warning(f"Invalid or expired state parameter received: {state}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter."
        )

    nonce = state_data.get("nonce")
    flow = state_data.get("flow", "staff_login")
    metadata = state_data.get("metadata", {})

    try:
        # ── Step 1: Exchange code for tokens ──────────────────
        logger.info("Exchanging authorization code for tokens...")
        token_data = await auth_service.exchange_code_for_tokens(code)

        access_token = token_data["access_token"]
        id_token = token_data["id_token"]

        # ── Step 2: Validate the id_token ────────────────────
        logger.info("Validating id_token...")
        id_claims = await auth_service.validate_id_token(id_token, expected_nonce=nonce)

        # The 'sub' claim is the unique user identifier (pairwise pseudonymous)
        sub = id_claims["sub"]
        logger.info(f"Authenticated user sub: {sub}")

        # ── Step 3: Fetch user claims from userinfo ──────────
        logger.info("Fetching userinfo claims...")
        try:
            userinfo = await auth_service.get_userinfo(access_token)
        except Exception as e:
            logger.warning(f"Userinfo fetch failed, using id_token claims only: {e}")
            userinfo = id_claims  # Fallback to id_token claims

        # ── Patient identity flow callback ────────────────────
        if flow == "patient_identity_verification":
            patient_id = metadata.get("patientId")
            if not patient_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing patient context in state metadata."
                )

            is_unique = await patient_service.check_esignet_sub_unique(
                sub,
                exclude_patient_id=patient_id,
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This eSignet identity is already linked to another patient.",
                )

            existing_patient = await patient_service.get_patient(patient_id)
            if not existing_patient:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Patient not found: {patient_id}",
                )

            provider_kyc_status = auth_service.determine_kyc_status(userinfo)
            identity_status = "VERIFIED" if provider_kyc_status == "VERIFIED_BY_PROVIDER" else "PENDING"
            patient_kyc = "VERIFIED_BY_PROVIDER" if provider_kyc_status == "VERIFIED_BY_PROVIDER" else "PENDING"

            updated_patient = await patient_service.update_patient(
                patient_id,
                {
                    "esignetSubjectId": sub,
                    "identityStatus": identity_status,
                    "kycStatus": patient_kyc,
                    "registrationSource": "esignet",
                },
            )

            return JSONResponse(
                content={
                    "message": (
                        "Patient identity verified successfully."
                        if identity_status == "VERIFIED"
                        else "Patient verification initiated but provider verification is still pending."
                    ),
                    "patient": updated_patient,
                    "identity_status": identity_status,
                    "kyc_status": patient_kyc,
                }
            )

        # ── Step 4: Determine KYC status from userinfo ───────
        kyc_status = auth_service.determine_kyc_status(userinfo)

        # ── Step 5: Create or update user in Firestore ───────
        existing_user = await firebase_service.get_user(sub)

        if existing_user:
            # User exists → update lastLogin only
            logger.info(f"Existing user found: {sub}. Updating lastLogin.")
            await firebase_service.update_last_login(sub)
            user_data = await firebase_service.get_user(sub)
        else:
            # New user → create with defaults
            logger.info(f"New user: {sub}. Creating in Firestore.")
            user_data = {
                "uid": sub,
                "email": userinfo.get("email"),
                "fullName": userinfo.get("name"),
                "photoURL": userinfo.get("picture"),
                "contactPhone": userinfo.get("phone_number"),
                "role": None,
                "hospital": None,
                "title": None,
                "matriculeNumber": None,
                "nationalId": userinfo.get("individual_id"),
                "specialty": None,
                "unitName": None,
                "isActive": True,
                "kycStatus": kyc_status,
                "provider": "esignet",
            }
            user_data = await firebase_service.create_user(user_data)

        # ── Step 6: Build response ───────────────────────────
        profile_complete = auth_service.is_profile_complete(user_data)

        # Build user model for response — safely handle enum fields
        user_fields = {}
        for k in UserModel.model_fields.keys():
            if k in user_data:
                user_fields[k] = user_data[k]
        user_model = UserModel.model_validate(user_fields)

        # Determine appropriate message
        if kyc_status == "VERIFIED_BY_PROVIDER" and not profile_complete:
            message = "Identity verified by provider. Please complete your profile (hospital, role, matriculeNumber)."
        elif kyc_status == "PENDING":
            message = "Please submit your identity documents via POST /kyc/submit."
        else:
            message = "Authentication successful."

        response_data = {
            "access_token": access_token,
            "id_token": id_token,
            "token_type": "Bearer",
            "user": user_model.model_dump(),
            "kyc_status": user_data.get("kycStatus", kyc_status),
            "profile_complete": profile_complete,
            "message": message,
        }

        logger.info(f"Callback completed for user {sub}. KYC: {kyc_status}")
        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Callback processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication processing failed: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /auth/me
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get Current User",
    description="Returns the profile of the currently authenticated user.",
)
async def get_me(claims: dict = Depends(get_current_user)):
    """
    Protected endpoint — requires valid JWT Bearer token.
    
    Extracts 'sub' from the validated token, fetches the user
    from Firestore, and returns the full profile with KYC status.
    """
    uid = claims["sub"]

    try:
        user_data = await firebase_service.get_user(uid)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {uid}"
            )

        user_model = UserModel.model_validate({
            k: user_data.get(k)
            for k in UserModel.model_fields.keys()
            if k in user_data
        })

        return UserProfileResponse(
            user=user_model,
            kyc_status=user_data.get("kycStatus", "PENDING"),
            profile_complete=auth_service.is_profile_complete(user_data),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user profile."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /auth/complete-profile
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/complete-profile",
    summary="Complete Profile",
    description=(
        "For users with kycStatus=VERIFIED_BY_PROVIDER. "
        "Requires hospital, role, and matriculeNumber."
    ),
)
async def complete_profile(
    profile: ProfileCompletion,
    claims: dict = Depends(get_current_user),
):
    """
    When eSignet verifies the user (kycStatus=VERIFIED_BY_PROVIDER),
    they still need to provide professional details.
    """
    uid = claims["sub"]

    try:
        user_data = await firebase_service.get_user(uid)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        if user_data.get("kycStatus") != "VERIFIED_BY_PROVIDER":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile completion is only for provider-verified users."
            )

        # Update the profile fields — convert role enum to string for Firestore
        update_data = profile.model_dump(exclude_none=True)
        if "role" in update_data and hasattr(update_data["role"], "value"):
            update_data["role"] = update_data["role"].value
        updated_user = await firebase_service.update_user(uid, update_data)

        return {
            "message": "Profile completed successfully.",
            "user": updated_user,
            "profile_complete": auth_service.is_profile_complete(updated_user),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete profile."
        )
