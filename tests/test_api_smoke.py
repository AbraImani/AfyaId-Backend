"""API smoke tests for AfyaId.

These tests exercise the FastAPI routes with mocked external services so we can
verify endpoint logic, RBAC, payload shapes, and response status codes even when
external dependencies such as eSignet and Firestore are unavailable.

Run:
    python tests/test_api_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from typing import Any, Dict
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from dependencies import jwt_bearer
from services import auth_service, firebase_service, patient_service

app = main.app
client = TestClient(app)


@contextmanager
def override_current_user(sub: str = "staff-uid"):
    async def _current_user():
        return {"sub": sub}

    previous = app.dependency_overrides.get(jwt_bearer.get_current_user)
    app.dependency_overrides[jwt_bearer.get_current_user] = _current_user
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(jwt_bearer.get_current_user, None)
        else:
            app.dependency_overrides[jwt_bearer.get_current_user] = previous


@contextmanager
def patched(**replacements: Dict[str, Any]):
    originals = {}
    try:
        for dotted_name, replacement in replacements.items():
            module_name, attr_name = dotted_name.rsplit(".", 1)
            module = __import__(module_name, fromlist=[attr_name])
            originals[dotted_name] = getattr(module, attr_name)
            setattr(module, attr_name, replacement)
        yield
    finally:
        for dotted_name, original in originals.items():
            module_name, attr_name = dotted_name.rsplit(".", 1)
            module = __import__(module_name, fromlist=[attr_name])
            setattr(module, attr_name, original)


async def async_return(value):
    return value


def assert_ok(response, expected_status=200):
    assert response.status_code == expected_status, response.text
    return response.json()


def test_root_and_health():
    assert_ok(client.get("/"))
    assert_ok(client.get("/health"))


def test_auth_login():
    async def fake_build_authorization_url():
        return ("https://esignet.example/authorize?x=1", "state123", "nonce123")

    async def fake_save_auth_state(**kwargs):
        return None

    with patched(
        **{
            "services.auth_service.build_authorization_url": fake_build_authorization_url,
            "services.firebase_service.save_auth_state": fake_save_auth_state,
        }
    ):
        payload = assert_ok(client.get("/auth/login"))
        assert payload["authorization_url"].startswith("https://esignet.example/authorize")
        assert payload["state"] == "state123"


def test_auth_callback_staff_flow():
    async def fake_consume_auth_state(state: str):
        return {"nonce": "nonce123", "flow": "staff_login", "metadata": {}}

    async def fake_exchange_code_for_tokens(code: str):
        return {"access_token": "access.jwt", "id_token": "id.jwt"}

    async def fake_validate_id_token(id_token: str, expected_nonce: str | None = None):
        assert expected_nonce == "nonce123"
        return {"sub": "user-sub-1", "nonce": expected_nonce}

    async def fake_get_userinfo(access_token: str):
        return {
            "sub": "user-sub-1",
            "name": "Alice Staff",
            "email": "alice@example.com",
            "picture": "https://example.com/a.png",
            "phone_number": "+237600000000",
            "is_verified": True,
            "individual_id": "NAT-001",
        }

    async def fake_get_user(uid: str):
        return None

    async def fake_create_user(user_data: Dict[str, Any]):
        user_data = dict(user_data)
        user_data["createdAt"] = "2026-04-01T00:00:00"
        user_data["lastLogin"] = "2026-04-01T00:00:00"
        return user_data

    async def fake_update_last_login(uid: str):
        return None

    with patched(
        **{
            "services.firebase_service.consume_auth_state": fake_consume_auth_state,
            "services.auth_service.exchange_code_for_tokens": fake_exchange_code_for_tokens,
            "services.auth_service.validate_id_token": fake_validate_id_token,
            "services.auth_service.get_userinfo": fake_get_userinfo,
            "services.firebase_service.get_user": fake_get_user,
            "services.firebase_service.create_user": fake_create_user,
            "services.firebase_service.update_last_login": fake_update_last_login,
        }
    ):
        payload = assert_ok(client.get("/auth/callback?code=abc&state=state123"))
        assert payload["user"]["uid"] == "user-sub-1"
        assert payload["kyc_status"] == "VERIFIED_BY_PROVIDER"
        assert payload["profile_complete"] is False


def test_auth_me():
    async def fake_get_user(uid: str):
        return {
            "uid": uid,
            "email": "alice@example.com",
            "fullName": "Alice Staff",
            "role": "DOCTOR",
            "hospital": "Central Hospital",
            "matriculeNumber": "MAT-1",
            "kycStatus": "VERIFIED_BY_PROVIDER",
            "provider": "esignet",
            "isActive": True,
        }

    with override_current_user("user-sub-1"):
        with patched(**{"services.firebase_service.get_user": fake_get_user}):
            payload = assert_ok(client.get("/auth/me", headers={"Authorization": "Bearer token"}))
            assert payload["user"]["uid"] == "user-sub-1"
            assert payload["profile_complete"] is True


def test_kyc_submit():
    async def fake_get_user(uid: str):
        return {"uid": uid, "kycStatus": "PENDING"}

    async def fake_check_national_id_unique(national_id: str, exclude_uid: str | None = None):
        return True

    async def fake_update_kyc_status(uid: str, status: str, additional_data=None):
        return {
            "uid": uid,
            "kycStatus": status,
            **(additional_data or {}),
        }

    with override_current_user("user-sub-2"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_user,
                "services.firebase_service.check_national_id_unique": fake_check_national_id_unique,
                "services.firebase_service.update_kyc_status": fake_update_kyc_status,
            }
        ):
            payload = assert_ok(
                client.post(
                    "/kyc/submit",
                    json={
                        "nationalId": "NAT-002",
                        "hospital": "Central Hospital",
                        "role": "DOCTOR",
                        "matriculeNumber": "MAT-2",
                    },
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert payload["kycStatus"] == "SUBMITTED"
            assert payload["user"]["nationalId"] == "NAT-002"


def test_users_profile_update_reject_role_change():
    async def fake_get_user(uid: str):
        return {"uid": uid, "kycStatus": "VERIFIED_BY_PROVIDER", "role": "DOCTOR"}

    with override_current_user("user-sub-3"):
        with patched(**{"services.firebase_service.get_user": fake_get_user}):
            response = client.patch(
                "/users/me/profile",
                json={"role": "ADMIN"},
                headers={"Authorization": "Bearer token"},
            )
            assert response.status_code == 403, response.text


def test_users_profile_update_ok():
    async def fake_get_user(uid: str):
        return {"uid": uid, "kycStatus": "VERIFIED_BY_PROVIDER", "role": "DOCTOR"}

    async def fake_check_national_id_unique(national_id: str, exclude_uid: str | None = None):
        return True

    async def fake_update_user(uid: str, data: Dict[str, Any]):
        return {"uid": uid, **data}

    with override_current_user("user-sub-3"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_user,
                "services.firebase_service.check_national_id_unique": fake_check_national_id_unique,
                "services.firebase_service.update_user": fake_update_user,
            }
        ):
            payload = assert_ok(
                client.patch(
                    "/users/me/profile",
                    json={"fullName": "Alice Updated", "nationalId": "NAT-003"},
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert payload["user"]["fullName"] == "Alice Updated"


def test_patient_register_and_get_routes():
    async def fake_get_user(uid: str):
        return {"uid": uid, "role": "HEALTH_WORKER", "hospital": "Central Hospital"}

    async def fake_check_patient_national_id_unique(national_id: str, exclude_patient_id=None):
        return True

    async def fake_check_esignet_sub_unique(esignet_sub: str, exclude_patient_id=None):
        return True

    async def fake_create_patient(patient_data: Dict[str, Any]):
        data = dict(patient_data)
        data["patientId"] = "PAT-001"
        data.setdefault("identityStatus", "PENDING")
        data.setdefault("kycStatus", "PENDING")
        return data

    async def fake_get_patient(patient_id: str):
        return {
            "patientId": patient_id,
            "fullName": "Bob Patient",
            "bloodType": "O+",
            "allergies": ["Penicillin"],
            "chronicConditions": ["Asthma"],
            "medications": ["Inhaler"],
            "emergencyContact": "Jane Doe",
            "hospital": "Central Hospital",
            "identityStatus": "PENDING",
            "isActive": True,
        }

    async def fake_get_doctor(uid: str):
        return {"uid": uid, "role": "DOCTOR", "hospital": "Central Hospital"}

    async def fake_get_first_responder(uid: str):
        return {"uid": uid, "role": "FIRST_RESPONDER", "hospital": "Central Hospital"}

    async def fake_update_patient(patient_id: str, data: Dict[str, Any]):
        current = await fake_get_patient(patient_id)
        current.update(data)
        return current

    with override_current_user("hw-1"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_user,
                "services.patient_service.check_patient_national_id_unique": fake_check_patient_national_id_unique,
                "services.patient_service.check_esignet_sub_unique": fake_check_esignet_sub_unique,
                "services.patient_service.create_patient": fake_create_patient,
                "services.patient_service.get_patient": fake_get_patient,
                "services.patient_service.update_patient": fake_update_patient,
            }
        ):
            created = assert_ok(
                client.post(
                    "/patients/register",
                    json={"fullName": "Bob Patient", "nationalId": "NAT-P-1"},
                    headers={"Authorization": "Bearer token"},
                ),
                expected_status=201,
            )
            patient_id = created["patient"]["patientId"]
            assert patient_id == "PAT-001"

            fetched = assert_ok(
                client.get(f"/patients/{patient_id}", headers={"Authorization": "Bearer token"})
            )
            assert fetched["patient"]["fullName"] == "Bob Patient"

            updated = assert_ok(
                client.patch(
                    f"/patients/{patient_id}",
                    json={"bloodType": "A+"},
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert updated["patient"]["bloodType"] == "A+"

    with override_current_user("doctor-1"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_doctor,
                "services.patient_service.get_patient": fake_get_patient,
            }
        ):
            summary = assert_ok(
                client.get(f"/patients/PAT-001/summary", headers={"Authorization": "Bearer token"})
            )
            assert summary["fullName"] == "Bob Patient"

    with override_current_user("fr-1"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_first_responder,
                "services.patient_service.get_patient": fake_get_patient,
            }
        ):
            emergency = assert_ok(
                client.get(f"/patients/PAT-001/emergency", headers={"Authorization": "Bearer token"})
            )
            assert emergency["bloodType"] == "O+"


def test_patient_verification_start_and_callback():
    async def fake_get_patient(patient_id: str):
        return {"patientId": patient_id, "fullName": "Bob Patient"}

    async def fake_get_hw(uid: str):
        return {"uid": uid, "role": "HEALTH_WORKER", "hospital": "Central Hospital"}

    async def fake_build_authorization_url():
        return ("https://esignet.example/authorize?x=1", "state-p", "nonce-p")

    async def fake_save_auth_state(**kwargs):
        return None

    async def fake_consume_auth_state(state: str):
        return {
            "nonce": "nonce-p",
            "flow": "patient_identity_verification",
            "metadata": {"patientId": "PAT-001"},
        }

    async def fake_exchange_code_for_tokens(code: str):
        return {"access_token": "access.jwt", "id_token": "id.jwt"}

    async def fake_validate_id_token(id_token: str, expected_nonce: str | None = None):
        return {"sub": "patient-sub-1", "nonce": expected_nonce}

    async def fake_get_userinfo(access_token: str):
        return {"sub": "patient-sub-1", "is_verified": True}

    async def fake_check_esignet_sub_unique(esignet_sub: str, exclude_patient_id=None):
        return True

    async def fake_update_patient(patient_id: str, data: Dict[str, Any]):
        return {"patientId": patient_id, "fullName": "Bob Patient", **data}

    with override_current_user("hw-1"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_hw,
                "services.patient_service.get_patient": fake_get_patient,
                "services.auth_service.build_authorization_url": fake_build_authorization_url,
                "services.firebase_service.save_auth_state": fake_save_auth_state,
                "services.firebase_service.consume_auth_state": fake_consume_auth_state,
                "services.auth_service.exchange_code_for_tokens": fake_exchange_code_for_tokens,
                "services.auth_service.validate_id_token": fake_validate_id_token,
                "services.auth_service.get_userinfo": fake_get_userinfo,
                "services.patient_service.check_esignet_sub_unique": fake_check_esignet_sub_unique,
                "services.patient_service.update_patient": fake_update_patient,
            }
        ):
            started = assert_ok(
                client.post(
                    "/patients/PAT-001/verify/start",
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert started["state"] == "state-p"

            callback = assert_ok(
                client.get("/auth/callback?code=abc&state=state-p")
            )
            assert callback["identity_status"] == "VERIFIED"
            assert callback["patient"]["esignetSubjectId"] == "patient-sub-1"


def test_admin_endpoints():
    async def fake_get_user(uid: str):
        if uid == "admin-1":
            return {"uid": uid, "role": "ADMIN", "kycStatus": "VERIFIED_BY_PROVIDER"}
        return {"uid": uid, "role": "DOCTOR", "kycStatus": "SUBMITTED"}

    async def fake_assign_user_role(uid: str, role: str, assigned_by: str):
        return {"uid": uid, "role": role, "roleAssignedBy": assigned_by}

    async def fake_update_kyc_status(uid: str, status: str, additional_data=None):
        return {"uid": uid, "kycStatus": status, **(additional_data or {})}

    async def fake_list_users_by_kyc_status(kyc_status: str, limit: int = 100):
        return [{"uid": "u1", "kycStatus": kyc_status}]

    with override_current_user("admin-1"):
        with patched(
            **{
                "services.firebase_service.get_user": fake_get_user,
                "services.firebase_service.assign_user_role": fake_assign_user_role,
                "services.firebase_service.update_kyc_status": fake_update_kyc_status,
                "services.firebase_service.list_users_by_kyc_status": fake_list_users_by_kyc_status,
            }
        ):
            role_resp = assert_ok(
                client.post(
                    "/admin/users/user-2/role",
                    json={"role": "DOCTOR"},
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert role_resp["user"]["role"] == "DOCTOR"

            verify_resp = assert_ok(
                client.post(
                    "/admin/users/user-2/kyc/verify",
                    json={"notes": "ok"},
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert verify_resp["user"]["kycStatus"] == "VERIFIED"

            reject_resp = assert_ok(
                client.post(
                    "/admin/users/user-2/kyc/reject",
                    json={"reason": "invalid docs"},
                    headers={"Authorization": "Bearer token"},
                )
            )
            assert reject_resp["user"]["kycStatus"] == "REJECTED"

            pending_resp = assert_ok(
                client.get("/admin/kyc/pending", headers={"Authorization": "Bearer token"})
            )
            assert pending_resp["count"] == 1


async def run_all():
    tests = [
        test_root_and_health,
        test_auth_login,
        test_auth_callback_staff_flow,
        test_auth_me,
        test_kyc_submit,
        test_users_profile_update_reject_role_change,
        test_users_profile_update_ok,
        test_patient_register_and_get_routes,
        test_patient_verification_start_and_callback,
        test_admin_endpoints,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            result = test()
            if asyncio.iscoroutine(result):
                await result
            print(f"[PASS] {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"[FAIL] {test.__name__}: {exc}")
            failed += 1

    print(f"\nAPI smoke summary: passed={passed} failed={failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run_all())
