"""
Firebase / Firestore service layer.
Handles all Firestore CRUD operations for the 'users' collection.
"""

import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from typing import Optional, Dict, Any, List

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Module-level Firestore client ────────────────────────────────
_db = None
_local_store: Dict[str, Dict[str, Dict[str, Any]]] = {}
_force_local_fallback = False


class _LocalDocumentSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data or {})


class _LocalDocumentRef:
    def __init__(self, collection_name: str, doc_id: str):
        self._collection_name = collection_name
        self.id = doc_id

    def get(self) -> _LocalDocumentSnapshot:
        collection = _local_store.get(self._collection_name, {})
        return _LocalDocumentSnapshot(self.id, collection.get(self.id))

    def set(self, data: Dict[str, Any]) -> None:
        collection = _local_store.setdefault(self._collection_name, {})
        collection[self.id] = dict(data)

    def update(self, data: Dict[str, Any]) -> None:
        collection = _local_store.setdefault(self._collection_name, {})
        if self.id not in collection:
            raise KeyError(f"Document not found: {self._collection_name}/{self.id}")
        collection[self.id].update(dict(data))

    def delete(self) -> None:
        collection = _local_store.setdefault(self._collection_name, {})
        collection.pop(self.id, None)


class _LocalQuery:
    def __init__(self, collection_name: str, conditions=None, limit_value: Optional[int] = None):
        self._collection_name = collection_name
        self._conditions = list(conditions or [])
        self._limit_value = limit_value

    def where(self, field: str, op: str, value: Any):
        return _LocalQuery(self._collection_name, self._conditions + [(field, op, value)], self._limit_value)

    def limit(self, value: int):
        return _LocalQuery(self._collection_name, self._conditions, value)

    def get(self):
        collection = _local_store.get(self._collection_name, {})
        results = []
        for doc_id, payload in collection.items():
            matched = True
            for field, op, expected in self._conditions:
                if op != "==":
                    raise NotImplementedError("Only equality queries are supported by the local fallback")
                if payload.get(field) != expected:
                    matched = False
                    break
            if matched:
                results.append(_LocalDocumentSnapshot(doc_id, payload))
            if self._limit_value is not None and len(results) >= self._limit_value:
                break
        return results


class _LocalCollection:
    def __init__(self, collection_name: str):
        self._collection_name = collection_name

    def document(self, doc_id: str) -> _LocalDocumentRef:
        return _LocalDocumentRef(self._collection_name, doc_id)

    def where(self, field: str, op: str, value: Any):
        return _LocalQuery(self._collection_name, [(field, op, value)])

    def limit(self, value: int):
        return _LocalQuery(self._collection_name, [], value)


class _LocalFirestoreClient:
    def collection(self, collection_name: str) -> _LocalCollection:
        return _LocalCollection(collection_name)


def utc_now_iso() -> str:
    """UTC timestamp helper in ISO format."""
    return datetime.utcnow().isoformat()


def _is_kyc_transition_allowed(current_status: str, next_status: str) -> bool:
    """Validate allowed KYC status transitions."""
    allowed = {
        "PENDING": {"SUBMITTED"},
        "SUBMITTED": {"VERIFIED", "REJECTED"},
        "REJECTED": {"SUBMITTED"},
        "VERIFIED": set(),
        "VERIFIED_BY_PROVIDER": set(),
    }
    return next_status in allowed.get(current_status, set())


