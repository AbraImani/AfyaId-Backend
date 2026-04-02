"""
API-level logic tests for AfyaID backend.

This test suite validates endpoint behavior and RBAC with an in-memory backend,
so we can verify complete API logic without external dependency flakiness.

Run:
    python tests/test_api_endpoints.py
"""

import asyncio
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from services import auth_service, firebase_service, patient_service
from dependencies import jwt_bearer


class InMemoryStore:
    def __init__(self):
        self.users = {}
        self.patients = {}
        self.auth_states = {}

    @staticmethod
    def _now_iso():
        return datetime.utcnow().isoformat()

    async def get_user(self, uid):
        return deepcopy(self.users.get(uid))

    async def create_user(self, user_data):
        data = deepcopy(user_data)
        data.setdefault("createdAt", self._now_iso())
        data.setdefault("lastLogin", self._now_iso())
        self.users[data["uid"]] = data
        return deepcopy(data)

    async def update_user(self, uid, data):
        if uid not in self.users:
            raise ValueError(f"User not found: {uid}")
        self.users[uid].update(deepcopy(data))
        return deepcopy(self.users[uid])

    async def update_last_login(self, uid):
        if uid in self.users:
            self.users[uid]["lastLogin"] = self._now_iso()

    async def check_national_id_unique(self, national_id, exclude_uid=None):
        for uid, user in self.users.items():
            if exclude_uid and uid == exclude_uid:
                continue
            if user.get("nationalId") == national_id:
                return False
        return True

    async def update_kyc_status(self, uid, status, additional_data=None):
        user = await self.get_user(uid)
        if not user:
            raise ValueError(f"User not found: {uid}")

        allowed = {
            "PENDING": {"SUBMITTED"},
            "SUBMITTED": {"VERIFIED", "REJECTED"},
            "REJECTED": {"SUBMITTED"},
            "VERIFIED": set(),
            "VERIFIED_BY_PROVIDER": set(),
        }
        current = user.get("kycStatus", "PENDING")
        if status not in allowed.get(current, set()):
            raise ValueError(f"Invalid KYC transition: {current} -> {status}")

        payload = {"kycStatus": status, "kycUpdatedAt": self._now_iso()}
        if additional_data:
            payload.update(deepcopy(additional_data))
        return await self.update_user(uid, payload)

    async def assign_user_role(self, uid, role, assigned_by):
        return await self.update_user(
            uid,
            {
                "role": role,
                "roleAssignedBy": assigned_by,
                "roleAssignedAt": self._now_iso(),
            },
        )

    async def list_users_by_kyc_status(self, kyc_status, limit=100):
        items = [deepcopy(u) for u in self.users.values() if u.get("kycStatus") == kyc_status]
        return items[:limit]

    async def save_auth_state(self, state, nonce, flow, metadata=None):
        self.auth_states[state] = {
            "state": state,
            "nonce": nonce,
            "flow": flow,
            "metadata": metadata or {},
            "used": False,
            "expiresAt": (datetime.utcnow() + timedelta(minutes=5)).timestamp(),
        }

    async def consume_auth_state(self, state):
        item = self.auth_states.get(state)
        if not item or item.get("used"):
            return None
        if item.get("expiresAt", 0) < datetime.utcnow().timestamp():
            return None
        item["used"] = True
        return deepcopy(item)

    async def create_patient(self, patient_data):
        data = deepcopy(patient_data)
        pid = data.get("patientId") or f"PAT-{len(self.patients)+1:04d}"
        data["patientId"] = pid
        data.setdefault("createdAt", self._now_iso())
        data.setdefault("updatedAt", self._now_iso())
        data.setdefault("isActive", True)
        data.setdefault("identityStatus", "PENDING")
        data.setdefault("kycStatus", "PENDING")
        self.patients[pid] = data
        return deepcopy(data)

    async def get_patient(self, patient_id):
        return deepcopy(self.patients.get(patient_id))

    async def update_patient(self, patient_id, data):
        if patient_id not in self.patients:
            raise ValueError("Patient not found")
        self.patients[patient_id].update(deepcopy(data))
        self.patients[patient_id]["updatedAt"] = self._now_iso()
        return deepcopy(self.patients[patient_id])

    async def check_patient_national_id_unique(self, national_id, exclude_patient_id=None):
        for pid, patient in self.patients.items():
            if exclude_patient_id and pid == exclude_patient_id:
                continue
            if patient.get("nationalId") == national_id:
                return False
        return True

    async def check_esignet_sub_unique(self, esignet_sub, exclude_patient_id=None):
        for pid, patient in self.patients.items():
            if exclude_patient_id and pid == exclude_patient_id:
                continue
            if patient.get("esignetSubjectId") == esignet_sub:
                return False
        return True


