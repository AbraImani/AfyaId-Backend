"""
Admin routes for staff governance operations.

Endpoints:
- POST /admin/users
- POST /admin/users/{uid}/role
- POST /admin/users/{uid}/kyc/verify
- POST /admin/users/{uid}/kyc/reject
- GET  /admin/kyc/pending
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies.role_checker import require_role
from services import firebase_service
from services import patient_service
from models.user import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class AssignRoleRequest(BaseModel):
    role: UserRole = Field(..., description="Target staff role")


class VerifyKYCRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Optional reviewer notes")


class RejectKYCRequest(BaseModel):
    reason: str = Field(..., description="Reason for rejection")


class AdminCreateUserRequest(BaseModel):
    uid: str = Field(..., description="User UID (OIDC sub or controlled mock UID)")
    email: Optional[str] = Field(None, description="User email")
    fullName: Optional[str] = Field(None, description="Full name")
    role: Optional[UserRole] = Field(None, description="Target staff role")
    hospital: Optional[str] = Field(None, description="Hospital")
    title: Optional[str] = Field(None, description="Professional title")
    matriculeNumber: Optional[str] = Field(None, description="Professional matricule")
    nationalId: Optional[str] = Field(None, description="National ID")
    specialty: Optional[str] = Field(None, description="Medical specialty")
    unitName: Optional[str] = Field(None, description="Hospital unit")
    contactPhone: Optional[str] = Field(None, description="Phone number")
    photoURL: Optional[str] = Field(None, description="Photo URL")
    kycStatus: str = Field("VERIFIED_BY_PROVIDER", description="Initial KYC status")
    provider: str = Field("mock-oidc", description="Identity provider label")
    isActive: bool = Field(True, description="Whether account is active")


@router.post("/users", summary="Create Staff User (Admin)", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: AdminCreateUserRequest,
    current_admin: dict = Depends(require_role("ADMIN")),
):
    """Create a staff user directly from admin scope (mock/bootstrap workflow)."""
    try:
        existing = await firebase_service.get_user(body.uid)
        if existing:
            raise HTTPException(status_code=409, detail=f"User already exists: {body.uid}")

        if body.nationalId:
            is_unique = await firebase_service.check_national_id_unique(body.nationalId)
            if not is_unique:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This National ID is already registered.",
                )

        payload = body.model_dump()
        if payload.get("role") is not None:
            payload["role"] = payload["role"].value
            payload["roleAssignedBy"] = current_admin["uid"]
            payload["roleAssignedAt"] = firebase_service.utc_now_iso()

        created = await firebase_service.create_user(payload)
        return {
            "message": "User created successfully by admin.",
            "user": created,
            "created_by": current_admin.get("uid"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin create user failed for {body.uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user.",
        )


@router.delete("/patients/{patient_id}", summary="Delete Patient (Admin)")
async def admin_delete_patient(
    patient_id: str,
    current_admin: dict = Depends(require_role("ADMIN")),
):
    try:
        patient = await patient_service.get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")

        await patient_service.delete_patient(patient_id)
        return {
            "message": "Patient deleted successfully.",
            "patient_id": patient_id,
            "deleted_by": current_admin.get("uid"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete patient failed for {patient_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete patient.",
        )


@router.post("/users/{uid}/role", summary="Assign User Role")
async def assign_user_role(
    uid: str,
    body: AssignRoleRequest,
    current_admin: dict = Depends(require_role("ADMIN")),
):
    try:
        target = await firebase_service.get_user(uid)
        if not target:
            raise HTTPException(status_code=404, detail=f"User not found: {uid}")

        updated = await firebase_service.assign_user_role(
            uid=uid,
            role=body.role.value,
            assigned_by=current_admin["uid"],
        )
        return {
            "message": "Role assigned successfully.",
            "user": updated,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assign role failed for {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign role.",
        )


@router.post("/users/{uid}/kyc/verify", summary="Verify User KYC")
async def verify_user_kyc(
    uid: str,
    body: VerifyKYCRequest,
    current_admin: dict = Depends(require_role("ADMIN")),
):
    try:
        updated = await firebase_service.update_kyc_status(
            uid,
            "VERIFIED",
            additional_data={
                "kycReviewedBy": current_admin["uid"],
                "kycReviewedAt": firebase_service.utc_now_iso(),
                "kycReviewNotes": body.notes,
            },
        )
        return {
            "message": "KYC verified successfully.",
            "user": updated,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"KYC verify failed for {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify KYC.",
        )


@router.post("/users/{uid}/kyc/reject", summary="Reject User KYC")
async def reject_user_kyc(
    uid: str,
    body: RejectKYCRequest,
    current_admin: dict = Depends(require_role("ADMIN")),
):
    try:
        updated = await firebase_service.update_kyc_status(
            uid,
            "REJECTED",
            additional_data={
                "kycReviewedBy": current_admin["uid"],
                "kycReviewedAt": firebase_service.utc_now_iso(),
                "kycRejectionReason": body.reason,
            },
        )
        return {
            "message": "KYC rejected.",
            "user": updated,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"KYC reject failed for {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject KYC.",
        )


@router.get("/kyc/pending", summary="List Pending KYC Submissions")
async def list_pending_kyc(
    limit: int = Query(100, ge=1, le=500),
    current_admin: dict = Depends(require_role("ADMIN")),
):
    try:
        users = await firebase_service.list_users_by_kyc_status("SUBMITTED", limit=limit)
        return {
            "count": len(users),
            "items": users,
            "reviewer": current_admin.get("uid"),
        }
    except Exception as e:
        logger.error(f"List pending KYC failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list pending KYC submissions.",
        )
