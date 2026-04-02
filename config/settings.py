"""
Application configuration loaded from environment variables.
Provides settings for eSignet OIDC, Firebase, and app-level config.
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load .env file from the project root
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── eSignet OIDC Configuration ────────────────────────────────
    esignet_base_url: str = Field(
        default="https://esignet-mock.collab.mosip.net",
        description="Base URL for eSignet IdP (discovery auto-fetched)"
    )
    client_id: str = Field(
        default="",
        description="OAuth2 Client ID registered with eSignet"
    )
    client_secret: str = Field(
        default="",
        description="OAuth2 Client Secret (fallback if no private key)"
    )
    redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
        description="Redirect URI registered with eSignet"
    )
    private_key_pem_path: str = Field(
        default="",
        description="Path to RSA private key PEM for private_key_jwt auth"
    )
    jwt_audience: str = Field(
        default="",
        description="Expected JWT audience (defaults to client_id if empty)"
    )

    # ── Firebase Configuration ────────────────────────────────────
    firebase_credentials_json: str = Field(
        default="./afyaid-backend1-firebase-adminsdk-fbsvc-b17807b016.json",
        description="Path to Firebase service account JSON file"
    )
    firebase_project_id: str = Field(
        default="",
        description="Firebase project ID"
    )
    app_env: str = Field(
        default="development",
        description="Application environment (development/staging/production)"
    )
    allow_firebase_local_fallback: bool = Field(
        default=True,
        description="Allow in-memory Firestore fallback when cloud is unavailable"
    )

    # ── Application Settings ─────────────────────────────────────
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend URL for CORS and post-login redirect"
    )
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080,http://localhost:8000",
        description="Comma-separated allowed CORS origins"
    )
    app_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of this backend API"
    )
    app_secret_key: str = Field(
        default="change-this-to-a-random-secret-key",
        description="Secret key for session/state signing"
    )

    @property
    def effective_jwt_audience(self) -> str:
        """JWT audience for token validation — falls back to client_id."""
        return self.jwt_audience or self.client_id

    @property
    def oidc_discovery_url(self) -> str:
        """OpenID Connect discovery endpoint URL."""
        return f"{self.esignet_base_url.rstrip('/')}/.well-known/openid-configuration"

    @property
    def jwks_url(self) -> str:
        """JWKS endpoint URL (fallback if not in discovery)."""
        return f"{self.esignet_base_url.rstrip('/')}/.well-known/jwks.json"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Normalized allowed CORS origins from env + frontend_url."""
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins

    @property
    def is_production(self) -> bool:
        """Whether the app is running in production mode."""
        return self.app_env.strip().lower() == "production"

    @property
    def firebase_local_fallback_enabled(self) -> bool:
        """Enable local Firestore fallback only outside production unless explicitly disabled."""
        return self.allow_firebase_local_fallback and not self.is_production

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Singleton settings instance
settings = Settings()
