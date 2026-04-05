# AfyaId Backend

AfyaId is a FastAPI backend for healthcare identity, patient management, RBAC, KYC, and mock eSignet authentication. The repository also includes a mock OIDC provider for local development and public integration testing.

## What is included

- `main.py`: FastAPI entry point.
- `routes/`: auth, admin, patient, and KYC endpoints.
- `services/`: Firestore, OIDC, and domain services.
- `mock_idp/`: mock OIDC provider used for login tests.
- `docker-compose.yml`: one-command local orchestration for backend + mock OIDC.
- `.env`: local environment variables.

## Requirements

Use only free and open-source tools:

- Python 3.10 or 3.11
- Docker Engine
- Docker Compose V2
- `pip`

## Configuration

The repository already contains a working [.env](.env) file for local development.

If you need to regenerate the mock OIDC keys:

```bash
python scripts/generate_mock_oidc_keys.py
```

## Run with Docker

This is the recommended path because it starts both services with no extra setup.

### Windows PowerShell

```powershell
docker compose up --build
```

### Linux / macOS shell

```bash
docker compose up --build
```

After startup:

- Backend API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Mock OIDC: http://localhost:9000
- Mock authorize page: http://localhost:9000/authorize

## Run without Docker

### 1. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 2. Install mock OIDC dependencies if you want to run it separately

```bash
pip install -r mock_idp/requirements.txt
```

### 3. Generate keys if needed

```bash
python scripts/generate_mock_oidc_keys.py
```

### 4. Start the mock OIDC provider

```bash
uvicorn mock_idp.app:app --host 0.0.0.0 --port 9000 --reload
```

### 5. Start the backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment variables

The required variables are already present in [.env](.env).

Key values:

- `ESIGNET_BASE_URL=http://localhost:9000`
- `CLIENT_ID=afya-local-client`
- `CLIENT_SECRET=afya-local-secret`
- `REDIRECT_URI=http://localhost:8000/auth/callback`
- `PRIVATE_KEY_PEM_PATH=./mock_idp/keys/client_private.pem`
- `FIREBASE_CREDENTIALS_JSON=./afya-id-firebase-adminsdk-fbsvc-b17807b016.json`
- `FIREBASE_PROJECT_ID=afya-id`
- `APP_ENV=development`
- `ALLOW_FIREBASE_LOCAL_FALLBACK=true`
- `APP_BASE_URL=http://localhost:8000`
- `FRONTEND_URL=http://localhost:3000`
- `APP_CALLBACK_URL=https://afya-id.web.app//auth/callback`
- `ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5000,http://127.0.0.1:5000,https://afya-id.web.app`
- `ALLOW_DEV_DYNAMIC_LOCALHOST_ORIGINS=true`
- `APP_SECRET_KEY=change-this-to-a-random-secret-key`

## Quick validation

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:9000/.well-known/openid-configuration
```

## Auth flow

1. Call `GET /auth/login`.
2. Open the returned `authorization_url`.
3. Sign in on the mock provider.
4. The provider redirects to `GET /auth/callback`.
5. The backend returns `access_token`, `id_token`, and the user profile.
6. Use `Authorization: Bearer <access_token>` on protected routes.

For a direct app callback after authentication:

1. Call `GET /auth/login/app` (optional query: `app_callback_url=afyaid://auth/callback`).
2. Open the returned `authorization_url` in WebView/browser.
3. After sign-in, backend `/auth/callback` redirects (HTTP 302) to the app callback URL.
4. Tokens and auth context are sent in the URL fragment (`#access_token=...`) so they are not sent to web servers.

## Mock accounts

- `admin.mock / Admin123!`
- `doctor.mock / Doctor123!`
- `healthworker.mock / Health123!`
- `responder.mock / Responder123!`
- `patient.verified / Patient123!`
- `patient.pending / Patient123!`

## Useful mock pages

- Login mock: http://localhost:9000/authorize?response_type=code&client_id=afya-local-client&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback&scope=openid&state=test
- Admin user create page: http://localhost:9000/admin/users/new

## Public deployment

- Backend: https://afya-id-419586439350.europe-west2.run.app
- Mock OIDC: https://afya-mock-oidc-419586439350.europe-west2.run.app

## Notes

- `GET /auth/me` is protected and requires a Bearer token.
- The mock OIDC provider is for integration testing only.
