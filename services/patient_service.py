"""
Patient Firestore service layer.

Handles all CRUD operations for the 'patients' collection.
Patients are separate from staff users and are registered by Health Workers.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from services.firebase_service import get_db, _should_use_local_fallback, _activate_local_fallback

logger = logging.getLogger(__name__)


# _____________________ Patient CRUD Operations _____________________

async def create_patient(patient_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new patient document in the 'patients' collection.

    If no id is provided, one is auto-generated.
    If esignetSubjectId is provided, it is used as the document ID
    to guarantee 1:1 mapping between verified identity and patient record.

    Args:
        patient_data: Dict containing patient fields aligned with PatientsModel.

    Returns:
        The created patient data dict with id and timestamps.
    """
    try:
        db = get_db()

        # Determine document ID
        # If patient was verified via eSignet, use esignetSubjectId as ID
        # Otherwise generate a unique ID
        doc_id = patient_data.get("id")
        if not doc_id:
            esignet_sub = patient_data.get("esignetSubjectId")
            doc_id = esignet_sub if esignet_sub else f"PAT-{uuid.uuid4().hex[:12]}"
            patient_data["id"] = doc_id

        # Set timestamps
        now = datetime.utcnow().isoformat()
        patient_data["createdAt"] = now
        patient_data["updatedAt"] = now

        # Set defaults for list fields
        patient_data.setdefault("isActive", True)
        patient_data.setdefault("identityStatus", "PENDING")
        patient_data.setdefault("kycStatus", "PENDING")
        patient_data.setdefault("registrationSource", "manual")
        patient_data.setdefault("chronicConditions", [])
        patient_data.setdefault("emergencyContacts", [])
        patient_data.setdefault("medicalNotes", [])
        patient_data.setdefault("activeMedecines", [])
        patient_data.setdefault("appointments", [])
        patient_data.setdefault("vaccinations", [])

        db.collection("patients").document(doc_id).set(patient_data)
        logger.info(f"Patient created in Firestore: {doc_id}")
        return patient_data

    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            doc_id = patient_data.get("id")
            if not doc_id:
                esignet_sub = patient_data.get("esignetSubjectId")
                doc_id = esignet_sub if esignet_sub else f"PAT-{uuid.uuid4().hex[:12]}"
                patient_data["id"] = doc_id

            now = datetime.utcnow().isoformat()
            patient_data["createdAt"] = now
            patient_data["updatedAt"] = now
            patient_data.setdefault("isActive", True)
            patient_data.setdefault("identityStatus", "PENDING")
            patient_data.setdefault("kycStatus", "PENDING")
            patient_data.setdefault("registrationSource", "manual")
            patient_data.setdefault("chronicConditions", [])
            patient_data.setdefault("emergencyContacts", [])
            patient_data.setdefault("medicalNotes", [])
            patient_data.setdefault("activeMedecines", [])
            patient_data.setdefault("appointments", [])
            patient_data.setdefault("vaccinations", [])
            db.collection("patients").document(doc_id).set(patient_data)
            logger.info(f"Patient created in local fallback store: {doc_id}")
            return patient_data
        logger.error(f"Error creating patient: {e}")
        raise


