# Flutter Guide - Using AfyaID Backend in local/mock mode

Validation date: 2026-04-04

## 1) Current setup reality: what is real vs mock

- Firebase/Firestore: real (cloud project afya-id).
- AfyaID FastAPI backend: real (production code), executable locally and also deployed on Cloud Run.
- Official eSignet: not connected with official credentials in this setup.
- Mock OIDC identity provider: local (localhost:9000) for development tests.

In short: data persistence is real, but the identity provider used for local tests is simulated.

## 2) URLs for Flutter to use

### Local/mock mode (recommended for immediate integration)

- Backend API (dev machine): http://localhost:8000
- Mock OIDC/eSignet local: http://localhost:9000

### Public/deployed mode

- Public backend API: https://afya-id-419586439350.europe-west2.run.app

Important:
- The public backend responds well.
- The public auth flow should not be considered "team-ready" unless a valid real OIDC client is configured on the deployment side (see limitations section).

## 3) Prerequisites and local backend launch

Prerequisites:
- Python 3.10+
- venv created
- Dependencies installed: pip install -r requirements.txt
- Local .env file configured (see .env.example)

Minimum backend local variables:
- ESIGNET_BASE_URL=http://localhost:9000
- CLIENT_ID=afya-local-client
- CLIENT_SECRET=afya-local-secret
- PRIVATE_KEY_PEM_PATH=./mock_idp/keys/client_private.pem
- REDIRECT_URI=http://localhost:8000/auth/callback
- FIREBASE_PROJECT_ID=afya-id
- FIREBASE_CREDENTIALS_JSON=./afya-id-firebase-adminsdk-fbsvc-b17807b016.json
- APP_ENV=development

Command:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Quick verification:
- GET http://localhost:8000/
- GET http://localhost:8000/health

## 4) Launching the local mock identity provider

### Option A - Docker (recommended)

1. Generate keys:

```bash
python scripts/generate_mock_oidc_keys.py
```

2. Start the mock:

```bash
docker compose -f docker-compose.mock-oidc.yml up --build -d
```

3. Verify:
- GET http://localhost:9000/.well-known/openid-configuration
- GET http://localhost:9000/.well-known/jwks.json

### Option B - Direct local (if Docker unavailable)

1. Generate keys:

```bash
python scripts/generate_mock_oidc_keys.py
```

2. Install mock dependencies:

```bash
pip install -r mock_idp/requirements.txt
```

3. Launch the mock IdP:

```bash
uvicorn mock_idp.app:app --host 0.0.0.0 --port 9000 --reload
```

## 5) How Flutter should connect to localhost

### Android Emulator

- Use http://10.0.2.2:8000 to reach the local backend on the host machine.
- For the mock provider, use http://10.0.2.2:9000 if the app opens URLs via the emulator.

### Physical Android device

- Use the LAN IP of the dev machine, e.g.: http://192.168.1.20:8000
- Same for mock OIDC: http://192.168.1.20:9000
- The mobile and dev machine must be on the same network.
- Allow local firewall for ports 8000 and 9000.

### Flutter Web

- Use directly http://localhost:8000
- The browser will open the mock login page on http://localhost:9000

## 6) Authentication flow in local mode

1. Flutter calls GET /auth/login.
2. Backend returns authorization_url + state.
3. Flutter opens authorization_url (WebView or external browser).
4. User logs in on the mock IdP.
5. Mock redirects to backend /auth/callback with code + state.
6. Backend exchanges the code, validates tokens, retrieves userinfo, creates/updates user in Firestore.
7. Backend returns access_token and user.
8. Flutter stores access_token.
9. Flutter calls GET /auth/me with Authorization: Bearer <token> to retrieve the profile.

Note for Flutter implementation:
- If Flutter controls the external browser, listen for the final redirect to /auth/callback and retrieve the JSON response.
- Practical alternative: open /auth/login?redirect=true in browser then handle the callback result according to your deep-link/webview strategy.

## 7) Patient flow to test on Flutter side

1. Authenticate staff (doctor/health worker/admin mock).
2. Patient creation: POST /patients/register.
3. Patient update: PUT /patients/{patient_id}.
4. View patient summary: GET /patients/{patient_id}/summary.
5. Emergency view: GET /patients/{patient_id}/emergency.
6. Mock identity verification:
   - POST /patients/{patient_id}/verify/start
   - Open authorization_url
   - Mock login
   - Backend callback updates identityStatus, kycStatus, esignetSubjectId.

## 8) Concrete request/response examples

### Login bootstrap

Request:
- GET /auth/login

Expected response (excerpt):

```json
{
  "authorization_url": "http://localhost:9000/authorize?...",
  "state": "d29aa392cd874a53ab0eb2b2a8516ad3"
}
```

### Successful callback

Request:
- GET /auth/callback?code=...&state=...

Expected response (excerpt):

```json
{
  "message": "Authentication successful",
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "user": {
    "uid": "mock-doctor-001",
    "provider": "esignet"
  }
}
```

### Current profile

Request:
- GET /auth/me
- Header: Authorization: Bearer <access_token>

Expected response (excerpt):

```json
{
  "uid": "mock-doctor-001",
  "role": "DOCTOR",
  "provider": "esignet"
}
```

### Start patient verification

Request:
- POST /patients/{patient_id}/verify/start

Expected response (excerpt):

```json
{
  "authorization_url": "http://localhost:9000/authorize?...",
  "state": "..."
}
```

### Patient verification callback

Request:
- GET /auth/callback?code=...&state=patient_verify:{patient_id}:...

Expected response (excerpt):

```json
{
  "message": "Patient identity verified successfully",
  "patient": {
    "identityStatus": "VERIFIED",
    "kycStatus": "VERIFIED_BY_PROVIDER",
    "esignetSubjectId": "mock-patient-verified-001"
  }
}
```

## 9) Known limitations (honest)

- Without official eSignet credentials, auth remains in mock mode for integration.
- A public backend alone is not sufficient to guarantee a complete auth flow if the deployed OIDC client is not valid.
- If the mock IdP is not deployed publicly, it is only useful for local apps or those with tunnels.
- Biometric flows (face/fingerprint) are not part of this version.

## 10) Recommended team mode (short term)

Recommended mode now: Flutter local/mock integration.

Why:
- Faster and more stable immediately.
- Complete auth flow already valid locally end-to-end.
- Firestore remains real, so business data and behaviors are representative.
- Avoids blocking the team on the availability of official eSignet credentials.

Next option when you want shared remote testing:
- Also deploy the mock IdP to a public URL, then configure the public backend with this issuer + a valid OIDC client.
