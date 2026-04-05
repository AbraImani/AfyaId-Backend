"""
AfyaId Backend — Main Application Entrypoint

FastAPI application integrating eSignet (OIDC) authentication with Firestore.

Startup:
    - Initializes Firebase Admin SDK
    - Pre-fetches eSignet OIDC discovery configuration
    - Caches JWKS public keys for JWT validation

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from services.firebase_service import init_firebase
from services.auth_service import get_oidc_config, get_jwks
from auth.routes import router as auth_router
from routes.kyc_routes import router as kyc_router
from routes.patient_routes import router as patient_router
from routes.user_routes import router as user_router
from routes.admin_routes import router as admin_router

# ── Logging Configuration ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application Lifespan (startup / shutdown) ────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown events.
    
    On startup:
    1. Initialize Firebase Admin SDK with service account credentials
    2. Fetch and cache eSignet OIDC discovery document
    3. Fetch and cache JWKS public keys for JWT validation
    """
    logger.info("=" * 60)
    logger.info("AfyaId Backend — Starting up...")
    logger.info("=" * 60)

    # Step 1: Initialize Firebase
    try:
        init_firebase()
        logger.info("✅ Firebase initialized successfully")
    except Exception as e:
        logger.error(f"❌ Firebase initialization failed: {e}")
        raise

    # Step 2: Pre-fetch OIDC discovery configuration
    try:
        oidc_config = await get_oidc_config()
        logger.info(f"✅ OIDC discovery loaded from: {settings.esignet_base_url}")
        logger.info(f"   Issuer: {oidc_config.get('issuer')}")
    except Exception as e:
        logger.warning(f"⚠️  OIDC discovery pre-fetch failed (will retry on first request): {e}")

    # Step 3: Pre-fetch JWKS
    try:
        jwks = await get_jwks()
        logger.info(f"✅ JWKS loaded ({len(jwks.get('keys', []))} keys)")
    except Exception as e:
        logger.warning(f"⚠️  JWKS pre-fetch failed (will retry on first request): {e}")

    logger.info("=" * 60)
    logger.info("AfyaId Backend — Ready to accept requests")
    logger.info(f"  eSignet Base URL: {settings.esignet_base_url}")
    logger.info(f"  Client ID: {settings.client_id[:8]}..." if settings.client_id else "  Client ID: NOT SET")
    logger.info(f"  Redirect URI: {settings.redirect_uri}")
    logger.info("=" * 60)

    yield  # App is running

    # Shutdown
    logger.info("AfyaId Backend — Shutting down...")


# ── FastAPI Application ──────────────────────────────────────────
app = FastAPI(
    title="AfyaId Backend",
    description=(
        "Backend API for AfyaId — Digital identity management "
        "integrating eSignet (MOSIP) OIDC authentication with "
        "Firestore for healthcare identity and patient management."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ──────────────────────────────────────────────
# Allow the Flutter app and frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ─────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(kyc_router)
app.include_router(user_router)
app.include_router(patient_router)
app.include_router(admin_router)


# ── Health Check ─────────────────────────────────────────────────
@app.get(
    "/",
    tags=["Health"],
    summary="Health Check",
    description="Returns the API status and version.",
)
async def health_check():
    """Root endpoint — confirms the API is running."""
    return {
        "status": "healthy",
        "service": "AfyaId Backend",
        "version": "1.0.0",
        "provider": "eSignet (MOSIP)",
        "docs": "/docs",
    }


@app.get(
    "/health",
    tags=["Health"],
    summary="Detailed Health Check",
)
async def detailed_health():
    """Returns detailed health information including configuration status."""
    return {
        "status": "healthy",
        "esignet_base_url": settings.esignet_base_url,
        "client_id_configured": bool(settings.client_id),
        "firebase_configured": True,
        "private_key_configured": bool(settings.private_key_pem_path),
    }