async def get_patient(patient_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a patient document by its document ID.

    Args:
        patient_id: The patient's unique document ID.

    Returns:
        Patient data dict if found, None otherwise.
    """
    try:
        db = get_db()
        doc = db.collection("patients").document(patient_id).get()
        if doc.exists:
            logger.info(f"Patient found: {patient_id}")
            return doc.to_dict()
        logger.info(f"Patient not found: {patient_id}")
        return None
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            doc = db.collection("patients").document(patient_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        logger.error(f"Error fetching patient {patient_id}: {e}")
        raise


async def get_patient_by_esignet_sub(esignet_sub: str) -> Optional[Dict[str, Any]]:
    """Find a patient by their eSignet subject ID.

    Used to check if a patient with this verified identity already exists,
    preventing duplicate registrations.

    Args:
        esignet_sub: The eSignet 'sub' claim value.

    Returns:
        Patient data dict if found, None otherwise.
    """
    try:
        db = get_db()
        query = (
            db.collection("patients")
            .where("esignetSubjectId", "==", esignet_sub)
            .limit(1)
        )
        results = query.get()
        for doc in results:
            logger.info(f"Patient found by esignetSubjectId: {esignet_sub}")
            return doc.to_dict()
        return None
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            query = (
                db.collection("patients")
                .where("esignetSubjectId", "==", esignet_sub)
                .limit(1)
            )
            results = query.get()
            for doc in results:
                return doc.to_dict()
            return None
        logger.error(f"Error querying patient by esignetSubjectId: {e}")
        raise


async def update_patient(patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update specific fields of a patient document.

    Automatically sets the 'updatedAt' timestamp.

    Args:
        patient_id: The patient's unique document ID.
        data: Dict of fields to update.

    Returns:
        The full updated patient data dict.

    Raises:
        ValueError: If patient does not exist.
    """
    try:
        db = get_db()

        # Verify patient exists
        doc_ref = db.collection("patients").document(patient_id)
        if not doc_ref.get().exists:
            raise ValueError(f"Patient not found: {patient_id}")

        # Always update the timestamp
        data["updatedAt"] = datetime.utcnow().isoformat()

        doc_ref.update(data)
        logger.info(f"Patient updated: {patient_id}")

        # Return the full updated document
        updated_doc = doc_ref.get()
        return updated_doc.to_dict()

    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            doc_ref = db.collection("patients").document(patient_id)
            if not doc_ref.get().exists:
                raise ValueError(f"Patient not found: {patient_id}")
            data["updatedAt"] = datetime.utcnow().isoformat()
            doc_ref.update(data)
            updated_doc = doc_ref.get()
            return updated_doc.to_dict()
        logger.error(f"Error updating patient {patient_id}: {e}")
        raise


async def check_patient_national_id_unique(
    national_id: str, exclude_patient_id: Optional[str] = None
) -> bool:
    """Check if a nationalId is unique across all patients.

    Args:
        national_id: The national ID to check.
        exclude_patient_id: Optional patient ID to exclude (for updates).

    Returns:
        True if the nationalId is unique (not found), False if duplicate.
    """
    try:
        db = get_db()
        query = (
            db.collection("patients")
            .where("nationalId", "==", national_id)
            .limit(2)
        )
        results = query.get()

        for doc in results:
            if exclude_patient_id and doc.id == exclude_patient_id:
                continue
            logger.warning(
                f"Patient nationalId {national_id} already exists: {doc.id}"
            )
            return False

        return True
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            query = (
                db.collection("patients")
                .where("nationalId", "==", national_id)
                .limit(2)
            )
            results = query.get()
            for doc in results:
                if exclude_patient_id and doc.id == exclude_patient_id:
                    continue
                return False
            return True
        logger.error(f"Error checking patient nationalId uniqueness: {e}")
        raise


async def check_esignet_sub_unique(
    esignet_sub: str, exclude_patient_id: Optional[str] = None
) -> bool:
    """Check if an esignetSubjectId is unique across all patients.

    Args:
        esignet_sub: The eSignet subject ID to check.
        exclude_patient_id: Optional patient ID to exclude.

    Returns:
        True if unique, False if duplicate.
    """
    try:
        db = get_db()
        query = (
            db.collection("patients")
            .where("esignetSubjectId", "==", esignet_sub)
            .limit(2)
        )
        results = query.get()

        for doc in results:
            if exclude_patient_id and doc.id == exclude_patient_id:
                continue
            return False

        return True
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            query = (
                db.collection("patients")
                .where("esignetSubjectId", "==", esignet_sub)
                .limit(2)
            )
            results = query.get()
            for doc in results:
                if exclude_patient_id and doc.id == exclude_patient_id:
                    continue
                return False
            return True
        logger.error(f"Error checking esignetSubjectId uniqueness: {e}")
        raise


def build_patient_summary(patient_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a medical summary view for Doctors.

    Includes all medically relevant fields needed for patient care.

    Args:
        patient_data: Full patient document from Firestore.

    Returns:
        Filtered dict with medical summary fields aligned with PatientSummaryResponse.
    """
    return {
        "id": patient_data.get("id"),
        "firstName": patient_data.get("firstName"),
        "lastName": patient_data.get("lastName"),
        "email": patient_data.get("email"),
        "phone": patient_data.get("phone"),
        "gender": patient_data.get("gender"),
        "adress": patient_data.get("adress"),
        "bloodGroup": patient_data.get("bloodGroup"),
        "dateOfBirth": patient_data.get("dateOfBirth"),
        "medAllergies": patient_data.get("medAllergies"),
        "foodAllergies": patient_data.get("foodAllergies"),
        "chronicConditions": patient_data.get("chronicConditions", []),
        "weightKg": patient_data.get("weightKg"),
        "heightCm": patient_data.get("heightCm"),
        "latestVitalSigns": patient_data.get("latestVitalSigns"),
        "activeMedecines": patient_data.get("activeMedecines", []),
        "medicalNotes": patient_data.get("medicalNotes", []),
        "appointments": patient_data.get("appointments", []),
        "vaccinations": patient_data.get("vaccinations", []),
        "identityStatus": patient_data.get("identityStatus", "PENDING"),
        "kycStatus": patient_data.get("kycStatus", "PENDING"),
        "isActive": patient_data.get("isActive", True),
    }


def build_patient_emergency(patient_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build minimal emergency view for First Responders.

    Contains ONLY what is needed in an emergency:
    name, blood type, allergies, chronic conditions, emergency contact.

    Args:
        patient_data: Full patient document from Firestore.

    Returns:
        Filtered dict with emergency-only fields aligned with PatientEmergencyResponse.
    """
    return {
        "id": patient_data.get("id"),
        "firstName": patient_data.get("firstName"),
        "lastName": patient_data.get("lastName"),
        "phone": patient_data.get("phone"),
        "gender": patient_data.get("gender"),
        "bloodGroup": patient_data.get("bloodGroup"),
        "medAllergies": patient_data.get("medAllergies"),
        "foodAllergies": patient_data.get("foodAllergies"),
        "chronicConditions": patient_data.get("chronicConditions", []),
        "weightKg": patient_data.get("weightKg"),
        "heightCm": patient_data.get("heightCm"),
        "latestVitalSigns": patient_data.get("latestVitalSigns"),
        "emergencyContacts": patient_data.get("emergencyContacts", []),
        "isActive": patient_data.get("isActive", True),
    }


async def delete_patient(patient_id: str) -> None:
    """Delete a patient document (used for testing cleanup).

    Args:
        patient_id: The patient's document ID.
    """
    try:
        db = get_db()
        db.collection("patients").document(patient_id).delete()
        logger.info(f"Patient deleted: {patient_id}")
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            db.collection("patients").document(patient_id).delete()
            return
        logger.error(f"Error deleting patient {patient_id}: {e}")
        raise
