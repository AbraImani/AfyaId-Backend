"""
Pydantic models for the Patient collection and related API contracts.

Patients are separate from staff users:
- Patients do NOT authenticate directly
- They are registered/verified by Health Workers
- Their identity may be verified through eSignet workflows
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ── Identity / KYC Status Enums ─────────────────────────────────

class IdentityStatus(str, Enum):
    """Patient identity verification status."""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class PatientKYCStatus(str, Enum):
    """Patient KYC status."""
    PENDING = "PENDING"
    VERIFIED_BY_PROVIDER = "VERIFIED_BY_PROVIDER"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# ── Patient Firestore Model ────────────────────────────────────

class PatientModel(BaseModel):
    """Full patient model matching the Firestore 'patients' collection.

    Document ID = patientId (auto-generated or derived from esignetSubjectId).
    """

    patientId: str = Field(..., description="Unique patient document ID")
    esignetSubjectId: Optional[str] = Field(
        None,
        description="eSignet 'sub' claim if identity was verified via eSignet"
    )
    fullName: str = Field(..., description="Patient full name")
    dateOfBirth: Optional[str] = Field(None, description="ISO date of birth")
    gender: Optional[str] = Field(None, description="Gender")
    phoneNumber: Optional[str] = Field(None, description="Phone number")
    nationalId: Optional[str] = Field(None, description="National ID (unique)")
    emergencyContact: Optional[str] = Field(
        None, description="Emergency contact name and phone"
    )
    bloodType: Optional[str] = Field(None, description="Blood type (e.g. A+)")
    allergies: Optional[List[str]] = Field(
        default_factory=list, description="Known allergies"
    )
    chronicConditions: Optional[List[str]] = Field(
        default_factory=list, description="Chronic conditions"
    )
    medications: Optional[List[str]] = Field(
        default_factory=list, description="Current medications"
    )
    hospital: Optional[str] = Field(None, description="Registered hospital")
    registeredBy: Optional[str] = Field(
        None,
        description="UID of the Health Worker who registered this patient"
    )
    registrationSource: str = Field(
        "manual",
        description="How the patient was registered: 'manual' or 'esignet'"
    )
    identityStatus: str = Field(
        IdentityStatus.PENDING,
        description="Identity verification status"
    )
    kycStatus: str = Field(
        PatientKYCStatus.PENDING,
        description="KYC verification status"
    )
    createdAt: Optional[str] = Field(None, description="ISO creation timestamp")
    updatedAt: Optional[str] = Field(None, description="ISO last update timestamp")
    isActive: bool = Field(True, description="Whether the patient record is active")


# ── Request Models ──────────────────────────────────────────────

class PatientRegisterRequest(BaseModel):
    """Request body for POST /patients/register.

    Sent by the Health Worker when registering a new patient.
    """

    fullName: str = Field(..., description="Patient full name")
    dateOfBirth: Optional[str] = Field(None, description="Date of birth (ISO)")
    gender: Optional[str] = Field(None, description="Gender")
    phoneNumber: Optional[str] = Field(None, description="Phone number")
    nationalId: Optional[str] = Field(None, description="National ID")
    emergencyContact: Optional[str] = Field(None, description="Emergency contact")
    bloodType: Optional[str] = Field(None, description="Blood type")
    allergies: Optional[List[str]] = Field(default_factory=list)
    chronicConditions: Optional[List[str]] = Field(default_factory=list)
    medications: Optional[List[str]] = Field(default_factory=list)
    hospital: Optional[str] = Field(None, description="Hospital")
    # Optional: if patient identity was pre-verified via eSignet
    esignetSubjectId: Optional[str] = Field(
        None,
        description="eSignet sub if identity already verified"
    )
    identityVerified: bool = Field(
        False,
        description="True if identity was verified through eSignet workflow"
    )


class PatientUpdateRequest(BaseModel):
    """Request body for PATCH /patients/{patient_id}.

    All fields optional — only provided fields are updated.
    """

    fullName: Optional[str] = None
    dateOfBirth: Optional[str] = None
    gender: Optional[str] = None
    phoneNumber: Optional[str] = None
    nationalId: Optional[str] = None
    emergencyContact: Optional[str] = None
    bloodType: Optional[str] = None
    allergies: Optional[List[str]] = None
    chronicConditions: Optional[List[str]] = None
    medications: Optional[List[str]] = None
    hospital: Optional[str] = None
    esignetSubjectId: Optional[str] = None
    identityStatus: Optional[str] = None
    kycStatus: Optional[str] = None
    isActive: Optional[bool] = None


# ── Response Models ─────────────────────────────────────────────

class PatientResponse(BaseModel):
    """Full patient response (for Health Worker / Admin / Doctor)."""
    patient: PatientModel
    message: str = "Patient retrieved successfully."


class PatientSummaryResponse(BaseModel):
    """Medical summary for Doctors — includes medical details for care."""

    patientId: str
    fullName: str
    dateOfBirth: Optional[str] = None
    gender: Optional[str] = None
    bloodType: Optional[str] = None
    allergies: List[str] = Field(default_factory=list)
    chronicConditions: List[str] = Field(default_factory=list)
    medications: List[str] = Field(default_factory=list)
    emergencyContact: Optional[str] = None
    hospital: Optional[str] = None
    identityStatus: str = "PENDING"
    isActive: bool = True


class PatientEmergencyResponse(BaseModel):
    """Minimal emergency data for First Responders.

    Contains ONLY what is needed in an emergency situation:
    name, blood type, allergies, chronic conditions, emergency contact.
    """

    patientId: str
    fullName: str
    bloodType: Optional[str] = None
    allergies: List[str] = Field(default_factory=list)
    chronicConditions: List[str] = Field(default_factory=list)
    emergencyContact: Optional[str] = None
