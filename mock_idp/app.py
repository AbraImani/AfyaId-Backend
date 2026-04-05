import base64
import json
import os
import time
import uuid
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import JWTError, jwt
import httpx

ISSUER = os.getenv("OIDC_ISSUER", "http://localhost:9000").rstrip("/")
USERS_FILE = os.getenv("USERS_FILE", "/app/users.json")
KEYS_DIR = Path(os.getenv("KEYS_DIR", "/app/keys"))
CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "afya-local-client")
CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "afya-local-secret")
REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "http://localhost:8000/auth/callback")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

PROVIDER_PRIVATE_KEY_PATH = KEYS_DIR / "provider_private.pem"
CLIENT_PRIVATE_KEY_PATH = KEYS_DIR / "client_private.pem"

AUTH_CODES: Dict[str, Dict[str, Any]] = {}

app = FastAPI(title="AfyaID Mock OIDC Provider", version="1.0.0")


def _base64url_int(i: int) -> str:
    b = i.to_bytes((i.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _load_private_key_pem(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Missing key file: {path}")
    return path.read_text(encoding="utf-8")


def _load_public_pem_from_private(path: Path) -> str:
    private_key = serialization.load_pem_private_key(
        path.read_bytes(),
        password=None,
        backend=default_backend(),
    )
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def _provider_public_jwk() -> Dict[str, Any]:
    private_key = serialization.load_pem_private_key(
        PROVIDER_PRIVATE_KEY_PATH.read_bytes(),
        password=None,
        backend=default_backend(),
    )
    public_numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "mock-provider-kid-1",
        "n": _base64url_int(public_numbers.n),
        "e": _base64url_int(public_numbers.e),
    }


def _load_users() -> Dict[str, Dict[str, Any]]:
    rows = json.loads(Path(USERS_FILE).read_text(encoding="utf-8"))
    return {u["username"]: u for u in rows}


def _render_login_page(
        *,
        client_id: str,
        response_type: str,
        redirect_uri: str,
        scope: str,
        state: str,
        nonce: Optional[str],
        usernames: Dict[str, Dict[str, Any]],
) -> str:
        username_options = "".join(
                f'<option value="{escape(username)}">{escape(data.get("name") or username)} · {escape(data.get("role", "USER"))}</option>'
                for username, data in usernames.items()
        )
        credential_cards = "".join(
                f'''
                    <div class="credential-card">
                        <span class="credential-role">{escape(data.get("role", "USER"))}</span>
                        <strong>{escape(username)}</strong>
                        <span>{escape(data.get("password", ""))}</span>
                    </div>
                '''
                for username, data in usernames.items()
        )

        return f"""
        <html lang="en">
            <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>AfyaID Mock eSignet Login</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
                <style>
                    :root {{
                        --primary: #003F87;
                        --primary-deep: #002B5D;
                        --primary-soft: #EAF1FF;
                        --ink: #122033;
                        --muted: #61708A;
                        --line: #D8E2F1;
                        --surface: rgba(255, 255, 255, 0.88);
                        --shadow: 0 24px 60px rgba(18, 32, 51, 0.16);
                    }}

                    * {{ box-sizing: border-box; }}
                    body {{
                        margin: 0;
                        font-family: 'Outfit', sans-serif;
                        color: var(--ink);
                        min-height: 100vh;
                        background:
                            radial-gradient(circle at top left, rgba(0, 63, 135, 0.18), transparent 30%),
                            radial-gradient(circle at bottom right, rgba(0, 63, 135, 0.10), transparent 28%),
                            linear-gradient(180deg, #F6F9FF 0%, #EFF5FF 100%);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        padding: 24px;
                    }}

                    .panel {{
                        width: min(520px, 100%);
                        border: 1px solid rgba(255, 255, 255, 0.8);
                        border-radius: 28px;
                        box-shadow: var(--shadow);
                        overflow: hidden;
                    }}

                    .panel {{
                        background: var(--surface);
                        backdrop-filter: blur(18px);
                        padding: 28px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                    }}

                    .panel-header h2 {{
                        margin: 0;
                        font-size: 1.9rem;
                        letter-spacing: -0.03em;
                    }}

                    .panel-header p {{
                        margin: 8px 0 0;
                        color: var(--muted);
                        line-height: 1.6;
                    }}

                    .client-pill {{
                        margin-top: 16px;
                        display: inline-flex;
                        align-items: center;
                        gap: 10px;
                        padding: 10px 14px;
                        background: var(--primary-soft);
                        color: var(--primary-deep);
                        border-radius: 14px;
                        font-size: 0.95rem;
                        font-weight: 600;
                        width: fit-content;
                    }}

                    form {{ margin-top: 22px; }}

                    .field {{ margin-bottom: 16px; }}

                    label {{
                        display: block;
                        margin-bottom: 8px;
                        font-size: 0.92rem;
                        font-weight: 700;
                        color: var(--ink);
                    }}

                    select, input[type="password"] {{
                        width: 100%;
                        padding: 15px 16px;
                        border-radius: 16px;
                        border: 1.5px solid var(--line);
                        background: white;
                        font: inherit;
                        color: var(--ink);
                        outline: none;
                        transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
                    }}

                    select:focus, input[type="password"]:focus {{
                        border-color: var(--primary);
                        box-shadow: 0 0 0 4px rgba(0, 63, 135, 0.12);
                    }}

                    .hint {{
                        margin-top: 8px;
                        color: var(--muted);
                        font-size: 0.9rem;
                    }}

                    .button-row {{ margin-top: 24px; }}

                    button {{
                        width: 100%;
                        border: 0;
                        border-radius: 20px;
                        padding: 18px 22px;
                        background: linear-gradient(135deg, var(--primary), #0B5AB6);
                        color: white;
                        font: inherit;
                        font-weight: 700;
                        letter-spacing: 0.01em;
                        box-shadow: 0 16px 30px rgba(0, 63, 135, 0.28);
                        cursor: pointer;
                    }}

                    button:hover {{ filter: brightness(1.03); }}

                    @media (max-width: 980px) {{
                        .panel {{ width: min(560px, 100%); }}
                    }}

                    @media (max-width: 640px) {{
                        body {{ padding: 14px; }}
                        .panel {{ border-radius: 22px; padding: 22px; }}
                    }}
                </style>
            </head>
            <body>
                <main class="panel">
                    <div class="panel-header">
                        <h2>Welcome back</h2>
                        <p>Authenticate with one of the mock identities below to continue to the backend callback.</p>
                        <div class="client-pill">Client: <span>{escape(client_id)}</span></div>
                    </div>

                    <form method="post" action="/authorize">
                        <div class="field">
                            <label>Username</label>
                            <select name="username" required>
                                {username_options}
                            </select>
                        </div>

                        <div class="field">
                            <label>Password</label>
                            <input type="password" name="password" placeholder="Enter the mock password" required />
                            <div class="hint">Select an account, then use its password from the credential list below.</div>
                        </div>

                        <input type="hidden" name="response_type" value="{escape(response_type)}"/>
                        <input type="hidden" name="client_id" value="{escape(client_id)}"/>
                        <input type="hidden" name="redirect_uri" value="{escape(redirect_uri)}"/>
                        <input type="hidden" name="scope" value="{escape(scope)}"/>
                        <input type="hidden" name="state" value="{escape(state)}"/>
                        <input type="hidden" name="nonce" value="{escape(nonce or '')}"/>

                        <div class="button-row">
                            <button type="submit">Login and Authorize</button>
                        </div>
                    </form>
                </main>
            </body>
        </html>
        """


def _render_admin_user_mock_page() -> str:
        return _render_admin_create_user_page()


async def _fetch_admin_access_token() -> str:
        users = _load_users()
        admin_user = users.get("admin.mock")
        if not admin_user:
                raise HTTPException(status_code=500, detail="Mock admin user not found.")

        async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:
                login_response = await client.get(f"{APP_BASE_URL}/auth/login")
                if login_response.status_code != 200:
                        raise HTTPException(status_code=502, detail="Failed to start admin auth flow.")

                auth_url = login_response.json().get("authorization_url")
                if not auth_url:
                        raise HTTPException(status_code=502, detail="Missing authorization_url from backend.")

                auth_page = await client.get(auth_url)
                if auth_page.status_code != 200:
                        raise HTTPException(status_code=502, detail="Failed to load mock authorize page.")

                form_data = {
                        "username": "admin.mock",
                        "password": admin_user["password"],
                        "response_type": "code",
                        "client_id": CLIENT_ID,
                        "redirect_uri": REDIRECT_URI,
                        "scope": "openid profile email phone",
                        "state": login_response.json()["state"],
                        "nonce": "",
                }

                authorize_response = await client.post(f"{ISSUER}/authorize", data=form_data)
                if authorize_response.status_code not in (302, 303):
                        raise HTTPException(status_code=502, detail="Failed to authorize mock admin.")

                callback_url = authorize_response.headers.get("location")
                if not callback_url:
                        raise HTTPException(status_code=502, detail="Missing callback redirect from mock provider.")

                callback_response = await client.get(callback_url)
                if callback_response.status_code != 200:
                        raise HTTPException(status_code=502, detail="Backend callback failed for admin session.")

                token_payload = callback_response.json()
                access_token = token_payload.get("access_token")
                if not access_token:
                        raise HTTPException(status_code=502, detail="Missing access_token from backend callback.")

                return access_token


def _render_admin_create_user_page(message: str = "", error: str = "") -> str:
        message_block = f'<div class="flash success">{escape(message)}</div>' if message else ""
        error_block = f'<div class="flash error">{escape(error)}</div>' if error else ""
        return f"""
        <html lang="en">
            <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>AfyaID Admin - Create User</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
                <style>
                    :root {{
                        --primary: #003F87;
                        --primary-soft: #EAF1FF;
                        --ink: #122033;
                        --muted: #61708A;
                        --line: #D8E2F1;
                        --surface: rgba(255, 255, 255, 0.92);
                        --shadow: 0 24px 60px rgba(18, 32, 51, 0.14);
                        --success: #0B7A4B;
                        --error: #B42318;
                    }}

                    * {{ box-sizing: border-box; }}
                    body {{
                        margin: 0;
                        font-family: 'Outfit', sans-serif;
                        color: var(--ink);
                        min-height: 100vh;
                        background:
                            radial-gradient(circle at top left, rgba(0, 63, 135, 0.15), transparent 28%),
                            radial-gradient(circle at bottom right, rgba(0, 63, 135, 0.08), transparent 26%),
                            linear-gradient(180deg, #F6F9FF 0%, #EEF4FF 100%);
                        padding: 24px;
                    }}

                    .page {{
                        width: min(1080px, 100%);
                        margin: 0 auto;
                        background: var(--surface);
                        backdrop-filter: blur(18px);
                        border: 1px solid rgba(255, 255, 255, 0.8);
                        border-radius: 30px;
                        box-shadow: var(--shadow);
                        overflow: hidden;
                    }}

                    .topbar {{
                        background: linear-gradient(135deg, #003F87, #0B5AB6);
                        color: white;
                        padding: 28px 32px;
                    }}

                    .topbar h1 {{
                        margin: 0;
                        font-size: clamp(1.8rem, 3vw, 2.7rem);
                        letter-spacing: -0.03em;
                    }}

                    .topbar p {{
                        margin: 10px 0 0;
                        color: rgba(255, 255, 255, 0.84);
                        max-width: 62ch;
                        line-height: 1.6;
                    }}

                    .content {{
                        display: grid;
                        grid-template-columns: 1fr 0.92fr;
                        gap: 24px;
                        padding: 28px 32px 32px;
                    }}

                    .card {{
                        border: 1px solid var(--line);
                        border-radius: 24px;
                        padding: 22px;
                        background: white;
                    }}

                    .card h2 {{
                        margin: 0 0 8px;
                        font-size: 1.5rem;
                    }}

                    .card p {{
                        margin: 0 0 18px;
                        color: var(--muted);
                        line-height: 1.6;
                    }}

                    .flash {{
                        padding: 14px 16px;
                        border-radius: 16px;
                        margin-bottom: 16px;
                        font-weight: 600;
                    }}

                    .flash.success {{ background: rgba(11, 122, 75, 0.10); color: var(--success); border: 1px solid rgba(11, 122, 75, 0.18); }}
                    .flash.error {{ background: rgba(180, 35, 24, 0.10); color: var(--error); border: 1px solid rgba(180, 35, 24, 0.18); }}

                    .form-grid {{
                        display: grid;
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                        gap: 14px;
                    }}

                    .field {{ display: flex; flex-direction: column; gap: 8px; }}
                    .field.full {{ grid-column: 1 / -1; }}

                    label {{
                        font-size: 0.9rem;
                        font-weight: 700;
                    }}

                    input, select {{
                        width: 100%;
                        padding: 14px 15px;
                        border-radius: 16px;
                        border: 1.5px solid var(--line);
                        font: inherit;
                    }}

                    input:focus, select:focus {{
                        outline: none;
                        border-color: var(--primary);
                        box-shadow: 0 0 0 4px rgba(0, 63, 135, 0.12);
                    }}

                    .side-panel {{
                        display: flex;
                        flex-direction: column;
                        gap: 16px;
                    }}

                    .note {{
                        border-radius: 20px;
                        border: 1px dashed #C4D3EA;
                        background: #F8FBFF;
                        padding: 18px;
                        color: var(--muted);
                        line-height: 1.6;
                    }}

                    .cta {{
                        width: 100%;
                        margin-top: auto;
                        display: inline-flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 60px;
                        border-radius: 18px;
                        background: linear-gradient(135deg, var(--primary), #0B5AB6);
                        color: white;
                        font-weight: 700;
                        font-size: 1.05rem;
                        padding: 18px 24px;
                        box-shadow: 0 16px 30px rgba(0, 63, 135, 0.24);
                        border: 0;
                        cursor: pointer;
                    }}

                    @media (max-width: 920px) {{
                        .content {{ grid-template-columns: 1fr; }}
                    }}

                    @media (max-width: 640px) {{
                        body {{ padding: 14px; }}
                        .page, .topbar {{ border-radius: 22px; }}
                        .topbar, .content {{ padding-left: 20px; padding-right: 20px; }}
                        .form-grid {{ grid-template-columns: 1fr; }}
                    }}
                </style>
            </head>
            <body>
                <main class="page">
                    <section class="topbar">
                        <h1>New Worker Account</h1>
                        <p>Same functionality as the backend admin create-user flow, with a cleaner Afya visual style.</p>
                    </section>

                    <section class="content">
                        <div class="card">
                            <h2>Create user</h2>
                            <p>Fill the form, then the mock page will call the public backend admin endpoint.</p>
                            {message_block}
                            {error_block}

                            <form method="post" action="/admin/users/new">
                                <div class="form-grid">
                                    <div class="field full">
                                        <label>UID</label>
                                        <input type="text" name="uid" placeholder="Optional custom UID" />
                                    </div>
                                    <div class="field full">
                                        <label>Full Name *</label>
                                        <input type="text" name="fullName" placeholder="Jane Doe" required />
                                    </div>
                                    <div class="field">
                                        <label>Email *</label>
                                        <input type="email" name="email" placeholder="jane.doe@afya.local" required />
                                    </div>
                                    <div class="field">
                                        <label>Phone</label>
                                        <input type="tel" name="contactPhone" placeholder="+243 000 000 000" />
                                    </div>
                                    <div class="field full">
                                        <label>Hospital</label>
                                        <input type="text" name="hospital" placeholder="Central Hospital" />
                                    </div>
                                    <div class="field">
                                        <label>Role</label>
                                        <select name="role" required>
                                            <option value="DOCTOR">Doctor</option>
                                            <option value="HEALTH_WORKER">Health Worker</option>
                                            <option value="FIRST_RESPONDER">First Responder</option>
                                            <option value="ADMIN">Admin</option>
                                        </select>
                                    </div>
                                    <div class="field">
                                        <label>National ID</label>
                                        <input type="text" name="nationalId" placeholder="NI-0000" />
                                    </div>
                                    <div class="field full">
                                        <label>Professional title</label>
                                        <input type="text" name="title" placeholder="Dr, Nurse, etc." />
                                    </div>
                                    <div class="field full">
                                        <label>Professional matricule</label>
                                        <input type="text" name="matriculeNumber" placeholder="MAT-001" />
                                    </div>
                                    <div class="field full">
                                        <label>Specialty</label>
                                        <input type="text" name="specialty" placeholder="General medicine" />
                                    </div>
                                    <div class="field full">
                                        <label>Unit name</label>
                                        <input type="text" name="unitName" placeholder="Emergency" />
                                    </div>
                                    <div class="field full">
                                        <label>Photo URL</label>
                                        <input type="url" name="photoURL" placeholder="https://..." />
                                    </div>
                                </div>

                                <div style="margin-top: 24px;">
                                    <button class="cta" type="submit">Create</button>
                                </div>
                            </form>
                        </div>
                    </section>
                </main>
            </body>
        </html>
        """


def _token_endpoint() -> str:
    return f"{ISSUER}/token"


def _authorize_endpoint() -> str:
    return f"{ISSUER}/authorize"


def _userinfo_endpoint() -> str:
    return f"{ISSUER}/userinfo"


def _jwks_uri() -> str:
    return f"{ISSUER}/.well-known/jwks.json"


def _user_claims(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sub": user["sub"],
        "email": user.get("email"),
        "name": user.get("name"),
        "phone_number": user.get("phone_number"),
        "is_verified": user.get("is_verified", False),
        "individual_id": user.get("nationalId"),
        "nationalId": user.get("nationalId"),
        "role": user.get("role"),
    }


def _authenticate_client(
    client_id: str,
    client_secret: Optional[str],
    client_assertion_type: Optional[str],
    client_assertion: Optional[str],
) -> None:
    if client_id != CLIENT_ID:
        raise HTTPException(status_code=401, detail="invalid_client")

    if client_assertion:
        if client_assertion_type != "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
            raise HTTPException(status_code=401, detail="invalid_client_assertion_type")

        try:
            claims = jwt.decode(
                client_assertion,
                _load_public_pem_from_private(CLIENT_PRIVATE_KEY_PATH),
                algorithms=["RS256"],
                audience=_token_endpoint(),
                issuer=CLIENT_ID,
                options={"verify_sub": False},
            )
        except JWTError as exc:
            raise HTTPException(status_code=401, detail=f"invalid_client_assertion: {exc}")

        if claims.get("sub") != CLIENT_ID:
            raise HTTPException(status_code=401, detail="invalid_client_sub")
        return

    if client_secret and client_secret == CLIENT_SECRET:
        return

    raise HTTPException(status_code=401, detail="invalid_client")


def _mint_tokens(user: Dict[str, Any], nonce: Optional[str], scope: str) -> Dict[str, Any]:
    now = int(time.time())
    provider_private_key = _load_private_key_pem(PROVIDER_PRIVATE_KEY_PATH)

    id_payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": user["sub"],
        "iat": now,
        "exp": now + 900,
        "nonce": nonce,
        **_user_claims(user),
    }
    access_payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": user["sub"],
        "iat": now,
        "exp": now + 900,
        "scope": scope,
        "token_use": "access",
    }

    headers = {"kid": "mock-provider-kid-1", "typ": "JWT"}
    id_token = jwt.encode(id_payload, provider_private_key, algorithm="RS256", headers=headers)
    access_token = jwt.encode(access_payload, provider_private_key, algorithm="RS256", headers=headers)

    return {
        "token_type": "Bearer",
        "expires_in": 900,
        "id_token": id_token,
        "access_token": access_token,
    }


