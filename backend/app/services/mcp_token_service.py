"""Issuance and verification for hosted external MCP access tokens (Phase 3F).
Only a SHA-256 hash is ever persisted; the raw token is returned exactly once,
at creation, in the API response - never logged, never stored, never
retrievable again afterward.
"""
from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MCPAccessToken
from app.time_utils import utc_now

TOKEN_PREFIX = "mcp_ext_"


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_token(
    db: Session, *, name: str, scope: str = "read", rate_limit_per_minute: int = 30, created_by: int | None = None
) -> tuple[MCPAccessToken, str]:
    raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = MCPAccessToken(
        name=name, token_hash=_hash(raw_token), scope=scope,
        rate_limit_per_minute=rate_limit_per_minute, is_active=True, created_by=created_by,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token, raw_token


def verify_token(db: Session, raw_token: str) -> MCPAccessToken | None:
    if not raw_token or not raw_token.startswith(TOKEN_PREFIX):
        return None
    token = db.execute(
        select(MCPAccessToken).where(MCPAccessToken.token_hash == _hash(raw_token), MCPAccessToken.is_active.is_(True))
    ).scalar_one_or_none()
    if token is not None:
        token.last_used_at = utc_now()
        db.add(token)
        db.commit()
    return token


def revoke_token(db: Session, token_id: int) -> MCPAccessToken | None:
    token = db.get(MCPAccessToken, token_id)
    if token is None:
        return None
    token.is_active = False
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def list_tokens(db: Session) -> list[MCPAccessToken]:
    return list(db.execute(select(MCPAccessToken).order_by(MCPAccessToken.created_at.desc())).scalars())