def init_firebase() -> None:
    """Initialize Firebase Admin SDK using service account credentials.
    
    Reads credentials from the path specified in FIREBASE_CREDENTIALS_JSON
    environment variable. Must be called once at app startup.
    """
    global _db

    if firebase_admin._apps and _db is not None:
        if isinstance(_db, _LocalFirestoreClient):
            logger.info("Using local Firestore-compatible fallback store.")
            return
        logger.info("Firebase already initialized, reusing existing app.")
        _db = firestore.client()
        return

    try:
        cred_path = settings.firebase_credentials_json.strip()
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("Initializing Firebase with service account file: %s", cred_path)
        else:
            options = {}
            if settings.firebase_project_id:
                options["projectId"] = settings.firebase_project_id
            firebase_admin.initialize_app(options=options or None)
            logger.info("Initializing Firebase with application default credentials.")
        _db = firestore.client()
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        if settings.firebase_local_fallback_enabled:
            logger.warning(
                "Falling back to local Firestore-compatible store because the remote database is unavailable: %s",
                e,
            )
            _db = _LocalFirestoreClient()
            return
        logger.error("Firebase initialization failed and local fallback is disabled: %s", e)
        raise


def get_db():
    """Get the Firestore client instance."""
    global _db
    if _force_local_fallback:
        if _db is None or not isinstance(_db, _LocalFirestoreClient):
            _db = _LocalFirestoreClient()
        return _db
    if _db is None:
        init_firebase()
    return _db


def _should_use_local_fallback(error: Exception) -> bool:
    if not settings.firebase_local_fallback_enabled:
        return False
    message = str(error).lower()
    return (
        "database (default) does not exist" in message
        or "service_disabled" in message
        or "cloud firestore api" in message
    )


def _activate_local_fallback(reason: Exception) -> None:
    global _db, _force_local_fallback
    if not settings.firebase_local_fallback_enabled:
        raise reason
    _force_local_fallback = True
    _db = _LocalFirestoreClient()
    logger.warning("Using local Firestore-compatible fallback store: %s", reason)


# ── User CRUD Operations ────────────────────────────────────────

async def get_user(uid: str) -> Optional[Dict[str, Any]]:
    """Retrieve a user document from Firestore by uid (= sub).
    
    Args:
        uid: The user's unique ID (sub claim from eSignet).
    
    Returns:
        User data dict if found, None otherwise.
    """
    try:
        db = get_db()
        doc = db.collection("users").document(uid).get()
        if doc.exists:
            logger.info(f"User found in Firestore: {uid}")
            return doc.to_dict()
        logger.info(f"User not found in Firestore: {uid}")
        return None
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            doc = db.collection("users").document(uid).get()
            if doc.exists:
                return doc.to_dict()
            return None
        logger.error(f"Error fetching user {uid}: {e}")
        raise