@app.get("/.well-known/openid-configuration")
async def openid_configuration() -> Dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": _authorize_endpoint(),
        "token_endpoint": _token_endpoint(),
        "userinfo_endpoint": _userinfo_endpoint(),
        "jwks_uri": _jwks_uri(),
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email", "phone"],
        "token_endpoint_auth_methods_supported": ["private_key_jwt", "client_secret_post"],
        "claims_supported": [
            "sub",
            "email",
            "name",
            "phone_number",
            "is_verified",
            "individual_id",
            "nationalId",
            "role",
        ],
    }


@app.get("/.well-known/jwks.json")
async def jwks() -> Dict[str, Any]:
    return {"keys": [_provider_public_jwk()]}


@app.get("/authorize", response_class=HTMLResponse)
async def authorize_get(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("openid"),
    state: str = Query(...),
    nonce: str = Query(None),
):
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported_response_type")
    if client_id != CLIENT_ID:
        raise HTTPException(status_code=400, detail="invalid_client")
    if redirect_uri != REDIRECT_URI:
        raise HTTPException(status_code=400, detail="invalid_redirect_uri")

    users = _load_users()
    html = _render_login_page(
        client_id=client_id,
        response_type=response_type,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        nonce=nonce,
        usernames=users,
    )
    return HTMLResponse(content=html)