def patch_services(store: InMemoryStore):
    async def fake_validate_access_token(token):
        mapping = {
            "token-admin": "admin-1",
            "token-hw": "hw-1",
            "token-doc": "doc-1",
            "token-fr": "fr-1",
            "token-user": "user-1",
        }
        sub = mapping.get(token)
        if not sub:
            raise ValueError("invalid token")
        return {"sub": sub, "iss": "mock", "aud": "mock", "exp": 9999999999}

    async def fake_build_authorization_url():
        return (
            "https://esignet.mock/authorize?response_type=code&state=state-1",
            "state-1",
            "nonce-1",
        )

    async def fake_exchange_code_for_tokens(code):
        return {"access_token": "access-1", "id_token": "id-1", "token_type": "Bearer"}

    async def fake_validate_id_token(id_token, expected_nonce=None):
        if expected_nonce and expected_nonce != "nonce-1":
            raise ValueError("bad nonce")
        return {"sub": "esignet-sub-1", "nonce": expected_nonce or "nonce-1"}

    async def fake_get_userinfo(access_token):
        return {
            "sub": "esignet-sub-1",
            "name": "Demo User",
            "email": "demo@afyaid.test",
            "phone_number": "+237600000001",
            "is_verified": True,
            "individual_id": "NAT-S-001",
        }

    # Auth service patches
    auth_service.validate_access_token = fake_validate_access_token
    jwt_bearer.validate_access_token = fake_validate_access_token
    auth_service.build_authorization_url = fake_build_authorization_url
    auth_service.exchange_code_for_tokens = fake_exchange_code_for_tokens
    auth_service.validate_id_token = fake_validate_id_token
    auth_service.get_userinfo = fake_get_userinfo

    # Firebase service patches
    firebase_service.get_user = store.get_user
    firebase_service.create_user = store.create_user
    firebase_service.update_user = store.update_user
    firebase_service.update_last_login = store.update_last_login
    firebase_service.check_national_id_unique = store.check_national_id_unique
    firebase_service.update_kyc_status = store.update_kyc_status
    firebase_service.assign_user_role = store.assign_user_role
    firebase_service.list_users_by_kyc_status = store.list_users_by_kyc_status
    firebase_service.save_auth_state = store.save_auth_state
    firebase_service.consume_auth_state = store.consume_auth_state

    # Patient service patches
    patient_service.create_patient = store.create_patient
    patient_service.get_patient = store.get_patient
    patient_service.update_patient = store.update_patient
    patient_service.check_patient_national_id_unique = store.check_patient_national_id_unique
    patient_service.check_esignet_sub_unique = store.check_esignet_sub_unique

    # Avoid external startup calls from app lifespan during TestClient creation.
    def fake_init_firebase():
        return None

    async def fake_get_oidc_config():
        return {"issuer": "https://esignet.mock"}

    async def fake_get_jwks():
        return {"keys": [{"kid": "k1"}]}

    main.init_firebase = fake_init_firebase
    main.get_oidc_config = fake_get_oidc_config
    main.get_jwks = fake_get_jwks


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def run_tests():
    store = InMemoryStore()
    patch_services(store)

    # Seed users
    now = datetime.utcnow().isoformat()
    store.users["admin-1"] = {
        "uid": "admin-1", "role": "ADMIN", "kycStatus": "VERIFIED", "isActive": True,
        "hospital": "H1", "matriculeNumber": "A-001", "createdAt": now, "lastLogin": now, "provider": "esignet"
    }
    store.users["hw-1"] = {
        "uid": "hw-1", "role": "HEALTH_WORKER", "kycStatus": "VERIFIED", "isActive": True,
        "hospital": "H1", "matriculeNumber": "HW-001", "createdAt": now, "lastLogin": now, "provider": "esignet"
    }
    store.users["doc-1"] = {
        "uid": "doc-1", "role": "DOCTOR", "kycStatus": "VERIFIED", "isActive": True,
        "hospital": "H1", "matriculeNumber": "D-001", "createdAt": now, "lastLogin": now, "provider": "esignet"
    }
    store.users["fr-1"] = {
        "uid": "fr-1", "role": "FIRST_RESPONDER", "kycStatus": "VERIFIED", "isActive": True,
        "hospital": "H1", "matriculeNumber": "FR-001", "createdAt": now, "lastLogin": now, "provider": "esignet"
    }
    store.users["user-1"] = {
        "uid": "user-1", "role": None, "kycStatus": "PENDING", "isActive": True,
        "hospital": None, "matriculeNumber": None, "createdAt": now, "lastLogin": now, "provider": "esignet"
    }

    client = TestClient(main.app)

    # Health
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200

    # Auth login + callback
    r = client.get("/auth/login")
    assert r.status_code == 200
    state = r.json()["state"]
    cb = client.get("/auth/callback", params={"code": "abc", "state": state})
    assert cb.status_code == 200
    cb_data = cb.json()
    assert cb_data["user"]["uid"] == "esignet-sub-1"

    # Auth me
    me = client.get("/auth/me", headers=auth_header("token-admin"))
    assert me.status_code == 200

    # Profile update cannot change role
    deny_role = client.patch(
        "/users/me/profile",
        headers=auth_header("token-hw"),
        json={"role": "DOCTOR"},
    )
    assert deny_role.status_code == 403

    # KYC submit by pending user
    kyc = client.post(
        "/kyc/submit",
        headers=auth_header("token-user"),
        json={"nationalId": "NAT-U-001", "hospital": "H1", "role": "HEALTH_WORKER", "matriculeNumber": "U-001"},
    )
    assert kyc.status_code == 200
    assert kyc.json()["kycStatus"] == "SUBMITTED"

    # Admin KYC list and actions
    pending = client.get("/admin/kyc/pending", headers=auth_header("token-admin"))
    assert pending.status_code == 200
    assert pending.json()["count"] >= 1

    verify = client.post(
        "/admin/users/user-1/kyc/verify",
        headers=auth_header("token-admin"),
        json={"notes": "ok"},
    )
    assert verify.status_code == 200

    # Assign role admin-only
    no_admin_assign = client.post(
        "/admin/users/user-1/role",
        headers=auth_header("token-hw"),
        json={"role": "DOCTOR"},
    )
    assert no_admin_assign.status_code == 403

    yes_admin_assign = client.post(
        "/admin/users/user-1/role",
        headers=auth_header("token-admin"),
        json={"role": "DOCTOR"},
    )
    assert yes_admin_assign.status_code == 200

    # Register patient (HW)
    reg = client.post(
        "/patients/register",
        headers=auth_header("token-hw"),
        json={
            "fullName": "Patient One",
            "dateOfBirth": "1990-01-01",
            "gender": "M",
            "nationalId": "PAT-NAT-001",
            "bloodType": "O+",
            "allergies": ["Penicillin"],
            "chronicConditions": ["Asthma"],
            "medications": ["Inhaler"],
            "emergencyContact": "Alice +2376000",
        },
    )
    assert reg.status_code == 201
    patient_id = reg.json()["patient"]["patientId"]

    # Duplicate patient nationalId rejected
    dup = client.post(
        "/patients/register",
        headers=auth_header("token-hw"),
        json={"fullName": "Patient Two", "nationalId": "PAT-NAT-001"},
    )
    assert dup.status_code == 409

    # Patient update
    upd = client.patch(
        f"/patients/{patient_id}",
        headers=auth_header("token-hw"),
        json={"phoneNumber": "+237611111111"},
    )
    assert upd.status_code == 200

    # Full patient access by doctor
    full_doctor = client.get(f"/patients/{patient_id}", headers=auth_header("token-doc"))
    assert full_doctor.status_code == 200

    # Summary: doctor yes, responder no
    summary_doc = client.get(f"/patients/{patient_id}/summary", headers=auth_header("token-doc"))
    assert summary_doc.status_code == 200
    summary_fr = client.get(f"/patients/{patient_id}/summary", headers=auth_header("token-fr"))
    assert summary_fr.status_code == 403

    # Emergency: responder yes with minimal fields
    emergency_fr = client.get(f"/patients/{patient_id}/emergency", headers=auth_header("token-fr"))
    assert emergency_fr.status_code == 200
    emergency_data = emergency_fr.json()
    assert "medications" not in emergency_data
    assert "hospital" not in emergency_data

    # Start patient verification
    start_verify = client.post(f"/patients/{patient_id}/verify/start", headers=auth_header("token-hw"))
    assert start_verify.status_code == 200
    state_verify = start_verify.json()["state"]

    # Callback patient verification
    cb_patient = client.get("/auth/callback", params={"code": "abc", "state": state_verify})
    assert cb_patient.status_code == 200
    assert cb_patient.json()["identity_status"] == "VERIFIED"

    print("ALL_API_LOGIC_TESTS_PASSED")


if __name__ == "__main__":
    run_tests()
