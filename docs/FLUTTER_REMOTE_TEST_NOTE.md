# Flutter Note - Complete Remote Integration (public backend with public mock OIDC on Cloud Run)

Date: 2026-04-04

## 1) What is in place now

- Public backend API: https://afya-id-419586439350.europe-west2.run.app
- Public mock OIDC/eSignet: https://afya-mock-oidc-tpetcpbucq-nw.a.run.app
- Public backend callback: https://afya-id-419586439350.europe-west2.run.app/auth/callback
- Firestore: production (project afya-id)

Practical conclusion:
- The Flutter team can test the entire flow remotely without localhost.

## 2) Why the login interface appears as HTML

The screen you see (basic HTML form) is normal.

- This provider is an integration test mock, not the official eSignet UI.
- The objective is to validate the OIDC protocol (authorize, token, userinfo, jwks), not the final UI design.
- In production, this UI will be replaced by the real eSignet portal once credentials are obtained.

## 3) Recommended auth flow for Flutter (important)

The backend is configured for this contract:

1. Flutter calls GET /auth/login
2. Backend returns:
   - authorization_url
   - state
3. Flutter opens authorization_url in a WebView (or in-app browser)
4. User logs in on the mock
5. Mock attempts to redirect to /auth/callback?code=...&state=...
6. Flutter intercepts this callback URL
7. Flutter calls this URL callback via its HTTP client
8. Backend responds with JSON containing access_token, id_token, user
9. Flutter stores access_token and uses it as Bearer on protected endpoints

Why this method is the best:
- It avoids depending on reading JSON body in the WebView.
- It keeps API logic clear and testable.

## 4) Token management without ambiguity

Expected response on callback:

```json
{
  "access_token": "eyJ...",
  "id_token": "eyJ...",
  "token_type": "Bearer",
  "user": { ... },
  "kyc_status": "...",
  "profile_complete": true,
  "message": "..."
}
```

Usage:
- Header Authorization: Bearer <access_token>
- Session verification endpoint: GET /auth/me

Recommended storage on Flutter side:
- Keep access_token in secure storage (not plaintext).
- On 401, restart the login flow.

## 5) Strategy for Flutter WebView implementation

Recommended:
- Open authorization_url in WebView.
- In shouldOverrideUrlLoading (or equivalent), detect URLs that start with:
  - https://afya-id-419586439350.europe-west2.run.app/auth/callback
- Cancel the WebView navigation to this URL.
- Close the WebView.
- Make an HTTP GET from Flutter to this intercepted URL.
- Extract access_token from the backend JSON response.

Important warning:
- You must cancel the navigation before the WebView actually calls /auth/callback,
  otherwise the state can be consumed and a second call may fail.

## 6) Mock test accounts

- admin.mock / Admin123!
- doctor.mock / Doctor123!
- healthworker.mock / Health123!
- responder.mock / Responder123!
- patient.verified / Patient123!
- patient.pending / Patient123!

## 7) Useful endpoints after login

- GET /auth/me
- POST /auth/complete-profile
- POST /patients/register
- POST /patients/{patient_id}/verify/start
- GET /patients/{patient_id}
- GET /patients/{patient_id}/summary
- GET /patients/{patient_id}/emergency
- POST /kyc/submit

## 8) Patient verification from Flutter

Flow:

1. Authenticate staff (doctor or health worker)
2. Create patient via POST /patients/register
3. Start verification via POST /patients/{patient_id}/verify/start
4. Open the received authorization_url
5. Intercept callback as for login
6. Call callback via HTTP
7. Verify in the response patient:
   - identityStatus
   - kycStatus
   - esignetSubjectId

## 9) Flutter integration checklist

- GET /auth/login returns a public URL
- Mock login screen appears
- Callback is intercepted
- Callback HTTP returns access_token
- GET /auth/me works with Bearer
- At least one protected patient route works

## 10) Trust notes

- Firebase/Firestore remains real on the afya-id project.
- The identity provider is a remote mock (not official eSignet).
- The test flow is 100% remote: no localhost is required.

## 11) Flutter pseudocode (callback interception)

A simple algorithmic example to adapt to the WebView package on Flutter side:

```
1. loginResp = GET /auth/login
2. openWebView(loginResp.authorization_url)
3. onNavigation(url):
   - if url startsWith("https://afya-id-419586439350.europe-west2.run.app/auth/callback"):
     - cancel WebView navigation
     - close WebView
     - callbackResp = GET url
     - token = callbackResp.access_token
     - secureStore.write("access_token", token)
     - me = GET /auth/me with Authorization: Bearer token
     - continue app session with me.user
```

I don't know how it will go on your side but if you use an external browser instead of WebView, you will need to:
- configure a deep link for app return,
- or keep an intermediate frontend page that retrieves the callback JSON and sends it to the app.