@app.get("/admin/users/new", response_class=HTMLResponse)
async def admin_user_mock_page():
    return HTMLResponse(content=_render_admin_user_mock_page())


@app.post("/admin/users/new", response_class=HTMLResponse)
async def admin_user_create_mock(
    uid: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    fullName: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    hospital: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    matriculeNumber: Optional[str] = Form(None),
    nationalId: Optional[str] = Form(None),
    specialty: Optional[str] = Form(None),
    unitName: Optional[str] = Form(None),
    contactPhone: Optional[str] = Form(None),
    photoURL: Optional[str] = Form(None),
):
    try:
        access_token = await _fetch_admin_access_token()
    except HTTPException as exc:
        return HTMLResponse(content=_render_admin_create_user_page(error=exc.detail), status_code=exc.status_code)

    payload = {
        "uid": uid or None,
        "email": email or None,
        "fullName": fullName or None,
        "role": role or None,
        "hospital": hospital or None,
        "title": title or None,
        "matriculeNumber": matriculeNumber or None,
        "nationalId": nationalId or None,
        "specialty": specialty or None,
        "unitName": unitName or None,
        "contactPhone": contactPhone or None,
        "photoURL": photoURL or None,
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "")}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{APP_BASE_URL}/admin/users",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )

    if response.status_code >= 400:
        return HTMLResponse(
            content=_render_admin_create_user_page(error=response.text),
            status_code=response.status_code,
        )

    created_user = response.json().get("user", {})
    success_message = f"User created successfully: {created_user.get('uid') or created_user.get('id') or 'unknown'}."
    return HTMLResponse(content=_render_admin_create_user_page(message=success_message))


