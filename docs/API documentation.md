# API Documentation for AfyaID

## 1. Introduction

This documentation explains what has been built in the API for better integration with Flutter.

The AfyaID API is our backend for managing authentication, staff profiles, patients, and the KYC flow.

In practice, the backend does three main things:

1. Authenticate users via eSignet.
2. Store and read business data in Firebase Firestore.
3. Protect access according to the user's role.

Concretely for Flutter:

- The mobile application calls this API.
- The API reads/writes to Firebase.
- The API communicates with eSignet once we have real credentials.

## 2. Architecture

```mermaid
flowchart LR
    F[Flutter App] -->|HTTPS JSON| B[FastAPI / AfyaID]
    B -->|Firestore SDK| FS[(Firebase Firestore)]
    B -->|OIDC / OAuth2| ES[eSignet]
    ES -->|ID Token + Userinfo| B
```

### Quick read

- Flutter sends requests to FastAPI.
- FastAPI reads and writes to Firestore.
- eSignet is used for OIDC authentication.
- In production, Firebase is real.
- eSignet is still in mock mode until real `CLIENT_ID` and `CLIENT_SECRET` are provided.

## 3. Authentication

### Login flow

```mermaid
sequenceDiagram
    participant U as Flutter User
    participant A as AfyaID Backend
    participant E as eSignet
    participant F as Firestore

    U->>A: GET /auth/login
    A->>F: save state + nonce
    A-->>U: authorization_url
    U->>E: open eSignet page
    E-->>A: GET /auth/callback?code=...&state=...
    A->>F: verify state, nonce
    A->>E: exchange code for tokens
    E-->>A: access_token + id_token
    A->>E: read userinfo
    A->>F: create or update user
    A-->>U: profile + tokens + KYC status
```

### What is already real now

- Firebase validation,
- user creation and reading,
- state and nonce management,
- role and KYC logic,
- patient routes.

### What still depends on real eSignet

- Real OAuth code exchange,
- Real production `id_token` validation,
- Real `userinfo` reading,
- Real patient identity verification.

## 4. Roles and Permissions

### Admin

- Can assign a role to staff.
- Can validate or reject a KYC.
- Can read patient views.
- Can read the pending KYC list.

### Doctor

- Can read the complete patient file.
- Can read medical summary.

### Health Worker

- Can create a patient.
- Can update a patient.
- Can start eSignet patient verification.
- Can read a complete patient.

### First Responder

- Can only read the patient emergency view.
- Does not see the complete file.

## 5. Patient Flow

```mermaid
flowchart TD
    A[Health Worker] --> B[POST /patients/register]
    B --> C{eSignet Identity?}
    C -->|Yes| D[Status identityStatus=VERIFIED]
    C -->|No| E[Status identityStatus=PENDING]
  A --> F[PATCH /patients/:patient_id]
  A --> G[POST /patients/:patient_id/verify/start]
    G --> H[Return to eSignet]
    H --> I[GET /auth/callback]
    I --> J[Update patient Firestore]
    J --> K[Admin/Doctor/First Responder read adapted views]
```

### Functional summary

- `register` creates the patient.
- `update` modifies the patient.
- `verify/start` starts eSignet verification.
- `/summary` gives medical view for doctor.
- `/emergency` gives short view for first responder.

## 6. Production Base URL

API URL in production:

`https://afya-id-419586439350.europe-west2.run.app`

All endpoints documented here use this base URL.

## 7. Request Authentication

Protected routes use `Authorization: Bearer <token>`.

Example:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

## 8. Endpoints

### 8.1 Health

#### GET /

Description: Verifies that the API responds.

Example response:

```json
{
  "status": "healthy",
  "service": "AfyaId Backend",
  "version": "1.0.0",
  "provider": "eSignet (MOSIP)",
  "docs": "/docs"
}
```

#### GET /health

Description: Returns configuration status.

Example response:

```json
{
  "status": "healthy",
  "esignet_base_url": "https://esignet-mock.collab.mosip.net",
  "client_id_configured": false,
  "firebase_configured": true,
  "private_key_configured": false
}
```

### 8.2 Authentication

#### GET /auth/login

Required role: None, but this is the login entry point.

Description: Generates eSignet URL, saves `state` and `nonce`.

Example response:

```json
{
  "authorization_url": "https://...",
  "state": "f2d1..."
}
```

#### GET /auth/callback

Required role: None (called by eSignet).

Description: Exchanges OAuth code for tokens, creates/updates user in Firestore.

Query parameters:

- `code` (from eSignet)
- `state` (from eSignet)

Example response:

```json
{
  "message": "Authentication successful",
  "access_token": "eyJ...",
  "id_token": "eyJ...",
  "token_type": "Bearer",
  "user": {
    "uid": "12345",
    "role": "DOCTOR",
    "provider": "esignet"
  }
}
```

#### GET /auth/me

Required role: Any authenticated role.

Description: Returns current user profile.

Example response:

```json
{
  "uid": "12345",
  "email": "doctor@example.com",
  "fullName": "Dr. Jane Doe",
  "role": "DOCTOR",
  "hospital": "Central Hospital",
  "kycStatus": "VERIFIED",
  "profileComplete": true
}
```

### 8.3 User Management

#### PATCH /users/me/profile

Required role: Any authenticated role.

Description: Updates current user profile.

Request body:

```json
{
  "fullName": "Dr. Jane Doe",
  "hospital": "Central Hospital",
  "contactPhone": "+243900000000",
  "title": "Dr",
  "specialty": "General Medicine",
  "photoURL": "https://..."
}
```

Response:

```json
{
  "uid": "12345",
  "fullName": "Dr. Jane Doe",
  "message": "Profile updated successfully"
}
```

#### POST /kyc/submit

Required role: Any authenticated role.

Description: Submits KYC information for the current user.

Request body:

```json
{
  "nationalId": "NAT-001",
  "hospital": "Central Hospital",
  "role": "DOCTOR",
  "matriculeNumber": "MAT-001",
  "documentUrl": "https://..."
}
```

Response:

```json
{
  "message": "KYC submitted successfully",
  "kycStatus": "SUBMITTED",
  "uid": "12345"
}
```

### 8.4 Patient Management

#### POST /patients/register

Required role: HEALTH_WORKER, ADMIN.

Description: Creates a new patient.

Request body:

```json
{
  "firstName": "John",
  "lastName": "Doe",
  "dateOfBirth": "1990-01-15",
  "gender": "M",
  "nationalId": "ID-001",
  "bloodType": "O+",
  "phone": "+243900000000"
}
```

Response (201):

```json
{
  "message": "Patient registered successfully",
  "patientId": "PAT-001",
  "patient": {
    "id": "PAT-001",
    "fullName": "John Doe",
    "identityStatus": "PENDING",
    "kycStatus": "PENDING"
  }
}
```

#### GET /patients/{patient_id}

Required role: HEALTH_WORKER, DOCTOR, ADMIN.

Description: Retrieves complete patient data.

Response:

```json
{
  "patientId": "PAT-001",
  "fullName": "John Doe",
  "dateOfBirth": "1990-01-15",
  "nationalId": "ID-001",
  "bloodType": "O+",
  "phone": "+243900000000",
  "allergies": ["Penicillin"],
  "chronicConditions": ["Asthma"],
  "medications": ["Inhaler"],
  "emergencyContact": "Jane Doe",
  "identityStatus": "PENDING",
  "kycStatus": "PENDING"
}
```

#### GET /patients/{patient_id}/summary

Required role: DOCTOR, ADMIN.

Description: Retrieves patient medical summary (doctor view).

Response:

```json
{
  "patientId": "PAT-001",
  "fullName": "John Doe",
  "bloodType": "O+",
  "allergies": ["Penicillin"],
  "chronicConditions": ["Asthma"],
  "medications": ["Inhaler"]
}
```

#### GET /patients/{patient_id}/emergency

Required role: FIRST_RESPONDER, DOCTOR, ADMIN.

Description: Retrieves patient emergency info (short view).

Response:

```json
{
  "patientId": "PAT-001",
  "fullName": "John Doe",
  "phone": "+243900000000",
  "bloodType": "O+",
  "allergies": ["Penicillin"],
  "emergencyContact": "Jane Doe"
}
```

#### PATCH /patients/{patient_id}

Required role: HEALTH_WORKER, DOCTOR, ADMIN.

Description: Updates patient information.

Request body:

```json
{
  "allergies": ["Penicillin", "Sulfonamides"],
  "chronicConditions": ["Asthma", "Diabetes"],
  "medications": ["Inhaler", "Metformin"]
}
```

Response:

```json
{
  "message": "Patient updated successfully",
  "patient": {
    "patientId": "PAT-001",
    "allergies": ["Penicillin", "Sulfonamides"],
    "chronicConditions": ["Asthma", "Diabetes"],
    "medications": ["Inhaler", "Metformin"]
  }
}
```

#### POST /patients/{patient_id}/verify/start

Required role: HEALTH_WORKER, ADMIN.

Description: Starts patient identity verification via eSignet.

Response:

```json
{
  "authorization_url": "https://...",
  "state": "f2d1...",
  "message": "Patient verification started"
}
```

### 8.5 Admin Endpoints

#### GET /admin/kyc/pending

Required role: ADMIN.

Description: Returns list of pending KYC submissions (users and patients).

Response:

```json
[
  {
    "uid": "u1",
    "fullName": "Dr. Jane",
    "role": "DOCTOR",
    "kycStatus": "SUBMITTED",
    "submittedAt": "2024-01-15T10:30:00Z",
    "type": "user"
  },
  {
    "uid": "PAT-001",
    "fullName": "John Doe",
    "role": "PATIENT",
    "kycStatus": "SUBMITTED",
    "submittedAt": "2024-01-15T10:35:00Z",
    "type": "patient"
  }
]
```

#### POST /admin/users/{uid}/kyc/verify

Required role: ADMIN.

Description: Verifies a user or patient KYC.

Request body:

```json
{
  "notes": "Documents verified and valid"
}
```

Response:

```json
{
  "message": "KYC verified successfully",
  "user": {
    "uid": "12345",
    "kycStatus": "VERIFIED",
    "kycReviewedBy": "admin-uid",
    "kycReviewedAt": "2024-01-15T10:40:00Z"
  }
}
```

#### POST /admin/users/{uid}/kyc/reject

Required role: ADMIN.

Description: Rejects a user or patient KYC.

Request body:

```json
{
  "reason": "Document is expired"
}
```

Response:

```json
{
  "message": "KYC rejected",
  "user": {
    "uid": "12345",
    "kycStatus": "REJECTED",
    "kycRejectionReason": "Document is expired",
    "kycReviewedBy": "admin-uid",
    "kycReviewedAt": "2024-01-15T10:40:00Z"
  }
}
```

#### POST /admin/users/{uid}/role

Required role: ADMIN.

Description: Assigns or updates a user role.

Request body:

```json
{
  "role": "DOCTOR"
}
```

Response:

```json
{
  "message": "Role assigned successfully",
  "uid": "12345",
  "role": "DOCTOR",
  "assignedBy": "admin-uid"
}
```

#### POST /admin/users

Required role: ADMIN.

Description: Creates a new staff user.

Request body:

```json
{
  "email": "doctor@example.com",
  "fullName": "Dr. Jane Doe",
  "role": "DOCTOR",
  "hospital": "Central Hospital",
  "contactPhone": "+243900000000"
}
```

Response (201):

