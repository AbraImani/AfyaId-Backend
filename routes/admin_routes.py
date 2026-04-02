"""
Admin routes for staff governance operations.

Endpoints:
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
from models.user import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class AssignRoleRequest(BaseModel):
    role: UserRole = Field(..., description="Target staff role")


class VerifyKYCRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Optional reviewer notes")


class RejectKYCRequest(BaseModel):
    reason: str = Field(..., description="Reason for rejection")


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