@app.post("/authorize")
async def authorize_post(
    username: str = Form(...),
    password: str = Form(...),
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form("openid"),
    state: str = Form(...),
    nonce: str = Form(None),
):
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported_response_type")
    if client_id != CLIENT_ID:
        raise HTTPException(status_code=400, detail="invalid_client")
    if redirect_uri != REDIRECT_URI:
        raise HTTPException(status_code=400, detail="invalid_redirect_uri")

    users = _load_users()
    user = users.get(username)
    if not user or user.get("password") != password:
        raise HTTPException(status_code=401, detail="invalid_user_credentials")

    code = uuid.uuid4().hex
    AUTH_CODES[code] = {
        "sub": user["sub"],
        "username": username,
        "scope": scope,
        "nonce": nonce,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "exp": int(time.time()) + 300,
    }

    redirect_params = urlencode({"code": code, "state": state})
    return RedirectResponse(url=f"{redirect_uri}?{redirect_params}", status_code=302)


@app.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(None),
    client_assertion_type: str = Form(None),
    client_assertion: str = Form(None),
):
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")

    _authenticate_client(client_id, client_secret, client_assertion_type, client_assertion)

    code_data = AUTH_CODES.pop(code, None)
    if not code_data:
        raise HTTPException(status_code=400, detail="invalid_or_used_code")

    if code_data["exp"] < int(time.time()):
        raise HTTPException(status_code=400, detail="expired_code")
    if redirect_uri != code_data["redirect_uri"]:
        raise HTTPException(status_code=400, detail="invalid_redirect_uri")

    user = _load_users().get(code_data["username"])
    if not user:
        raise HTTPException(status_code=400, detail="invalid_user")

    token_data = _mint_tokens(user, nonce=code_data.get("nonce"), scope=code_data.get("scope", "openid"))
    return JSONResponse(content=token_data)


@app.get("/userinfo")
async def userinfo(authorization: str = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")

    token = authorization.split(" ", 1)[1]
    try:
        claims = jwt.decode(
            token,
            _load_public_pem_from_private(PROVIDER_PRIVATE_KEY_PATH),
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid_access_token: {exc}")

    user_by_sub = {u["sub"]: u for u in _load_users().values()}
    user = user_by_sub.get(claims.get("sub"))
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    return _user_claims(user)
