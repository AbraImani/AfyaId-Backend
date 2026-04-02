"""
KYC (Know Your Customer) routes.

Provides endpoints for users to submit identity verification documents
when their identity is NOT verified by the eSignet provider.

Endpoint:
- POST /kyc/submit → Submit KYC documents and profile information
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.jwt_bearer import get_current_user
from services import firebase_service
from models.user import KYCSubmission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kyc", tags=["KYC"])


@router.post(
    "/submit",
    summary="Submit KYC Documents",
    description=(
        "Submit identity documents and professional information for KYC verification. "
        "Required when kycStatus is PENDING (user NOT verified by eSignet provider). "
        "The nationalId field must be unique across all users."
    ),
)
async def submit_kyc(
    submission: KYCSubmission,
    claims: dict = Depends(get_current_user),
):
    """
    KYC submission for unverified users.
    
    Steps:
    1. Validate the user exists and has PENDING KYC status
    2. Check that nationalId is unique across all users (uniqueness constraint)
    3. Update user document with KYC data
    4. Set kycStatus to SUBMITTED (awaiting admin review)
    
    In a production system, this would trigger:
    - Document verification pipeline
    - Admin review queue
    - Automated identity checks
    """
    uid = claims["sub"]

    try:
        # ── Step 1: Fetch existing user ───────────────────────
        user_data = await firebase_service.get_user(uid)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        # Check KYC status — only PENDING or REJECTED users can submit
        current_kyc = user_data.get("kycStatus", "PENDING")
        if current_kyc in ("VERIFIED", "VERIFIED_BY_PROVIDER"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"KYC already verified (status: {current_kyc}). No resubmission needed."
            )

        # ── Step 2: Validate nationalId uniqueness ────────────
        if submission.nationalId:
            is_unique = await firebase_service.check_national_id_unique(
                submission.nationalId,
                exclude_uid=uid
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This National ID is already registered to another user."
                )

        # ── Step 3: Build update data ─────────────────────────
        update_data = {
            "nationalId": submission.nationalId,
            "kycSubmittedAt": firebase_service.utc_now_iso(),
        }

        # Add optional fields if provided
        optional_fields = [
            "hospital", "role", "title", "matriculeNumber",
            "specialty", "unitName", "contactPhone", "documentUrl"
        ]
        for field in optional_fields:
            value = getattr(submission, field, None)
            if value is not None:
                # Convert enum to string for Firestore storage
                update_data[field] = value.value if hasattr(value, "value") else value

        # ── Step 4: Update user in Firestore ──────────────────
        updated_user = await firebase_service.update_kyc_status(
            uid,
            "SUBMITTED",
            additional_data=update_data,
        )

        logger.info(f"KYC submitted for user {uid}. Status: SUBMITTED")

        return {
            "message": "KYC documents submitted successfully. Awaiting verification.",
            "kycStatus": "SUBMITTED",
            "user": updated_user,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KYC submission failed for user {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit KYC documents."
        )
