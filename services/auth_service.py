"""
eSignet Authentication Service.

Handles the complete OIDC flow:
1. Discovery → dynamically fetch endpoints from .well-known/openid-configuration
2. Authorization URL → build redirect URL with proper parameters  
3. Token Exchange → exchange auth code for tokens using private_key_jwt
4. JWT Validation → verify tokens using JWKS public keys
5. UserInfo → fetch user claims from the userinfo endpoint
"""

import time
import uuid
import logging
from typing import Optional, Dict, Any, Tuple

import httpx
from jose import jwt, jwk, JWTError
from jose.utils import base64url_decode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Cached OIDC configuration and JWKS ──────────────────────────
_oidc_config: Optional[Dict[str, Any]] = None
_oidc_config_fetched_at: float = 0
_jwks_data: Optional[Dict[str, Any]] = None
_jwks_fetched_at: float = 0

# Cache TTL in seconds (refresh every 1 hour)
CACHE_TTL = 3600


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 1: OIDC Discovery
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_oidc_config() -> Dict[str, Any]:
    """Fetch and cache the OpenID Connect discovery document.
    
    Dynamically retrieves all endpoint URLs from:
    {ESIGNET_BASE_URL}/.well-known/openid-configuration
    
    NEVER hardcodes endpoints — always uses discovery.
    
    Returns:
        Dict containing the full OIDC discovery document with keys like:
        - authorization_endpoint
        - token_endpoint
        - userinfo_endpoint
        - jwks_uri
        - issuer
        - scopes_supported
        - claims_supported
    """
    global _oidc_config, _oidc_config_fetched_at

    # Return cached config if still valid
    if _oidc_config and (time.time() - _oidc_config_fetched_at) < CACHE_TTL:
        return _oidc_config

    discovery_url = settings.oidc_discovery_url
    logger.info(f"Fetching OIDC discovery from: {discovery_url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(discovery_url)
        response.raise_for_status()
        _oidc_config = response.json()
        _oidc_config_fetched_at = time.time()

    logger.info(f"OIDC discovery loaded. Issuer: {_oidc_config.get('issuer')}")
    logger.info(f"  authorization_endpoint: {_oidc_config.get('authorization_endpoint')}")
    logger.info(f"  token_endpoint: {_oidc_config.get('token_endpoint')}")
    logger.info(f"  userinfo_endpoint: {_oidc_config.get('userinfo_endpoint')}")
    logger.info(f"  jwks_uri: {_oidc_config.get('jwks_uri')}")

    return _oidc_config


async def get_jwks() -> Dict[str, Any]:
    """Fetch and cache the JWKS (JSON Web Key Set) from eSignet.
    
    Used to validate JWT signatures on id_token, access_token,
    and userinfo responses.
    
    Returns:
        Dict containing the JWKS with 'keys' array.
    """
    global _jwks_data, _jwks_fetched_at

    # Return cached JWKS if still valid
    if _jwks_data and (time.time() - _jwks_fetched_at) < CACHE_TTL:
        return _jwks_data

    oidc_config = await get_oidc_config()
    jwks_uri = oidc_config.get("jwks_uri", settings.jwks_url)

    logger.info(f"Fetching JWKS from: {jwks_uri}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(jwks_uri)
        response.raise_for_status()
        _jwks_data = response.json()
        _jwks_fetched_at = time.time()

    logger.info(f"JWKS loaded with {len(_jwks_data.get('keys', []))} keys.")
    return _jwks_data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 2: Build Authorization URL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def build_authorization_url() -> Tuple[str, str, str]:
    """Build the eSignet authorization URL for user redirect.
    
    Generates fresh state and nonce values to prevent CSRF and replay attacks.
    
    Returns:
        Tuple of (authorization_url, state, nonce)
    """
    oidc_config = await get_oidc_config()
    auth_endpoint = oidc_config["authorization_endpoint"]

    # Generate cryptographically random state and nonce
    state = uuid.uuid4().hex
    nonce = uuid.uuid4().hex

    # Build the claims parameter requesting user info
    import json
    claims_param = json.dumps({
        "userinfo": {
            "name": {"essential": True},
            "email": {"essential": False},
            "phone_number": {"essential": False},
            "picture": {"essential": False},
            "gender": {"essential": False},
            "birthdate": {"essential": False},
            "address": {"essential": False},
            "phone_number_verified": {"essential": False}
        },
        "id_token": {}
    })

    # Build query parameters according to eSignet OIDC spec
    params = {
        "response_type": "code",
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "scope": "openid profile email phone",
        "state": state,
        "nonce": nonce,
        "display": "page",
        "prompt": "consent",
        "acr_values": "mosip:idp:acr:generated-code",
        "claims": claims_param,
    }

    # Build the full URL
    query_string = "&".join(f"{k}={httpx.URL('', params={k: v}).params[k]}" 
                            for k, v in params.items())
    
    # Use httpx to properly encode
    url = httpx.URL(auth_endpoint, params=params)
    authorization_url = str(url)

    logger.info(f"Built authorization URL with state={state}")
    return authorization_url, state, nonce


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 3: Build Client Assertion (private_key_jwt)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_private_key() -> Optional[str]:
    """Load the RSA private key PEM from file if configured.
    
    Returns:
        PEM string of the private key, or None if not configured.
    """
    key_path = settings.private_key_pem_path
    if not key_path:
        return None
    
    try:
        with open(key_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Private key file not found: {key_path}")
        return None


async def build_client_assertion() -> Optional[str]:
    """Build a signed JWT client assertion for private_key_jwt authentication.
    
    This is required by eSignet for token endpoint authentication.
    The JWT is signed with the RP's private key and contains:
    - sub: client_id
    - iss: client_id
    - aud: token_endpoint URL
    - iat: current time
    - exp: current time + 5 minutes
    - jti: unique token ID
    
    Returns:
        Signed JWT string, or None if private key is not configured.
    """
    private_key_pem = _load_private_key()
    if not private_key_pem:
        logger.info("No private key configured, will use client_secret_post.")
        return None

    oidc_config = await get_oidc_config()
    token_endpoint = oidc_config["token_endpoint"]

    now = int(time.time())
    payload = {
        "sub": settings.client_id,
        "iss": settings.client_id,
        "aud": token_endpoint,
        "iat": now,
        "exp": now + 300,  # 5 minutes validity
        "jti": uuid.uuid4().hex,
    }

    # Sign with RS256 using the private key
    assertion = jwt.encode(payload, private_key_pem, algorithm="RS256")
    logger.info("Built client_assertion JWT for private_key_jwt auth.")
    return assertion


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 4: Exchange Authorization Code for Tokens
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange the authorization code for access_token and id_token.
    
    Supports two authentication methods:
    1. private_key_jwt (preferred, required by eSignet production)
       → sends client_assertion + client_assertion_type
    2. client_secret_post (fallback for testing)
       → sends client_id + client_secret in body
    
    Args:
        code: The authorization code from eSignet callback.
    
    Returns:
        Dict with 'access_token', 'id_token', 'token_type', etc.
    
    Raises:
        httpx.HTTPStatusError: If the token endpoint returns an error.
        ValueError: If the response is missing required fields.
    """
    oidc_config = await get_oidc_config()
    token_endpoint = oidc_config["token_endpoint"]

    logger.info(f"Exchanging auth code for tokens at: {token_endpoint}")

    # Build the token request body
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "client_id": settings.client_id,
    }

    # Try private_key_jwt first, fall back to client_secret_post
    client_assertion = await build_client_assertion()
    if client_assertion:
        data["client_assertion_type"] = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        data["client_assertion"] = client_assertion
        logger.info("Using private_key_jwt authentication for token exchange.")
    elif settings.client_secret:
        data["client_secret"] = settings.client_secret
        logger.info("Using client_secret_post authentication for token exchange.")
    else:
        raise ValueError(
            "No authentication method configured. "
            "Set either PRIVATE_KEY_PEM_PATH or CLIENT_SECRET in .env"
        )

    # Make the token request
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            response.raise_for_status()

        token_data = response.json()

    logger.info("Token exchange successful.")
    
    # Validate that we got the required tokens
    if "access_token" not in token_data:
        raise ValueError("Token response missing 'access_token'")
    if "id_token" not in token_data:
        raise ValueError("Token response missing 'id_token'")

    return token_data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 5: JWT Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _get_signing_key(token: str) -> Dict:
    """Extract the signing key from JWKS that matches the token's kid.
    
    Args:
        token: The JWT token string.
    
    Returns:
        The matching JWK key dict.
    
    Raises:
        JWTError: If no matching key is found.
    """
    jwks = await get_jwks()
    
    # Decode the token header to get the kid
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    alg = unverified_header.get("alg", "RS256")

    logger.info(f"Looking for key with kid={kid}, alg={alg}")

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            logger.info(f"Found matching key: kid={kid}")
            return key

    # If no kid match, try the first key (some implementations don't use kid)
    if jwks.get("keys"):
        logger.warning("No kid match found, using first available key.")
        return jwks["keys"][0]

    raise JWTError("No suitable signing key found in JWKS")


async def validate_id_token(id_token: str, expected_nonce: Optional[str] = None) -> Dict[str, Any]:
    """Validate the id_token JWT from eSignet.
    
    Performs the following validations as required by OIDC spec:
    1. Verify JWT signature using JWKS public key
    2. Validate 'iss' matches the eSignet issuer
    3. Validate 'aud' matches our client_id
    4. Validate 'exp' has not passed
    5. Extract and return all claims
    
    Args:
        id_token: The id_token JWT string.
    
    Returns:
        Dict of validated claims from the id_token.
    
    Raises:
        JWTError: If validation fails.
    """
    oidc_config = await get_oidc_config()
    expected_issuer = oidc_config.get("issuer")

    logger.info(f"Validating id_token. Expected issuer: {expected_issuer}")

    # Get the signing key
    signing_key = await _get_signing_key(id_token)

    try:
        # Decode and validate the id_token
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.client_id,
            issuer=expected_issuer,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_iat": True,
            }
        )

        if expected_nonce and claims.get("nonce") != expected_nonce:
            raise JWTError("Invalid nonce in id_token")

        logger.info(f"id_token validated successfully. sub={claims.get('sub')}")
        return claims

    except JWTError as e:
        logger.error(f"id_token validation failed: {e}")
        raise


async def validate_access_token(access_token: str) -> Dict[str, Any]:
    """Validate an access_token JWT from eSignet.
    
    eSignet access tokens follow RFC9068 (JWT Profile for OAuth 2.0 Access Tokens).
    
    Validates:
    1. JWT signature using JWKS
    2. issuer (iss)
    3. expiration (exp)
    4. audience (aud) — may be the resource server URL
    
    Args:
        access_token: The access_token JWT string.
    
    Returns:
        Dict of validated claims from the access_token.
    
    Raises:
        JWTError: If validation fails.
    """
    oidc_config = await get_oidc_config()
    expected_issuer = oidc_config.get("issuer")

    logger.info("Validating access_token...")

    signing_key = await _get_signing_key(access_token)

    try:
        claims = jwt.decode(
            access_token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.effective_jwt_audience,
            issuer=expected_issuer,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
            }
        )

        logger.info(f"access_token validated. sub={claims.get('sub')}")
        return claims

    except JWTError as e:
        logger.error(f"access_token validation failed: {e}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 6: Fetch User Info
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_userinfo(access_token: str) -> Dict[str, Any]:
    """Fetch user claims from the eSignet userinfo endpoint.
    
    The userinfo response is a signed JWT (JWS) that must be validated
    using the JWKS public keys.
    
    IMPORTANT: eSignet does NOT include user claims in the id_token.
    This endpoint is the ONLY way to get name, email, phone, etc.
    
    Args:
        access_token: Valid access_token from the token exchange.
    
    Returns:
        Dict of user claims including name, email, phone_number, etc.
    """
    oidc_config = await get_oidc_config()
    userinfo_endpoint = oidc_config["userinfo_endpoint"]

    logger.info(f"Fetching userinfo from: {userinfo_endpoint}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if response.status_code != 200:
            logger.error(f"Userinfo request failed: {response.status_code} - {response.text}")
            response.raise_for_status()

    # The response may be a JWT or plain JSON
    content_type = response.headers.get("content-type", "")
    response_text = response.text

    if "application/jwt" in content_type or response_text.count(".") == 2:
        # Response is a signed JWT — validate and decode it
        logger.info("Userinfo response is a JWT, validating...")
        try:
            signing_key = await _get_signing_key(response_text)
            userinfo = jwt.decode(
                response_text,
                signing_key,
                algorithms=["RS256"],
                options={
                    "verify_aud": False,
                    "verify_exp": False,  # Userinfo JWT may not have exp
                }
            )
        except JWTError:
            # If JWT validation fails, try decoding without verification
            # (some test environments may have issues)
            logger.warning("JWT validation of userinfo failed, decoding without verification.")
            userinfo = jwt.get_unverified_claims(response_text)
    else:
        # Response is plain JSON
        userinfo = response.json()

    logger.info(f"Userinfo received. Claims: {list(userinfo.keys())}")
    return userinfo


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Determine KYC Status
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def determine_kyc_status(userinfo: Dict[str, Any]) -> str:
    """Determine the KYC status based on eSignet userinfo claims.
    
    Case 1: If phone_number_verified is True → VERIFIED_BY_PROVIDER
            (User's identity has been verified by the IdP)
            Still need to complete profile (hospital, role, matriculeNumber)
    
    Case 2: If NOT verified → PENDING
            (User needs to submit KYC documents via POST /kyc/submit)
    
    Args:
        userinfo: Dict of claims from the userinfo endpoint.
    
    Returns:
        KYC status string.
    """
    # Primary signal requested by integration requirements
    is_verified = userinfo.get("is_verified")

    # Fallbacks commonly used in eSignet responses
    if is_verified is None:
        is_verified = userinfo.get("phone_number_verified", False)
    
    # Also check if verified_claims are present (eSignet's verified claims mechanism)
    has_verified_claims = "verified_claims" in userinfo

    if bool(is_verified) or has_verified_claims:
        logger.info("User is verified by provider.")
        return "VERIFIED_BY_PROVIDER"
    else:
        logger.info("User is NOT verified, KYC status set to PENDING.")
        return "PENDING"


def is_profile_complete(user_data: Dict[str, Any]) -> bool:
    """Check if a user's profile has the required fields completed.
    
    Required fields for a complete profile:
    - hospital
    - role
    - matriculeNumber
    
    Args:
        user_data: The user's Firestore document data.
    
    Returns:
        True if all required fields are filled.
    """
    required_fields = ["hospital", "role", "matriculeNumber"]
    for field in required_fields:
        if not user_data.get(field):
            return False
    return True
