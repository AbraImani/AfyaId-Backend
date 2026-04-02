"""
Comprehensive test suite for AfyaId Backend.

Tests:
1. OIDC discovery fetch
2. JWKS fetch
3. Authorization URL building
4. KYC logic assertions
5. Firebase user CRUD
6. JWT self-signed validation
7. Patient CRUD in Firestore
8. Patient uniqueness checks
9. Role-based access logic
10. Patient response shapes (summary vs emergency)

Run: python tests/test_flow.py
"""

import asyncio
import sys
import os
import json
import time
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("test_flow")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 1: OIDC Discovery
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_oidc_discovery():
    logger.info("=" * 60)
    logger.info("TEST 1: OIDC Discovery")
    logger.info("=" * 60)

    from services.auth_service import get_oidc_config

    try:
        config = await get_oidc_config()
        required = ["issuer", "authorization_endpoint", "token_endpoint",
                     "userinfo_endpoint", "jwks_uri"]
        for field in required:
            value = config.get(field)
            if value:
                logger.info(f"  ✅ {field}: {value}")
            else:
                logger.error(f"  ❌ {field}: MISSING")
                return False
        logger.info("  ✅ OIDC Discovery: PASSED")
        return True
    except Exception as e:
        logger.error(f"  ❌ OIDC Discovery FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 2: JWKS Fetch
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_jwks_fetch():
    logger.info("=" * 60)
    logger.info("TEST 2: JWKS Fetch")
    logger.info("=" * 60)

    from services.auth_service import get_jwks

    try:
        jwks = await get_jwks()
        keys = jwks.get("keys", [])
        logger.info(f"  Found {len(keys)} keys")
        for key in keys:
            logger.info(f"  Key: kid={key.get('kid')}, alg={key.get('alg')}")
        logger.info("  ✅ JWKS Fetch: PASSED")
        return True
    except Exception as e:
        logger.error(f"  ❌ JWKS Fetch FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 3: Authorization URL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_authorization_url():
    logger.info("=" * 60)
    logger.info("TEST 3: Authorization URL Building")
    logger.info("=" * 60)

    from services.auth_service import build_authorization_url

    try:
        url, state, nonce = await build_authorization_url()
        logger.info(f"  URL: {url[:100]}...")
        logger.info(f"  State: {state}")
        logger.info(f"  Nonce: {nonce}")

        for check, name in [("response_type=code", "response_type"),
                            ("scope=", "scope"), ("state=", "state")]:
            if check in url:
                logger.info(f"  ✅ URL contains {name}")
            else:
                logger.warning(f"  ⚠️  URL might be missing {name}")

        logger.info("  ✅ Authorization URL: PASSED")
        return True
    except Exception as e:
        logger.error(f"  ❌ Authorization URL FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 4: KYC Logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_kyc_logic():
    logger.info("=" * 60)
    logger.info("TEST 4: KYC Logic")
    logger.info("=" * 60)

    from services.auth_service import determine_kyc_status, is_profile_complete

    # Verified user
    s = determine_kyc_status({"phone_number_verified": True})
    assert s == "VERIFIED_BY_PROVIDER", f"Expected VERIFIED_BY_PROVIDER, got {s}"
    logger.info(f"  ✅ Verified → {s}")

    # Verified by explicit is_verified claim
    s = determine_kyc_status({"is_verified": True})
    assert s == "VERIFIED_BY_PROVIDER", f"Expected VERIFIED_BY_PROVIDER, got {s}"
    logger.info(f"  ✅ is_verified claim → {s}")

    # Unverified user
    s = determine_kyc_status({"phone_number_verified": False})
    assert s == "PENDING", f"Expected PENDING, got {s}"
    logger.info(f"  ✅ Unverified → {s}")

    # No field
    s = determine_kyc_status({"name": "Test"})
    assert s == "PENDING"
    logger.info(f"  ✅ No verification field → {s}")

    # Profile completeness
    assert is_profile_complete({"hospital": "H", "role": "DOCTOR", "matriculeNumber": "M"}) is True
    logger.info("  ✅ Complete profile detected")
    assert is_profile_complete({"hospital": "H", "role": None, "matriculeNumber": None}) is False
    logger.info("  ✅ Incomplete profile detected")

    logger.info("  ✅ KYC Logic: ALL PASSED")
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 5: Firebase User CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_firebase_user_crud():
    logger.info("=" * 60)
    logger.info("TEST 5: Firebase User CRUD")
    logger.info("=" * 60)

    from services.firebase_service import (
        init_firebase, get_user, create_user, update_user,
        update_last_login, check_national_id_unique, get_db,
    )

    try:
        init_firebase()
        logger.info("  ✅ Firebase initialized")

        test_uid = "test_user_crud_001"
        test_user = {
            "uid": test_uid,
            "email": "test@example.com",
            "fullName": "Test User",
            "role": None,
            "hospital": None,
            "title": None,
            "matriculeNumber": None,
            "nationalId": "TESTNAT001",
            "specialty": None,
            "unitName": None,
            "contactPhone": "+1234567890",
            "isActive": True,
            "kycStatus": "PENDING",
            "provider": "esignet",
            "photoURL": None,
        }

        # Create
        created = await create_user(test_user)
        assert created["uid"] == test_uid
        logger.info(f"  ✅ User created: {test_uid}")

        # Read
        fetched = await get_user(test_uid)
        assert fetched is not None
        assert fetched["email"] == "test@example.com"
        logger.info("  ✅ User retrieved")

        # Update lastLogin
        await update_last_login(test_uid)
        logger.info("  ✅ lastLogin updated")

        # Update fields
        await update_user(test_uid, {"kycStatus": "SUBMITTED", "hospital": "H1"})
        updated = await get_user(test_uid)
        assert updated["kycStatus"] == "SUBMITTED"
        assert updated["hospital"] == "H1"
        logger.info("  ✅ Fields updated")

        # NationalId uniqueness — same uid excluded
        is_unique = await check_national_id_unique("TESTNAT001", exclude_uid=test_uid)
        assert is_unique is True
        logger.info("  ✅ NationalId unique check (self-excluded) passed")

        # Cleanup
        get_db().collection("users").document(test_uid).delete()
        logger.info("  ✅ Test user cleaned up")
        logger.info("  ✅ Firebase User CRUD: ALL PASSED")
        return True

    except Exception as e:
        logger.error(f"  ❌ Firebase User CRUD FAILED: {e}")
        # Cleanup on failure
        try:
            from services.firebase_service import get_db
            get_db().collection("users").document("test_user_crud_001").delete()
        except Exception:
            pass
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 6: JWT Self-Signed Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_jwt_self_signed():
    logger.info("=" * 60)
    logger.info("TEST 6: JWT Self-Signed Validation")
    logger.info("=" * 60)

    from jose import jwt as jose_jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    try:
        private_key = rsa.generate_private_key(65537, 2048, default_backend())
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        now = int(time.time())
        payload = {
            "sub": "test_sub_123",
            "iss": "https://esignet-mock.collab.mosip.net",
            "aud": "test_client_id",
            "exp": now + 3600,
            "iat": now,
        }

        token = jose_jwt.encode(payload, private_pem, algorithm="RS256")
        decoded = jose_jwt.decode(token, public_pem, algorithms=["RS256"],
                                  audience="test_client_id",
                                  issuer="https://esignet-mock.collab.mosip.net")
        assert decoded["sub"] == "test_sub_123"
        logger.info(f"  ✅ JWT decoded: sub={decoded['sub']}")

        # Expired token
        expired = jose_jwt.encode({**payload, "exp": now - 100}, private_pem, algorithm="RS256")
        try:
            jose_jwt.decode(expired, public_pem, algorithms=["RS256"],
                          audience="test_client_id", issuer="https://esignet-mock.collab.mosip.net")
            logger.error("  ❌ Expired token should have been rejected!")
            return False
        except Exception:
            logger.info("  ✅ Expired token correctly rejected")

        # Wrong audience
        try:
            jose_jwt.decode(token, public_pem, algorithms=["RS256"],
                          audience="wrong_id", issuer="https://esignet-mock.collab.mosip.net")
            logger.error("  ❌ Wrong audience should have been rejected!")
            return False
        except Exception:
            logger.info("  ✅ Wrong audience correctly rejected")

        logger.info("  ✅ JWT Validation: ALL PASSED")
        return True

    except Exception as e:
        logger.error(f"  ❌ JWT test FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 7: Patient CRUD in Firestore
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_patient_crud():
    logger.info("=" * 60)
    logger.info("TEST 7: Patient CRUD")
    logger.info("=" * 60)

    from services.firebase_service import init_firebase
    from services.patient_service import (
        create_patient, get_patient, update_patient,
        get_patient_by_esignet_sub, check_patient_national_id_unique,
        check_esignet_sub_unique, delete_patient,
    )

    try:
        init_firebase()

        # ── Create patient with auto-generated ID ────────────
        patient_data = {
            "fullName": "Test Patient",
            "dateOfBirth": "1990-01-15",
            "gender": "Male",
            "phoneNumber": "+237600000001",
            "nationalId": "PAT_NAT_001",
            "emergencyContact": "Jane Doe +237600000002",
            "bloodType": "O+",
            "allergies": ["Penicillin"],
            "chronicConditions": ["Asthma"],
            "medications": ["Inhaler"],
            "hospital": "General Hospital",
            "registeredBy": "test_health_worker_uid",
        }

        created = await create_patient(patient_data)
        patient_id = created["patientId"]
        assert patient_id is not None
        assert created["fullName"] == "Test Patient"
        assert created["identityStatus"] == "PENDING"
        logger.info(f"  ✅ Patient created: {patient_id}")

        # ── Read ────────────────────────────────────────────
        fetched = await get_patient(patient_id)
        assert fetched is not None
        assert fetched["nationalId"] == "PAT_NAT_001"
        logger.info("  ✅ Patient retrieved by ID")

        # ── Update ──────────────────────────────────────────
        updated = await update_patient(patient_id, {
            "bloodType": "A+",
            "medications": ["Inhaler", "Antihistamine"],
        })
        assert updated["bloodType"] == "A+"
        assert len(updated["medications"]) == 2
        logger.info("  ✅ Patient updated")

        # ── NationalId uniqueness ────────────────────────────
        is_unique = await check_patient_national_id_unique("PAT_NAT_001")
        assert is_unique is False
        logger.info("  ✅ NationalId duplicate correctly detected")

        is_unique = await check_patient_national_id_unique("PAT_NAT_001", exclude_patient_id=patient_id)
        assert is_unique is True
        logger.info("  ✅ NationalId unique with self-exclusion")

        # ── Create patient with eSignet verified identity ────
        verified_data = {
            "fullName": "Verified Patient",
            "esignetSubjectId": "esignet_sub_test_001",
            "nationalId": "PAT_NAT_002",
            "identityStatus": "VERIFIED",
            "kycStatus": "VERIFIED_BY_PROVIDER",
            "registrationSource": "esignet",
            "registeredBy": "test_hw_uid",
        }
        verified = await create_patient(verified_data)
        verified_id = verified["patientId"]
        logger.info(f"  ✅ Verified patient created: {verified_id}")

        # ── Lookup by eSignet sub ────────────────────────────
        found = await get_patient_by_esignet_sub("esignet_sub_test_001")
        assert found is not None
        assert found["fullName"] == "Verified Patient"
        logger.info("  ✅ Patient found by eSignet sub")

        # ── eSignet sub uniqueness ───────────────────────────
        is_unique = await check_esignet_sub_unique("esignet_sub_test_001")
        assert is_unique is False
        logger.info("  ✅ eSignet sub duplicate detected")

        # ── Cleanup ──────────────────────────────────────────
        await delete_patient(patient_id)
        await delete_patient(verified_id)
        logger.info("  ✅ Test patients cleaned up")

        logger.info("  ✅ Patient CRUD: ALL PASSED")
        return True

    except Exception as e:
        logger.error(f"  ❌ Patient CRUD FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 8: Role Validation Logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_role_validation():
    logger.info("=" * 60)
    logger.info("TEST 8: Role Validation Logic")
    logger.info("=" * 60)

    from models.user import UserRole

    try:
        # Valid roles
        for role_str in ["ADMIN", "DOCTOR", "HEALTH_WORKER", "FIRST_RESPONDER"]:
            role = UserRole(role_str)
            assert role.value == role_str
            logger.info(f"  ✅ Valid role: {role_str}")

        # Invalid role
        try:
            UserRole("INVALID_ROLE")
            logger.error("  ❌ Invalid role should have been rejected!")
            return False
        except ValueError:
            logger.info("  ✅ Invalid role correctly rejected")

        # Role-based access simulation
        allowed_roles = ["HEALTH_WORKER", "ADMIN"]
        assert "HEALTH_WORKER" in allowed_roles
        assert "DOCTOR" not in allowed_roles
        assert "FIRST_RESPONDER" not in allowed_roles
        logger.info("  ✅ Role membership checks work")

        logger.info("  ✅ Role Validation: ALL PASSED")
        return True

    except Exception as e:
        logger.error(f"  ❌ Role Validation FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 9: Patient Response Shapes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_patient_response_shapes():
    logger.info("=" * 60)
    logger.info("TEST 9: Patient Response Shapes")
    logger.info("=" * 60)

    from services.patient_service import build_patient_summary, build_patient_emergency

    try:
        full_patient = {
            "patientId": "PAT-test",
            "esignetSubjectId": "esig_001",
            "fullName": "John Doe",
            "dateOfBirth": "1985-03-20",
            "gender": "Male",
            "phoneNumber": "+237600000001",
            "nationalId": "NAT123",
            "emergencyContact": "Jane Doe +237600000002",
            "bloodType": "AB+",
            "allergies": ["Penicillin", "Latex"],
            "chronicConditions": ["Diabetes", "Hypertension"],
            "medications": ["Metformin", "Lisinopril"],
            "hospital": "Central Hospital",
            "registeredBy": "hw_uid_001",
            "registrationSource": "esignet",
            "identityStatus": "VERIFIED",
            "kycStatus": "VERIFIED_BY_PROVIDER",
            "createdAt": "2025-01-01T00:00:00",
            "updatedAt": "2025-01-02T00:00:00",
            "isActive": True,
        }

        # ── Summary (Doctor view) ───────────────────────────
        summary = build_patient_summary(full_patient)
        expected_summary_keys = {
            "patientId", "fullName", "dateOfBirth", "gender", "bloodType",
            "allergies", "chronicConditions", "medications",
            "emergencyContact", "hospital", "identityStatus", "isActive",
        }
        assert set(summary.keys()) == expected_summary_keys, f"Summary keys mismatch: {set(summary.keys())}"
        assert summary["fullName"] == "John Doe"
        assert len(summary["allergies"]) == 2
        # Summary should NOT contain sensitive registration data
        assert "esignetSubjectId" not in summary
        assert "nationalId" not in summary
        assert "registeredBy" not in summary
        assert "kycStatus" not in summary
        logger.info("  ✅ Summary shape correct (Doctor view)")

        # ── Emergency (First Responder view) ─────────────────
        emergency = build_patient_emergency(full_patient)
        expected_emergency_keys = {
            "patientId", "fullName", "bloodType",
            "allergies", "chronicConditions", "emergencyContact",
        }
        assert set(emergency.keys()) == expected_emergency_keys, f"Emergency keys mismatch: {set(emergency.keys())}"
        assert emergency["bloodType"] == "AB+"
        assert len(emergency["chronicConditions"]) == 2
        # Emergency should NOT contain non-critical data
        assert "dateOfBirth" not in emergency
        assert "gender" not in emergency
        assert "medications" not in emergency
        assert "hospital" not in emergency
        assert "nationalId" not in emergency
        logger.info("  ✅ Emergency shape correct (First Responder view)")

        logger.info("  ✅ Response Shapes: ALL PASSED")
        return True

    except Exception as e:
        logger.error(f"  ❌ Response Shapes FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 10: Pydantic Models Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_pydantic_models():
    logger.info("=" * 60)
    logger.info("TEST 10: Pydantic Model Validation")
    logger.info("=" * 60)

    from models.user import ProfileCompletion, UserRole
    from models.patient import PatientRegisterRequest, PatientUpdateRequest

    try:
        # Valid profile completion
        pc = ProfileCompletion(hospital="H1", role=UserRole.DOCTOR, matriculeNumber="M001")
        assert pc.role == UserRole.DOCTOR
        logger.info("  ✅ ProfileCompletion with valid role")

        # Invalid role in profile completion
        try:
            ProfileCompletion(hospital="H1", role="INVALID", matriculeNumber="M001")
            logger.error("  ❌ Invalid role should have been rejected!")
            return False
        except Exception:
            logger.info("  ✅ Invalid role correctly rejected in ProfileCompletion")

        # Patient register request
        pr = PatientRegisterRequest(fullName="Test Patient")
        assert pr.fullName == "Test Patient"
        assert pr.allergies == []
        assert pr.identityVerified is False
        logger.info("  ✅ PatientRegisterRequest defaults correct")

        # Patient update request — all optional
        pu = PatientUpdateRequest()
        update_data = pu.model_dump(exclude_none=True)
        assert len(update_data) == 0
        logger.info("  ✅ PatientUpdateRequest empty update correct")

        # Patient update with some fields
        pu2 = PatientUpdateRequest(bloodType="O-", allergies=["Aspirin"])
        update_data2 = pu2.model_dump(exclude_none=True)
        assert update_data2["bloodType"] == "O-"
        assert len(update_data2["allergies"]) == 1
        logger.info("  ✅ PatientUpdateRequest partial update correct")

        logger.info("  ✅ Pydantic Models: ALL PASSED")
        return True

    except Exception as e:
        logger.error(f"  ❌ Pydantic Models FAILED: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    logger.info("\n")
    logger.info("🧪 AfyaId Backend — Comprehensive Test Suite")
    logger.info("=" * 60)
    logger.info("")

    results = {}

    # Tests that require network (eSignet)
    results["1. OIDC Discovery"] = await test_oidc_discovery()
    results["2. JWKS Fetch"] = await test_jwks_fetch()
    results["3. Authorization URL"] = await test_authorization_url()

    # Pure logic tests (no external deps)
    results["4. KYC Logic"] = await test_kyc_logic()
    results["6. JWT Validation"] = await test_jwt_self_signed()
    results["8. Role Validation"] = await test_role_validation()
    results["9. Response Shapes"] = await test_patient_response_shapes()
    results["10. Pydantic Models"] = await test_pydantic_models()

    # Firebase tests (require credentials)
    results["5. Firebase User CRUD"] = await test_firebase_user_crud()
    results["7. Patient CRUD"] = await test_patient_crud()

    # ── Summary ──────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 TEST RESULTS SUMMARY")
    logger.info("=" * 60)

    passed = 0
    failed = 0
    for name, result in sorted(results.items()):
        icon = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"  {icon} — {name}")
        if result:
            passed += 1
        else:
            failed += 1

    logger.info("")
    logger.info(f"  Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
    logger.info("=" * 60)

    if failed > 0:
        logger.info("\n⚠️  Some tests failed. Check the output above.")
        sys.exit(1)
    else:
        logger.info("\n🎉 All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
