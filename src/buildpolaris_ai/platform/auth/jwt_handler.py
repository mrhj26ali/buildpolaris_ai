"""JWT handling for forwarded BFF tokens (NFR-SEC.8)."""
from __future__ import annotations

import time
from typing import Optional

import jwt
import structlog

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.schemas import UserContext

logger = structlog.get_logger()


class JWTHandler:
    """Verifies BFF-issued JWTs and extracts UserContext."""

    def __init__(self) -> None:
        self._settings = get_settings().auth

    async def verify_and_decode(self, token: str) -> Optional[UserContext]:
        """Verify JWT signature and extract claims."""
        if self._settings.mode == "dev":
            return self._dev_mode_decode(token)

        try:
            if self._settings.mode == "secret":
                secret = self._settings.jwt_secret.get_secret_value()
                payload = jwt.decode(
                    token,
                    secret,
                    algorithms=["HS256"],
                    options={
                        "verify_exp": True,
                        "verify_iat": True,
                    },
                    leeway=self._settings.leeway_seconds,
                )
            elif self._settings.mode == "jwks":
                # RS256 with JWKS (production)
                jwks_client = jwt.PyJWKClient(self._settings.jwks_url)
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self._settings.expected_audience,
                    issuer=self._settings.expected_issuer,
                    leeway=self._settings.leeway_seconds,
                )
            else:
                logger.error("Unknown auth mode", mode=self._settings.mode)
                return None

            return self._extract_user_context(payload)

        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("JWT invalid", error=str(e))
            return None
        except Exception as e:
            logger.error("JWT decode unexpected error", error=str(e))
            return None

    def _dev_mode_decode(self, token: str) -> Optional[UserContext]:
        """Dev mode: accept mock tokens for local testing."""
        if token.startswith("mock-jwt-"):
            tenant_id = token.replace("mock-jwt-", "")
            return UserContext(
                user_id="dev-user",
                tenant_id=tenant_id,
                company_id="dev-company",
                assigned_project_ids=["PROJ-001"],
                role="Project Manager",
            )
        # In dev mode, also try HS256 with the dev secret
        try:
            secret = self._settings.jwt_secret.get_secret_value()
            payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False})
            return self._extract_user_context(payload)
        except Exception:
            return None

    def _extract_user_context(self, payload: dict) -> UserContext:
        return UserContext(
            user_id=payload.get("sub", payload.get("user_id", "unknown")),
            tenant_id=payload.get("tenant_id", payload.get("company_id", "unknown")),
            company_id=payload.get("company_id", payload.get("tenant_id", "unknown")),
            assigned_project_ids=payload.get("project_ids", []),
            role=payload.get("role", "Viewer"),
        )

    def create_dev_token(self, tenant_id: str, user_id: str = "dev-user") -> str:
        """Create a dev-mode token for testing."""
        secret = self._settings.jwt_secret.get_secret_value()
        payload = {
            "sub": user_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "company_id": tenant_id,
            "project_ids": ["PROJ-001"],
            "role": "Project Manager",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        return jwt.encode(payload, secret, algorithm="HS256")
