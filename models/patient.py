"""
Pydantic models for the Patient collection and related API contracts.

Aligned with Flutter team's PatientsModel structure for perfect coordination.

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


class UrgencyLevel(str, Enum):
    """Appointment urgency level."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AppointmentStatus(str, Enum):
    """Appointment status."""
    SCHEDULED = "Scheduled"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    NO_SHOW = "No-show"


# ── Vital Signs Model ──────────────────────────────────────────

class VitalSignsModel(BaseModel):
    """Latest vital signs for a patient."""
    
    heartRate: int = Field(..., description="Heart rate in BPM")
    oxygenSaturation: int = Field(..., description="Oxygen saturation in %")
    bloodPressure: str = Field(..., description="Blood pressure (e.g. 120/80)")
    timestamp: str = Field(..., description="ISO timestamp of reading")


# ── Emergency Contact Model ────────────────────────────────────

class EmergencyContact(BaseModel):
    """Emergency contact for a patient."""
    
    id: str = Field(..., description="Unique emergency contact ID")
    name: str = Field(..., description="Contact name")
    number: str = Field(..., description="Phone number")
    address: str = Field(..., description="Contact address")
    tag: str = Field(..., description="Relationship tag (Sister, Brother, etc)")
    patientId: str = Field(..., description="Patient ID")


# ── Medical Note Model ─────────────────────────────────────────

class MedicalNote(BaseModel):
    """Medical note from a doctor."""
    
    id: str = Field(..., description="Unique note ID")
    title: str = Field(..., description="Note title")
    description: str = Field(..., description="Note content")
    date: str = Field(..., description="ISO creation date")


# ── Active Medicine Model ──────────────────────────────────────

class ActiveMedecine(BaseModel):
    """Active medication for a patient."""
    
    id: str = Field(..., description="Unique medication ID")
    name: str = Field(..., description="Medication name")
    description: str = Field(..., description="Medication description")
    type: str = Field(..., description="Type (Tablet, Capsule, Injection, etc)")
    frequency: int = Field(..., description="Frequency per day")
    prescriptionDate: str = Field(..., description="ISO prescription date")
    prescriberId: str = Field(..., description="Doctor UID who prescribed")


# ── Appointment Model ──────────────────────────────────────────

class Appointment(BaseModel):
    """Doctor appointment for a patient."""
    
    id: str = Field(..., description="Unique appointment ID")
    doctorId: str = Field(..., description="Doctor UID")
    patientId: str = Field(..., description="Patient ID")
    patientName: str = Field(..., description="Patient full name")
    reason: str = Field(..., description="Appointment reason")
    date: str = Field(..., description="ISO appointment date/time")
    urgencyLevel: str = Field(..., description="Urgency (Low, Medium, High, Critical)")
    status: str = Field(..., description="Status (Scheduled, Completed, etc)")


# ── Vaccine Dose Model ─────────────────────────────────────────

class VaccineDose(BaseModel):
    """Single vaccine dose."""
    
    doseNumber: int = Field(..., description="Dose number")
    date: str = Field(..., description="ISO date of dose")


# ── Vaccination Model ─────────────────────────────────────────

class Vaccination(BaseModel):
    """Vaccination record for a patient."""
    
    id: str = Field(..., description="Unique vaccination ID")
    vaccineName: str = Field(..., description="Vaccine name")
    targetDisease: str = Field(..., description="Disease targeted")
    totalDoses: int = Field(..., description="Total planned doses")
    dosesReceived: List[VaccineDose] = Field(default_factory=list, description="Doses received")


# ── Organ Donation Model ───────────────────────────────────────

class OrganDonation(BaseModel):
    """Organ/blood donation information."""
    
    isOrganDonor: bool = Field(False, description="Is organ donor")
    isBloodDonor: bool = Field(False, description="Is blood donor")
    donatableOrgans: List[str] = Field(default_factory=list, description="Organs willing to donate")
    lastDonationDate: Optional[str] = Field(None, description="ISO date of last donation")


# ── Patient Firestore Model ──────────────────────────────────────