```json
{
  "message": "User created successfully",
  "user": {
    "uid": "new-uid",
    "email": "doctor@example.com",
    "fullName": "Dr. Jane Doe",
    "role": "DOCTOR"
  }
}
```

## 9. Patient Data Format

### Format returned by the API

Patient object structure:

```json
{
  "id": "PAT-001",
  "fullName": "John Doe",
  "dateOfBirth": "1990-01-15",
  "gender": "M",
  "nationalId": "ID-001",
  "phone": "+243900000000",
  "bloodType": "O+",
  "allergies": ["Penicillin"],
  "chronicConditions": ["Asthma"],
  "medications": ["Inhaler"],
  "emergencyContact": "Jane Doe",
  "identityStatus": "VERIFIED|PENDING",
  "kycStatus": "SUBMITTED|VERIFIED|REJECTED",
  "esignetSubjectId": "optional",
  "createdAt": "2024-01-15T10:00:00Z",
  "updatedAt": "2024-01-15T10:30:00Z",
  "createdBy": "hw-uid",
  "updatedBy": "hw-uid"
}
```

## 10. Error Handling

Standard HTTP status codes:

- `200 OK`: Success.
- `201 Created`: Resource created successfully.
- `400 Bad Request`: Invalid request body or parameters.
- `401 Unauthorized`: Missing or invalid token.
- `403 Forbidden`: Insufficient permissions.
- `404 Not Found`: Resource not found.
- `409 Conflict`: Resource already exists (e.g., duplicate nationalId).
- `422 Unprocessable Entity`: Validation error.
- `500 Internal Server Error`: Server error.

Error response format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

## 11. What is real now in production as a reminder

- Real Firebase: all users, patients, and KYC data is persisted.
- Real backend: all endpoints work on Cloud Run.
- Real OIDC protocol: discovery, JWKS, token validation follow standards.

## 12. Cloud Run Deployment

### Environment variables to set in Cloud Run

```
ESIGNET_BASE_URL=https://actual-esignet-url
CLIENT_ID=official-client-id
CLIENT_SECRET=official-client-secret
PRIVATE_KEY_PEM_PATH=/path/to/key
REDIRECT_URI=https://afya-id-prod.run.app/auth/callback
FIREBASE_CREDENTIALS_JSON=/gcp/credentials.json
FIREBASE_PROJECT_ID=afya-id
APP_ENV=production
ALLOW_FIREBASE_LOCAL_FALLBACK=false
```

### Recommended deployment commands

```bash
gcloud builds submit --tag gcr.io/afyaid-backend1/afyaid-backend:latest
gcloud run deploy afya-id --image gcr.io/afyaid-backend1/afyaid-backend:latest \
  --region europe-west2 \
  --platform managed \
  --allow-unauthenticated
```

### Quick verification after deployment

```bash
curl https://afya-id-production-url/health
curl https://afya-id-production-url/auth/login
```

## 13. Points to validate when real eSignet is ready

- Replace `ESIGNET_BASE_URL` with official production URL.
- Replace `CLIENT_ID` and `CLIENT_SECRET`.
- Ensure `REDIRECT_URI` is registered exactly with eSignet.
- Test full OAuth flow end-to-end.
- Validate `id_token` signature with real JWKS.
- Verify patient identity verification flow.

## 14. Final summary

| Component | Status | Notes |
|-----------|--------|-------|
| Backend API | Real | FastAPI on Cloud Run, fully functional |
| Firebase | Real | Production project, all data persisted |
| OIDC Protocol | Real | Discovery, token validation, userinfo fully implemented |
| eSignet Integration | Mock | Awaiting production credentials |
| Patient Management | Real | All routes and logic working |
| KYC Flow | Real | Submission, admin review, approval working |
| Role-based Access | Real | All roles and permissions enforced |

The backend is **production-ready** for integration testing, waiting only for real eSignet credentials to enable full production auth flow.
