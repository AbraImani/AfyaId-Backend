# Local Mock eSignet (OIDC) Setup for AfyaID

This document allows you to test the identity flow locally without official eSignet credentials, while keeping Firestore on the real cloud project.

## 1) Architecture chosen

- AfyaID FastAPI backend: local on http://localhost:8000
- Mock IdP OIDC (Docker): local on http://localhost:9000
- Firestore: real cloud (project `afya-id`)

The mock IdP exposes:
- `/.well-known/openid-configuration`
- `/.well-known/jwks.json`
- `/authorize`
- `/token`
- `/userinfo`

It supports:
- `private_key_jwt` (priority)
- `client_secret_post` (fallback)

## 2) Files added

- `docker-compose.mock-oidc.yml`
- `mock_idp/app.py`
- `mock_idp/bootstrap_keys.py`
- `mock_idp/Dockerfile`
- `mock_idp/requirements.txt`
- `mock_idp/users.json`
- `scripts/generate_mock_oidc_keys.py`

## 3) Mock users

Test credentials:

- Admin: `admin.mock / Admin123!`
- Doctor: `doctor.mock / Doctor123!`
- Health Worker: `healthworker.mock / Health123!`
- First Responder: `responder.mock / Responder123!`
- Verified patient: `patient.verified / Patient123!`
- Pending patient: `patient.pending / Patient123!`

Claims included: `sub`, `email`, `name`, `phone_number`, `is_verified`, `nationalId`, `role`.

## 4) Backend environment variables

Minimum example (see `.env.example`):

```env
ESIGNET_BASE_URL=http://localhost:9000
CLIENT_ID=afya-local-client
CLIENT_SECRET=afya-local-secret
PRIVATE_KEY_PEM_PATH=./mock_idp/keys/client_private.pem
REDIRECT_URI=http://localhost:8000/auth/callback
JWT_AUDIENCE=

FIREBASE_PROJECT_ID=afya-id
FIREBASE_CREDENTIALS_JSON=./afya-id-firebase-adminsdk-fbsvc-b17807b016.json
APP_ENV=development
ALLOW_FIREBASE_LOCAL_FALLBACK=true
```

## 5) Generating local RSA keys

Recommended option (from project root):

```powershell
python scripts/generate_mock_oidc_keys.py
```

Files generated:
- `mock_idp/keys/provider_private.pem` (signature of mock IdP tokens)
- `mock_idp/keys/client_private.pem` (used by backend for `private_key_jwt`)

If the files don't exist, the mock container can also create them on startup.

## 6) Local startup

1. Start the mock IdP:

```powershell
docker compose -f docker-compose.mock-oidc.yml up --build -d
```

2. Start the backend:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 7) Local URLs

- Mock issuer: `http://localhost:9000`
- OIDC discovery: `http://localhost:9000/.well-known/openid-configuration`
- JWKS: `http://localhost:9000/.well-known/jwks.json`
- Authorize: `http://localhost:9000/authorize`
- Token: `http://localhost:9000/token`
- Userinfo: `http://localhost:9000/userinfo`
- Backend: `http://localhost:8000`

## 8) Quick end-to-end test (browser)

1. Open:

```text
http://localhost:8000/auth/login?redirect=true
```

2. Browser redirects to `http://localhost:9000/authorize`.
3. Log in with a mock user.
4. Mock redirects to `http://localhost:8000/auth/callback?code=...&state=...`.
5. Backend exchanges the code, validates tokens, retrieves userinfo and creates/updates user in Firestore.

## 9) API test (curl)

1. Get the authorization URL:

```bash
curl "http://localhost:8000/auth/login"
```

2. Then use the browser for the login part (mock form).
3. After callback, get `access_token` from the response and test:

```bash
curl -H "Authorization: Bearer <ACCESS_TOKEN>" "http://localhost:8000/auth/me"
```

## 10) Patient verification (mock)

1. Authenticate a HEALTH_WORKER mock user.
2. Create a patient via `POST /patients/register`.
3. Start verification: `POST /patients/{patient_id}/verify/start`.
4. Open `authorization_url`, mock login.
5. Callback updates patient's `esignetSubjectId`, `identityStatus`, `kycStatus`.

## 11) Future migration to real eSignet

When official credentials become available:
- Replace `ESIGNET_BASE_URL` with real eSignet issuer
- Replace `CLIENT_ID`, `CLIENT_SECRET` (or production key)
- Set `PRIVATE_KEY_PEM_PATH` to the key registered with eSignet
- Verify that `REDIRECT_URI` exactly matches the one registered

The rest of the backend flow (`/auth/login`, `/auth/callback`, `/auth/me`) is already based on OIDC discovery, so the transition is mainly limited to configuration.