class PatientsModel(BaseModel):
    """Full patient model matching the Firestore 'patients' collection.

    Document ID = id (auto-generated or derived from esignetSubjectId).
    Aligned with Flutter team's PatientsModel structure.
    """

    id: str = Field(..., description="Unique patient document ID")
    firstName: str = Field(..., description="Patient first name")
    lastName: str = Field(..., description="Patient last name")
    email: Optional[str] = Field(None, description="Patient email")
    phone: Optional[str] = Field(None, description="Phone number")
    gender: Optional[str] = Field(None, description="Gender (Masculin, Féminin, Autre)")
    adress: Optional[str] = Field(None, description="Patient address")
    imageUrl: Optional[str] = Field(None, description="Patient photo URL")
    bloodGroup: Optional[str] = Field(None, description="Blood group (A+, O-, etc)")
    medAllergies: Optional[str] = Field(None, description="Medical allergies (comma-separated or structured)")
    foodAllergies: Optional[str] = Field(None, description="Food allergies (comma-separated or structured)")
    dateOfBirth: Optional[str] = Field(None, description="ISO date of birth")
    nationalId: Optional[str] = Field(None, description="National ID (unique)")
    chronicConditions: List[str] = Field(default_factory=list, description="List of chronic conditions")
    weightKg: Optional[float] = Field(None, description="Weight in kg")
    heightCm: Optional[float] = Field(None, description="Height in cm")
    latestVitalSigns: Optional[VitalSignsModel] = Field(None, description="Latest vital signs")
    emergencyContacts: List[EmergencyContact] = Field(default_factory=list, description="Emergency contacts")
    medicalNotes: List[MedicalNote] = Field(default_factory=list, description="Medical notes")
    activeMedecines: List[ActiveMedecine] = Field(default_factory=list, description="Active medications")
    appointments: List[Appointment] = Field(default_factory=list, description="Appointments")
    vaccinations: List[Vaccination] = Field(default_factory=list, description="Vaccination records")
    organDonation: Optional[OrganDonation] = Field(None, description="Organ/blood donation info")
    
    # Meta fields
    esignetSubjectId: Optional[str] = Field(None, description="eSignet 'sub' claim if identity verified")
    identityStatus: str = Field(IdentityStatus.PENDING, description="Identity verification status")
    kycStatus: str = Field(PatientKYCStatus.PENDING, description="KYC verification status")
    registrationSource: str = Field("manual", description="Registration source: 'manual' or 'esignet'")
    isActive: bool = Field(True, description="Active patient record")
    createdByID: str = Field(..., description="UID of staff who created record")
    createdAt: str = Field(..., description="ISO creation timestamp")
    updatedAt: str = Field(..., description="ISO update timestamp")


# ── Request Models ────────────────────────────────────────────

class PatientRegisterRequest(BaseModel):
    """Request body for POST /patients/register.

    Minimal required data at registration; Flutter can update later.
    """

    firstName: str = Field(..., description="Patient first name")
    lastName: str = Field(..., description="Patient last name")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Phone number")
    gender: Optional[str] = Field(None, description="Gender")
    adress: Optional[str] = Field(None, description="Address")
    dateOfBirth: Optional[str] = Field(None, description="ISO date of birth")
    nationalId: Optional[str] = Field(None, description="National ID")
    bloodGroup: Optional[str] = Field(None, description="Blood group")
    medAllergies: Optional[str] = Field(None, description="Medical allergies")
    foodAllergies: Optional[str] = Field(None, description="Food allergies")
    chronicConditions: Optional[List[str]] = Field(default_factory=list, description="Chronic conditions")
    weightKg: Optional[float] = Field(None, description="Weight in kg")
    heightCm: Optional[float] = Field(None, description="Height in cm")
    
    # Optional: if identity verified via eSignet
    esignetSubjectId: Optional[str] = Field(None, description="eSignet sub if pre-verified")
    identityVerified: bool = Field(False, description="True if identity verified via eSignet")


class PatientUpdateRequest(BaseModel):
    """Request body for PATCH /patients/{patient_id}.

    All fields optional — only provided fields are updated.
    """

    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    adress: Optional[str] = None
    imageUrl: Optional[str] = None
    dateOfBirth: Optional[str] = None
    nationalId: Optional[str] = None
    bloodGroup: Optional[str] = None
    medAllergies: Optional[str] = None
    foodAllergies: Optional[str] = None
    chronicConditions: Optional[List[str]] = None
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    emergencyContacts: Optional[List[EmergencyContact]] = None
    esignetSubjectId: Optional[str] = None
    identityStatus: Optional[str] = None
    kycStatus: Optional[str] = None
    isActive: Optional[bool] = None


# ── Response Models ──────────────────────────────────────────

class PatientResponse(BaseModel):
    """Full patient response for Flutter."""
    patient: PatientsModel
    message: str = "Patient retrieved successfully."


class PatientSummaryResponse(BaseModel):
    """Medical summary for Doctors — aligned with Flutter team expectations."""

    id: str
    firstName: str
    lastName: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    adress: Optional[str] = None
    bloodGroup: Optional[str] = None
    dateOfBirth: Optional[str] = None
    medAllergies: Optional[str] = None
    foodAllergies: Optional[str] = None
    chronicConditions: List[str] = Field(default_factory=list)
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    latestVitalSigns: Optional[VitalSignsModel] = None
    activeMedecines: List[ActiveMedecine] = Field(default_factory=list)
    medicalNotes: List[MedicalNote] = Field(default_factory=list)
    appointments: List[Appointment] = Field(default_factory=list)
    vaccinations: List[Vaccination] = Field(default_factory=list)
    identityStatus: str = "PENDING"
    kycStatus: str = "PENDING"
    isActive: bool = True


