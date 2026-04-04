import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import JWTError, jwt

ISSUER = os.getenv("OIDC_ISSUER", "http://localhost:9000").rstrip("/")
USERS_FILE = os.getenv("USERS_FILE", "/app/users.json")
KEYS_DIR = Path(os.getenv("KEYS_DIR", "/app/keys"))
CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "afya-local-client")
CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "afya-local-secret")
REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "http://localhost:8000/auth/callback")

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
    options = "".join(f'<option value="{u}">{u}</option>' for u in users.keys())

    html = f"""
    <html>
      <head><title>Afya Mock OIDC Login</title></head>
      <body style=\"font-family: sans-serif; max-width: 560px; margin: 40px auto;\">
        <h2>AfyaID Mock eSignet Login</h2>
        <p>Client: <strong>{client_id}</strong></p>
        <form method=\"post\" action=\"/authorize\">
          <label>Username</label><br/>
          <select name=\"username\" required>{options}</select><br/><br/>
          <label>Password</label><br/>
          <input type=\"password\" name=\"password\" required/><br/><br/>

          <input type=\"hidden\" name=\"response_type\" value=\"{response_type}\"/>
          <input type=\"hidden\" name=\"client_id\" value=\"{client_id}\"/>
          <input type=\"hidden\" name=\"redirect_uri\" value=\"{redirect_uri}\"/>
          <input type=\"hidden\" name=\"scope\" value=\"{scope}\"/>
          <input type=\"hidden\" name=\"state\" value=\"{state}\"/>
          <input type=\"hidden\" name=\"nonce\" value=\"{nonce or ''}\"/>
          <button type=\"submit\">Login and Authorize</button>
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


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
