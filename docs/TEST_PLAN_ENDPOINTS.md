# API Test Plan for AfyaID (complete verification before Flutter validation)

This document is the field test plan to verify that all endpoints work well, especially those with Authorization Bearer.

## 1) Objective

Validate on your side, step by step:

- that public endpoints respond correctly,
- that Bearer security properly blocks unauthorized access,
- that protected endpoints work well with a valid token,
- that role restrictions are correct (ADMIN, DOCTOR, HEALTH_WORKER, FIRST_RESPONDER),
- that Firebase is properly used (not a local fallback cache).

## 2) Test information

Production API base:

- https://afya-id-419586439350.europe-west2.run.app

Useful links:

- Swagger: https://afya-id-419586439350.europe-west2.run.app/docs
- OpenAPI JSON: https://afya-id-419586439350.europe-west2.run.app/openapi.json

## 3) Prerequisites before starting

1. Have curl or Postman.
2. Have at least 1 valid Bearer token (even if eSignet is still mock, test tokens can come from your environment).
3. Ideally have 4 different tokens:
   - ADMIN token
   - HEALTH_WORKER token
   - DOCTOR token
   - FIRST_RESPONDER token
4. If you don't have these 4 roles yet, start with an ADMIN token then assign roles using admin endpoints.

## 4) Suggested working variables (PowerShell)

Command to adapt on your machine:

```powershell
$BASE = "https://afya-id-419586439350.europe-west2.run.app"
$TOKEN_ADMIN = "put_a_real_admin_token"
$TOKEN_HW = "put_a_real_health_worker_token"
$TOKEN_DOCTOR = "put_a_real_doctor_token"
$TOKEN_FR = "put_a_real_first_responder_token"
```

## 5) Step A - Smoke test public endpoints

Action 1:

- GET /
- expected: 200 and version 1.0.0

Action 2:

- GET /health
- expected: 200

Action 3:

- GET /docs
- expected: 200

Action 4:

- GET /openapi.json
- expected: 200

Action 5:

- GET /auth/login
- expected: 200 with authorization_url and state
- this test is important because it confirms that state storage in Firestore works

## 6) Step B - Bearer security verification (mandatory)

For each protected endpoint, perform these 2 tests before the positive test:

Security test 1 (no token):

- expected: 401

Security test 2 (invalid token):

- expected: 401

Only then, perform the test with valid token.

## 7) Step C - User endpoints verification

### C1) GET /auth/me

- with valid token (any authenticated role)
- expected: 200 and user returned

### C2) PATCH /users/me/profile

- with valid token
- recommended minimal body:
  - fullName
  - hospital
  - contactPhone
- expected: 200

Critical negative test:

- send role in body
- expected: 403 (role changes are restricted)

### C3) POST /kyc/submit

- with valid token
- example body:
  - nationalId
  - hospital
  - role
  - matriculeNumber
- expected: 200 and kycStatus SUBMITTED

Negative test:

- nationalId already used
- expected: 409

## 8) Step D - Role preparation (if necessary)

If you only have an ADMIN token at the start:

1. Create or identify 3 target users (doctor, health worker, first responder).
2. ADMIN calls:
   - POST /admin/users/{uid}/role for DOCTOR
   - POST /admin/users/{uid}/role for HEALTH_WORKER
   - POST /admin/users/{uid}/role for FIRST_RESPONDER
3. Then verify with their respective tokens.

## 9) Step E - Complete patient flow (most important)

### E1) POST /patients/register

- role: HEALTH_WORKER or ADMIN
- expected: 201
- keep the returned patientId (important for the rest)

### E2) PATCH /patients/{patient_id}

- role: HEALTH_WORKER or ADMIN
- expected: 200

### E3) GET /patients/{patient_id}

- authorized roles: HEALTH_WORKER, DOCTOR, ADMIN
- expected: 200

Negative test:

- with FIRST_RESPONDER token
- expected: 403

### E4) GET /patients/{patient_id}/summary

- authorized roles: DOCTOR, ADMIN
- expected: 200

Negative test:

- with HEALTH_WORKER token
- expected: 403

### E5) GET /patients/{patient_id}/emergency

- authorized roles: FIRST_RESPONDER, DOCTOR, ADMIN
- expected: 200

Negative test:

- without token
- expected: 401

### E6) POST /patients/{patient_id}/verify/start

- authorized roles: HEALTH_WORKER, ADMIN
- expected: 200 with authorization_url and state

## 10) Step F - Admin endpoints

### F1) GET /admin/kyc/pending

- role: ADMIN
- expected: 200

### F2) POST /admin/users/{uid}/role

- role: ADMIN
- expected: 200

### F3) POST /admin/users/{uid}/kyc/verify

- role: ADMIN
- expected: 200

### F4) POST /admin/users/{uid}/kyc/reject

- role: ADMIN
- expected: 200

Global negative test for admin:

- retry each admin endpoint with non-ADMIN token
- expected: 403

## 11) Real Firebase verification

Do these checks during tests:

1. /auth/login must no longer return error database default does not exist.
2. Patient creations are visible in Firestore project afya-id.
3. Profile updates and KYC appear in users/patients collections.

If 1, 2, 3 are true, then backend is properly connected to real Firebase.

## 12) Definition of Ready to share with Flutter

You can confirm to the Flutter team that it's OK when:

1. All public tests are green.
2. All security 401 and 403 tests are green.
3. All positive tests of protected endpoints are green with valid tokens.
4. Complete patient flow E1 to E6 is green.
5. Data appears in Firestore project afya-id.

## 13) Quick final checklist

- [ ] GET / OK
- [ ] GET /health OK
- [ ] GET /auth/login OK
- [ ] Security 401 without token verified
- [ ] Security 401 invalid token verified
- [ ] Security 403 incorrect role verified
- [ ] patients/register OK
- [ ] patients/{id} OK
- [ ] patients/{id}/summary OK
- [ ] patients/{id}/emergency OK
- [ ] admin endpoints OK
- [ ] Data visible in Firestore afya-id
