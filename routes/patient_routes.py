"""
Patient routes — full CRUD with role-based access control.

Endpoints:
- POST   /patients/register              → Health Worker registers a patient
- PATCH  /patients/{patient_id}          → Update patient data
- GET    /patients/{patient_id}          → Full patient record
- GET    /patients/{patient_id}/summary  → Medical summary (Doctors)
- GET    /patients/{patient_id}/emergency → Emergency data (First Responders)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.role_checker import require_role
from services import patient_service
from services import auth_service
from services import firebase_service
from models.patient import (
    PatientRegisterRequest,
    PatientUpdateRequest,
    PatientModel,
    PatientSummaryResponse,
    PatientEmergencyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post(
    "/{patient_id}/verify/start",
    summary="Start Patient Identity Verification",
    description=(
        "Initiates eSignet identity verification for an existing patient. "
        "Only Health Workers and Admins can initiate this flow."
    ),
)
async def start_patient_verification(
    patient_id: str,
    current_user: dict = Depends(require_role("HEALTH_WORKER", "ADMIN")),
):
    """Create a state-bound eSignet authorization URL for patient verification."""
    try:
        patient = await patient_service.get_patient(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found: {patient_id}",
            )

        authorization_url, state, nonce = await auth_service.build_authorization_url()
        await firebase_service.save_auth_state(
            state=state,
            nonce=nonce,
            flow="patient_identity_verification",
            metadata={
                "patientId": patient_id,
                "initiatedBy": current_user.get("uid"),
            },
        )

        return {
            "message": "Patient verification initiated.",
            "patientId": patient_id,
            "authorization_url": authorization_url,
            "state": state,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate patient verification {patient_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate patient verification.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /patients/register
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/register",
    summary="Register a New Patient",
    description=(
        "Registers a new patient in the system. Only Health Workers and Admins "
        "can register patients. The patient does NOT authenticate directly — "
        "their identity is captured and optionally verified via eSignet workflow."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def register_patient(
    request: PatientRegisterRequest,
    current_user: dict = Depends(require_role("HEALTH_WORKER", "ADMIN")),
):
    """
    Patient registration workflow:

    1. Validate uniqueness of nationalId (if provided)
    2. Validate uniqueness of esignetSubjectId (if provided)
    3. Determine identity/KYC status based on eSignet verification
    4. Create patient record in Firestore 'patients' collection
    5. Link the registering Health Worker's UID to the record

    Request body (PatientRegisterRequest):
        - fullName (required)
        - dateOfBirth, gender, phoneNumber, nationalId, emergencyContact
        - bloodType, allergies, chronicConditions, medications
        - hospital
        - esignetSubjectId (if verified via eSignet)
        - identityVerified (bool — true if eSignet verified)

    Response:
        - 201: Patient created with full record
        - 409: Duplicate nationalId or esignetSubjectId
        - 403: Caller role not authorized
    """
    try:
        # ── Step 1: Check nationalId uniqueness ───────────────
        if request.nationalId:
            is_unique = await patient_service.check_patient_national_id_unique(
                request.nationalId
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This National ID is already registered to another patient.",
                )

        # ── Step 2: Check esignetSubjectId uniqueness ─────────
        if request.esignetSubjectId:
            is_unique = await patient_service.check_esignet_sub_unique(
                request.esignetSubjectId
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A patient with this eSignet identity already exists.",
                )

        # ── Step 3: Determine identity and KYC status ─────────
        if request.identityVerified and request.esignetSubjectId:
            identity_status = "VERIFIED"
            kyc_status = "VERIFIED_BY_PROVIDER"
            registration_source = "esignet"
        else:
            identity_status = "PENDING"
            kyc_status = "PENDING"
            registration_source = "manual"

        # ── Step 4: Build patient data ────────────────────────
        patient_data = request.model_dump(exclude={"identityVerified"})
        patient_data["identityStatus"] = identity_status
        patient_data["kycStatus"] = kyc_status
        patient_data["registrationSource"] = registration_source
        patient_data["registeredBy"] = current_user["uid"]
        patient_data["hospital"] = request.hospital or current_user.get("hospital")

        # ── Step 5: Create in Firestore ───────────────────────
        created_patient = await patient_service.create_patient(patient_data)

        logger.info(
            f"Patient registered by {current_user['uid']}: "
            f"{created_patient['patientId']}"
        )

        return {
            "message": "Patient registered successfully.",
            "patient": created_patient,
            "identity_status": identity_status,
            "kyc_status": kyc_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Patient registration failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register patient.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PATCH /patients/{patient_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.patch(
    "/{patient_id}",
    summary="Update Patient Data",
    description=(
        "Update a patient's record. Only Health Workers and Admins can update. "
        "All fields are optional — only provided fields will be changed."
    ),
)
async def update_patient(
    patient_id: str,
    request: PatientUpdateRequest,
    current_user: dict = Depends(require_role("HEALTH_WORKER", "ADMIN")),
):
    """
    Update patient fields. Validates nationalId and esignetSubjectId
    uniqueness if they are being changed.

    Response:
        - 200: Updated patient record
        - 404: Patient not found
        - 409: Duplicate nationalId or esignetSubjectId
    """
    try:
        # Verify patient exists
        existing = await patient_service.get_patient(patient_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found: {patient_id}",
            )

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update.",
            )

        # Check nationalId uniqueness if it's being changed
        if "nationalId" in update_data:
            is_unique = await patient_service.check_patient_national_id_unique(
                update_data["nationalId"], exclude_patient_id=patient_id
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This National ID is already registered.",
                )

        # Check esignetSubjectId uniqueness if changed
        if "esignetSubjectId" in update_data:
            is_unique = await patient_service.check_esignet_sub_unique(
                update_data["esignetSubjectId"], exclude_patient_id=patient_id
            )
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This eSignet identity is already linked.",
                )

        updated = await patient_service.update_patient(patient_id, update_data)

        logger.info(f"Patient {patient_id} updated by {current_user['uid']}")
        return {
            "message": "Patient updated successfully.",
            "patient": updated,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Patient update failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update patient.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /patients/{patient_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{patient_id}",
    summary="Get Full Patient Record",
    description=(
        "Retrieve the complete patient record. "
        "Accessible by Health Workers, Doctors, and Admins."
    ),
)
async def get_patient(
    patient_id: str,
    current_user: dict = Depends(
        require_role("HEALTH_WORKER", "DOCTOR", "ADMIN")
    ),
):
    """
    Returns the full patient document from Firestore.
    Access is restricted to authorized roles only.

    Response:
        - 200: Full patient record
        - 404: Patient not found
        - 403: Unauthorized role
    """
    try:
        patient_data = await patient_service.get_patient(patient_id)

        if not patient_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found: {patient_id}",
            )

        return {
            "patient": patient_data,
            "accessed_by": current_user["uid"],
            "access_role": current_user.get("role"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient {patient_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch patient data.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /patients/{patient_id}/summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{patient_id}/summary",
    response_model=PatientSummaryResponse,
    summary="Get Patient Medical Summary",
    description=(
        "Returns a medical summary of the patient for care delivery. "
        "Includes demographics, medical history, and medications. "
        "Accessible by Doctors and Admins only."
    ),
)
async def get_patient_summary(
    patient_id: str,
    current_user: dict = Depends(require_role("DOCTOR", "ADMIN")),
):
    """
    Medical summary for Doctors:
    - Name, DOB, gender
    - Blood type, allergies, chronic conditions, medications
    - Emergency contact, hospital
    - Identity verification status

    Response:
        - 200: PatientSummaryResponse
        - 404: Patient not found
    """
    try:
        patient_data = await patient_service.get_patient(patient_id)

        if not patient_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found: {patient_id}",
            )

        summary = patient_service.build_patient_summary(patient_data)
        return PatientSummaryResponse(**summary)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient summary {patient_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch patient summary.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /patients/{patient_id}/emergency
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{patient_id}/emergency",
    response_model=PatientEmergencyResponse,
    summary="Get Patient Emergency Data",
    description=(
        "Returns MINIMAL emergency-critical patient data. "
        "Accessible by First Responders, Doctors, and Admins. "
        "Contains only: name, blood type, allergies, chronic conditions, "
        "emergency contact."
    ),
)
async def get_patient_emergency(
    patient_id: str,
    current_user: dict = Depends(
        require_role("FIRST_RESPONDER", "DOCTOR", "ADMIN")
    ),
):
    """
    Emergency data for First Responders — minimal patient info:
    - Full name
    - Blood type
    - Allergies (critical for emergency treatment)
    - Chronic conditions (e.g. diabetes, heart disease)
    - Emergency contact

    Does NOT include: medications, hospital, registration details,
    identity status, or any administrative fields.

    Response:
        - 200: PatientEmergencyResponse
        - 404: Patient not found
    """
    try:
        patient_data = await patient_service.get_patient(patient_id)

        if not patient_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found: {patient_id}",
            )

        emergency = patient_service.build_patient_emergency(patient_data)
        return PatientEmergencyResponse(**emergency)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching emergency data {patient_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch emergency data.",
        )