async def create_user(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new user document in Firestore.
    
    Document ID is set to uid (= sub from eSignet) to guarantee
    1:1 mapping between eSignet identity and Firestore document.
    
    Args:
        user_data: Dict containing all user fields.
    
    Returns:
        The created user data dict.
    """
    try:
        db = get_db()
        uid = user_data["uid"]

        # Set timestamps
        now = utc_now_iso()
        user_data["createdAt"] = now
        user_data["lastLogin"] = now

        db.collection("users").document(uid).set(user_data)
        logger.info(f"User created in Firestore: {uid}")
        return user_data
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            uid = user_data["uid"]
            now = utc_now_iso()
            user_data["createdAt"] = now
            user_data["lastLogin"] = now
            db.collection("users").document(uid).set(user_data)
            logger.info(f"User created in local fallback store: {uid}")
            return user_data
        logger.error(f"Error creating user: {e}")
        raise


async def update_user(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update specific fields of a user document.
    
    Args:
        uid: The user's unique ID.
        data: Dict of fields to update.
    
    Returns:
        The updated user data dict.
    """
    try:
        db = get_db()
        db.collection("users").document(uid).update(data)
        logger.info(f"User updated in Firestore: {uid}")

        # Return the updated document
        updated_doc = db.collection("users").document(uid).get()
        return updated_doc.to_dict()
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            db.collection("users").document(uid).update(data)
            updated_doc = db.collection("users").document(uid).get()
            return updated_doc.to_dict()
        logger.error(f"Error updating user {uid}: {e}")
        raise


async def update_last_login(uid: str) -> None:
    """Update only the lastLogin timestamp for an existing user.
    
    Args:
        uid: The user's unique ID.
    """
    try:
        db = get_db()
        db.collection("users").document(uid).update({
            "lastLogin": utc_now_iso()
        })
        logger.info(f"Updated lastLogin for user: {uid}")
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            db.collection("users").document(uid).update({"lastLogin": utc_now_iso()})
            return
        logger.error(f"Error updating lastLogin for {uid}: {e}")
        raise


async def check_national_id_unique(national_id: str, exclude_uid: Optional[str] = None) -> bool:
    """Check if a nationalId is unique across all users.
    
    Args:
        national_id: The national ID to check.
        exclude_uid: Optional uid to exclude from the check (for updates).
    
    Returns:
        True if the nationalId is unique (not found), False if it already exists.
    """
    try:
        db = get_db()
        query = db.collection("users").where("nationalId", "==", national_id).limit(1)
        results = query.get()

        for doc in results:
            if exclude_uid and doc.id == exclude_uid:
                continue
            logger.warning(f"National ID {national_id} already exists for user: {doc.id}")
            return False

        return True
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            db = get_db()
            query = db.collection("users").where("nationalId", "==", national_id).limit(1)
            results = query.get()
            for doc in results:
                if exclude_uid and doc.id == exclude_uid:
                    continue
                return False
            return True
        logger.error(f"Error checking nationalId uniqueness: {e}")
        raise


async def update_kyc_status(uid: str, status: str, additional_data: Optional[Dict] = None) -> Dict[str, Any]:
    """Update the KYC status and optionally additional KYC-related fields.
    
    Args:
        uid: The user's unique ID.
        status: New KYC status value.
        additional_data: Optional dict of additional fields to update.
    
    Returns:
        The updated user data dict.
    """
    try:
        current = await get_user(uid)
        if not current:
            raise ValueError(f"User not found: {uid}")

        current_status = current.get("kycStatus", "PENDING")
        if not _is_kyc_transition_allowed(current_status, status):
            raise ValueError(
                f"Invalid KYC transition: {current_status} -> {status}"
            )

        update_data = {
            "kycStatus": status,
            "kycUpdatedAt": utc_now_iso(),
        }
        if additional_data:
            update_data.update(additional_data)

        return await update_user(uid, update_data)
    except Exception as e:
        if _should_use_local_fallback(e):
            _activate_local_fallback(e)
            return await update_user(uid, update_data)
        logger.error(f"Error updating KYC status for {uid}: {e}")
        raise


async def assign_user_role(uid: str, role: str, assigned_by: str) -> Dict[str, Any]:
    """Assign or update a user's staff role (admin-only operation)."""
    return await update_user(
        uid,
        {
            "role": role,
            "roleAssignedBy": assigned_by,
            "roleAssignedAt": utc_now_iso(),
        },
    )


async def list_users_by_kyc_status(kyc_status: str, limit: int = 100) -> List[Dict[str, Any]]:
    """List users filtered by KYC status."""
    db = get_db()
    query = db.collection("users").where("kycStatus", "==", kyc_status).limit(limit)
    docs = query.get()
    return [doc.to_dict() for doc in docs]


async def save_auth_state(state: str, nonce: str, flow: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Persist OAuth state with nonce and flow to prevent replay/CSRF."""
    db = get_db()
    now = datetime.utcnow()
    payload = {
        "state": state,
        "nonce": nonce,
        "flow": flow,
        "metadata": metadata or {},
        "createdAt": now.isoformat(),
        "expiresAt": (now.timestamp() + 300),
        "used": False,
    }
    db.collection("auth_states").document(state).set(payload)


async def consume_auth_state(state: str) -> Optional[Dict[str, Any]]:
    """Consume state once. Returns None if missing, expired, or already used."""
    db = get_db()
    doc_ref = db.collection("auth_states").document(state)
    doc = doc_ref.get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    if data.get("used"):
        return None

    expires_at = float(data.get("expiresAt", 0))
    if expires_at < datetime.utcnow().timestamp():
        return None

    doc_ref.update({"used": True, "usedAt": utc_now_iso()})
    return data
