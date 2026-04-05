"""
KYC (Know Your Customer) routes.

Shared KYC payload is used for both staff users and patients.

Endpoints:
- POST /kyc/submit : Submit shared KYC payload for authenticated staff users
- POST /kyc/patients/{patient_id}/submit : Submit shared KYC payload for a patient (by staff)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.jwt_bearer import get_current_user
from dependencies.role_checker import require_role
from models.user import KYCSubmission
from services import firebase_service
from services import patient_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kyc", tags=["KYC"])


@router.post(
    "/submit",
    summary="Submit User KYC Documents",
    description=(
        "Submit shared KYC payload for authenticated staff users. "
        "Allowed when current user KYC status is PENDING or REJECTED."
    ),
)
async def submit_kyc(
    submission: KYCSubmission,
    claims: dict = Depends(get_current_user),
):
    """KYC submission for authenticated users using the shared payload."""
    uid = claims["sub"]

    try:
        user_data = await firebase_service.get_user(uid)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        if submission.uid != uid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payload uid must match authenticated user uid.",
            )

        if submission.role.value == "PATIENT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use /kyc/patients/{patient_id}/submit for patient KYC.",
            )

        current_kyc = user_data.get("kycStatus", "PENDING")
        if current_kyc in ("VERIFIED", "VERIFIED_BY_PROVIDER"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"KYC already verified (status: {current_kyc}). No resubmission needed.",
            )

        is_unique = await firebase_service.check_national_id_unique(
            submission.nationalId,
            exclude_uid=uid,
        )
        if not is_unique:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This National ID is already registered to another user.",
            )

        update_data = {
            "uid": submission.uid,
            "fullName": submission.fullName,
            "nationalId": submission.nationalId,
            "role": submission.role.value,
            "matriculeNumber": submission.matriculeNumber,
            "contactPhone": submission.contactPhone,
            "documentUrl": submission.documentUrl,
            "kycSubmittedAt": firebase_service.utc_now_iso(),
        }

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
            detail="Failed to submit KYC documents.",
        )


@router.post(
    "/patients/{patient_id}/submit",
    summary="Submit Patient KYC Documents",
    description=(
        "Submit shared KYC payload for a patient record. "
        "Accessible to Health Workers and Admins."
    ),
)
async def submit_patient_kyc(
    patient_id: str,
    submission: KYCSubmission,
    current_user: dict = Depends(require_role("HEALTH_WORKER", "ADMIN")),
):
    """KYC submission for patients using the same shared payload."""
    try:
        patient = await patient_service.get_patient(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found: {patient_id}",
            )

        if submission.role.value != "PATIENT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For patient KYC submission, role must be PATIENT.",
            )

        if submission.uid != patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payload uid must match path patient_id.",
            )

        is_unique = await patient_service.check_patient_national_id_unique(
            submission.nationalId,
            exclude_patient_id=patient_id,
        )
        if not is_unique:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This National ID is already registered to another patient.",
            )

        names = submission.fullName.strip().split()
        first_name = names[0] if names else patient.get("firstName")
        last_name = " ".join(names[1:]) if len(names) > 1 else (patient.get("lastName") or "")

        update_data = {
            "fullName": submission.fullName,
            "firstName": first_name,
            "lastName": last_name,
            "nationalId": submission.nationalId,
            "contactPhone": submission.contactPhone,
            "phone": submission.contactPhone,
            "documentUrl": submission.documentUrl,
            "kycRole": submission.role.value,
            "kycSubmittedAt": firebase_service.utc_now_iso(),
            "kycStatus": "SUBMITTED",
            "kycSubmittedBy": current_user.get("uid"),
        }
        if submission.matriculeNumber:
            update_data["matriculeNumber"] = submission.matriculeNumber

        updated_patient = await patient_service.update_patient(patient_id, update_data)

        return {
            "message": "Patient KYC documents submitted successfully. Awaiting verification.",
            "kycStatus": "SUBMITTED",
            "patient": updated_patient,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Patient KYC submission failed for {patient_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit patient KYC documents.",
        )