from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)

DEMO_VIEWER_ROLE = "demo_viewer"
DEMO_VIEWER_SUBJECT = "demo-viewer"
DEMO_VIEWER_EMAIL = "demo-viewer@adops-signal.local"
DEMO_VIEWER_NAME = "Public Demo Viewer"
DEMO_SESSION_MINUTES = 60


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_text))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> tuple[str, int]:
    settings = get_settings()
    expires = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + expires,
        "iss": "adops-signal",
        "aud": "adops-signal-web",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(expires.total_seconds())


def create_demo_access_token() -> tuple[str, int]:
    """Issue a token for the public, read-only portfolio demo.

    Deliberately not backed by a database row: the JWT carries the
    demo_viewer role directly, and get_current_user() recognizes it without a
    lookup. require_roles() already excludes demo_viewer from every
    mutation-gated endpoint, and the agent layer skips audit/recommendation
    writes for this role - see api/agent.py.
    """
    settings = get_settings()
    expires = timedelta(minutes=DEMO_SESSION_MINUTES)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": DEMO_VIEWER_SUBJECT,
        "email": DEMO_VIEWER_EMAIL,
        "role": DEMO_VIEWER_ROLE,
        "demo": True,
        "iat": now,
        "exp": now + expires,
        "iss": "adops-signal",
        "aud": "adops-signal-web",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(expires.total_seconds())


def build_demo_viewer() -> User:
    return User(
        id=0,
        email=DEMO_VIEWER_EMAIL,
        full_name=DEMO_VIEWER_NAME,
        password_hash="",
        role=DEMO_VIEWER_ROLE,
        is_active=True,
    )


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.email == email.lower().strip())).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    if not settings.auth_enabled:
        user = db.execute(select(User).order_by(User.id).limit(1)).scalar_one_or_none()
        if user:
            return user
        raise HTTPException(status_code=503, detail="Demo user is not seeded")
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="adops-signal-web",
            issuer="adops-signal",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token") from exc
    if payload.get("sub") == DEMO_VIEWER_SUBJECT and payload.get("role") == DEMO_VIEWER_ROLE:
        return build_demo_viewer()
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token") from exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