class PatientEmergencyResponse(BaseModel):
    """Minimal emergency data for First Responders.

    Contains ONLY what is needed in an emergency situation.
    """

    id: str
    firstName: str
    lastName: str
    phone: Optional[str] = None
    gender: Optional[str] = None
    bloodGroup: Optional[str] = None
    medAllergies: Optional[str] = None
    foodAllergies: Optional[str] = None
    chronicConditions: List[str] = Field(default_factory=list)
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    latestVitalSigns: Optional[VitalSignsModel] = None
    emergencyContacts: List[EmergencyContact] = Field(default_factory=list)
    isActive: bool = True


# ── Request Models ────────────────────────────────────────────

class PatientRegisterRequest(BaseModel):
    """Request body for POST /patients/register.

    Minimal required data at registration; Flutter can update later.
    """

    firstName: str = Field(..., description="Patient first name")
    lastName: str = Field(..., description="Patient last name")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Phone number")
    gender: Optional[str] = Field(None, description="Gender")
    adress: Optional[str] = Field(None, description="Address")
    dateOfBirth: Optional[str] = Field(None, description="ISO date of birth")
    nationalId: Optional[str] = Field(None, description="National ID")
    bloodGroup: Optional[str] = Field(None, description="Blood group")
    medAllergies: Optional[str] = Field(None, description="Medical allergies")
    foodAllergies: Optional[str] = Field(None, description="Food allergies")
    chronicConditions: Optional[List[str]] = Field(default_factory=list, description="Chronic conditions")
    weightKg: Optional[float] = Field(None, description="Weight in kg")
    heightCm: Optional[float] = Field(None, description="Height in cm")
    
    # Optional: if identity verified via eSignet
    esignetSubjectId: Optional[str] = Field(None, description="eSignet sub if pre-verified")
    identityVerified: bool = Field(False, description="True if identity verified via eSignet")


class PatientUpdateRequest(BaseModel):
    """Request body for PATCH /patients/{patient_id}.

    All fields optional — only provided fields are updated.
    """

    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    adress: Optional[str] = None
    imageUrl: Optional[str] = None
    dateOfBirth: Optional[str] = None
    nationalId: Optional[str] = None
    bloodGroup: Optional[str] = None
    medAllergies: Optional[str] = None
    foodAllergies: Optional[str] = None
    chronicConditions: Optional[List[str]] = None
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    emergencyContacts: Optional[List[EmergencyContact]] = None
    esignetSubjectId: Optional[str] = None
    identityStatus: Optional[str] = None
    kycStatus: Optional[str] = None
    isActive: Optional[bool] = None


# ── Response Models ──────────────────────────────────────────

class PatientResponse(BaseModel):
    """Full patient response for Flutter."""
    patient: PatientsModel
    message: str = "Patient retrieved successfully."


class PatientSummaryResponse(BaseModel):
    """Medical summary for Doctors — aligned with Flutter team expectations."""

    id: str
    firstName: str
    lastName: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    adress: Optional[str] = None
    bloodGroup: Optional[str] = None
    dateOfBirth: Optional[str] = None
    medAllergies: Optional[str] = None
    foodAllergies: Optional[str] = None
    chronicConditions: List[str] = Field(default_factory=list)
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    latestVitalSigns: Optional[VitalSignsModel] = None
    activeMedecines: List[ActiveMedecine] = Field(default_factory=list)
    medicalNotes: List[MedicalNote] = Field(default_factory=list)
    appointments: List[Appointment] = Field(default_factory=list)
    vaccinations: List[Vaccination] = Field(default_factory=list)
    identityStatus: str = "PENDING"
    kycStatus: str = "PENDING"
    isActive: bool = True


class PatientEmergencyResponse(BaseModel):
    """Minimal emergency data for First Responders.

    Contains ONLY what is needed in an emergency situation.
    """

    id: str
    firstName: str
    lastName: str
    phone: Optional[str] = None
    gender: Optional[str] = None
    bloodGroup: Optional[str] = None
    medAllergies: Optional[str] = None
    foodAllergies: Optional[str] = None
    chronicConditions: List[str] = Field(default_factory=list)
    weightKg: Optional[float] = None
    heightCm: Optional[float] = None
    latestVitalSigns: Optional[VitalSignsModel] = None
    emergencyContacts: List[EmergencyContact] = Field(default_factory=list)
    isActive: bool = True
