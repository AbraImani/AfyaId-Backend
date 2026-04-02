"""
Pydantic models for User, KYC submission, and API responses.
These models define the data structures used across the application.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────

class UserRole(str, Enum):
    """Allowed staff roles in the AfyaID system."""
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    HEALTH_WORKER = "HEALTH_WORKER"
    FIRST_RESPONDER = "FIRST_RESPONDER"


class KYCStatus(str, Enum):
    """KYC verification status values."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    VERIFIED_BY_PROVIDER = "VERIFIED_BY_PROVIDER"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# ── User Model (Firestore document schema) ──────────────────────

class UserModel(BaseModel):
    """Full user model matching the Firestore 'users' collection schema.
    Document ID = uid = sub (from eSignet)."""

    uid: str = Field(..., description="Unique ID = sub claim from eSignet")
    email: Optional[str] = Field(None, description="User email from eSignet claims")
    fullName: Optional[str] = Field(None, description="Full name from eSignet claims")
    photoURL: Optional[str] = Field(None, description="Profile photo URL")
    role: Optional[UserRole] = Field(None, description="Staff role (ADMIN, DOCTOR, HEALTH_WORKER, FIRST_RESPONDER)")
    hospital: Optional[str] = Field(None, description="Associated hospital")
    title: Optional[str] = Field(None, description="Professional title")
    matriculeNumber: Optional[str] = Field(None, description="Professional matricule number")
    nationalId: Optional[str] = Field(None, description="National ID (must be unique)")
    specialty: Optional[str] = Field(None, description="Medical specialty")
    unitName: Optional[str] = Field(None, description="Hospital unit name")
    contactPhone: Optional[str] = Field(None, description="Contact phone number")
    isActive: bool = Field(True, description="Whether the account is active")
    createdAt: Optional[str] = Field(None, description="ISO 8601 creation timestamp")
    lastLogin: Optional[str] = Field(None, description="ISO 8601 last login timestamp")
    kycStatus: str = Field(KYCStatus.PENDING, description="KYC verification status")
    provider: str = Field("esignet", description="Identity provider name")


class UserCreateModel(BaseModel):
    """Model for creating a new user with defaults."""
    uid: str
    email: Optional[str] = None
    fullName: Optional[str] = None
    photoURL: Optional[str] = None
    role: Optional[UserRole] = None
    hospital: Optional[str] = None
    title: Optional[str] = None
    matriculeNumber: Optional[str] = None
    nationalId: Optional[str] = None
    specialty: Optional[str] = None
    unitName: Optional[str] = None
    contactPhone: Optional[str] = None
    isActive: bool = True
    createdAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    lastLogin: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    kycStatus: str = KYCStatus.PENDING
    provider: str = "esignet"


# ── KYC Submission Model ────────────────────────────────────────

class KYCSubmission(BaseModel):
    """Request body for POST /kyc/submit endpoint."""
    nationalId: str = Field(..., description="National ID document number")
    hospital: Optional[str] = Field(None, description="Hospital name")
    role: Optional[UserRole] = Field(None, description="Professional role")
    title: Optional[str] = Field(None, description="Professional title")
    matriculeNumber: Optional[str] = Field(None, description="Professional matricule")
    specialty: Optional[str] = Field(None, description="Medical specialty")
    unitName: Optional[str] = Field(None, description="Hospital unit")
    contactPhone: Optional[str] = Field(None, description="Contact phone")
    documentUrl: Optional[str] = Field(None, description="URL to uploaded ID document")


# ── Profile Completion Model ────────────────────────────────────

class ProfileCompletion(BaseModel):
    """Request body for completing profile when KYC is VERIFIED_BY_PROVIDER."""
    hospital: str = Field(..., description="Hospital name (required)")
    role: UserRole = Field(..., description="Staff role (required, must be ADMIN/DOCTOR/HEALTH_WORKER/FIRST_RESPONDER)")
    matriculeNumber: str = Field(..., description="Matricule number (required)")
    title: Optional[str] = None
    specialty: Optional[str] = None
    unitName: Optional[str] = None
    contactPhone: Optional[str] = None


# ── Profile Update Model ────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    """Request body for PATCH /users/me/profile. All fields optional."""
    fullName: Optional[str] = None
    hospital: Optional[str] = None
    role: Optional[UserRole] = None
    title: Optional[str] = None
    matriculeNumber: Optional[str] = None
    nationalId: Optional[str] = None
    specialty: Optional[str] = None
    unitName: Optional[str] = None
    contactPhone: Optional[str] = None
    photoURL: Optional[str] = None


# ── API Response Models ─────────────────────────────────────────

class AuthLoginResponse(BaseModel):
    """Response from GET /auth/login."""
    authorization_url: str
    state: str


class AuthCallbackResponse(BaseModel):
    """Response from GET /auth/callback."""
    access_token: str
    id_token: str
    token_type: str = "Bearer"
    user: UserModel
    kyc_status: str
    profile_complete: bool
    message: str


class UserProfileResponse(BaseModel):
    """Response from GET /auth/me."""
    user: UserModel
    kyc_status: str
    profile_complete: bool
